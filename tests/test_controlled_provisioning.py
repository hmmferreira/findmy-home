"""Synthetic provisioning handshake; no native library or Apple connection."""
import asyncio
import base64
import hashlib
from pathlib import Path
import plistlib
import tempfile
import threading
import unittest
from unittest.mock import patch

from findmy_home.apple_transport import OwnedHttpSession,Response,TransportBlocked,validate_destination
from findmy_home.controlled_provisioning import (provision_new_identity,ProvisioningBlocked,LOOKUP,START,FINISH)

class Worker:
    def __init__(self):self.calls=[];self.closed=False
    async def prepare(self,artifact):
        self.calls.append(("prepare",artifact))
        return {"X-Mme-Device-Id":"SYNTHETIC-DEVICE","X-MMe-Client-Info":"Synthetic client","X-Apple-I-MD-LU":"SYNTHETIC-UUID"}
    async def begin(self,spim):self.calls.append(("begin",spim));return b"PRIVATE_CPIM"
    async def finish(self,ptm,tk):self.calls.append(("finish",ptm,tk));return b"PRIVATE_STATE"
    async def close(self):self.closed=True

class Http(OwnedHttpSession):
    def __init__(self):
        self.profile="provisioning";self.calls=[];self.closed=False
        self.responses=[{"urls":{"midStartProvisioning":START,"midFinishProvisioning":FINISH}},
            {"Response":{"spim":base64.b64encode(b"PRIVATE_SPIM").decode()}},
            {"Response":{"ptm":base64.b64encode(b"PRIVATE_PTM").decode(),"tk":base64.b64encode(b"PRIVATE_TK").decode()}}]
        self.error=None
    async def request(self,method,url,**kwargs):
        validate_destination(self.profile,method,url)
        self.calls.append((method,url,kwargs))
        if self.error:raise self.error
        return Response(200,plistlib.dumps(self.responses.pop(0)),{})
    async def close(self):self.closed=True

class ControlledProvisioningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"library.bin"
        self.path.write_bytes(b"SYNTHETIC_ARTIFACT");self.digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.worker=Worker();self.http=Http()
    async def asyncTearDown(self):self.tmp.cleanup()
    async def run_flow(self,**extra):
        return await provision_new_identity(self.path,self.digest,worker=self.worker,transport=self.http,
            create_new_identity=True,**extra)
    async def test_complete_async_handshake_returns_private_state_without_file_write(self):
        self.assertEqual(await self.run_flow(),b"PRIVATE_STATE")
        self.assertEqual([v[:2] for v in self.http.calls],[("GET",LOOKUP),("POST",START),("POST",FINISH)])
        payload=plistlib.loads(self.http.calls[2][2]["data"])
        self.assertEqual(payload,{"Header":{},"Request":{"cpim":base64.b64encode(b"PRIVATE_CPIM").decode()}})
        self.assertEqual(self.worker.calls[-1],("finish",b"PRIVATE_PTM",b"PRIVATE_TK"))
        self.assertTrue(self.worker.closed);self.assertTrue(self.http.closed)
        self.assertEqual(list(Path(self.tmp.name).iterdir()),[self.path])
    async def test_explicit_user_agent_is_used_and_injection_refused(self):
        await self.run_flow(user_agent="Synthetic aligned CFNetwork/1 Darwin/2")
        for _,_,options in self.http.calls:
            self.assertEqual(options["headers"]["User-Agent"],"Synthetic aligned CFNetwork/1 Darwin/2")
        self.worker=Worker();self.http=Http()
        with self.assertRaises(ProvisioningBlocked):await self.run_flow(user_agent="bad\r\nheader")
        self.assertFalse(self.worker.calls);self.assertFalse(self.http.calls)
    async def test_missing_worker_or_explicit_creation_never_starts(self):
        for kwargs,code in (({},"explicit_new_identity_required"),({"create_new_identity":True},"isolated_provisioning_worker_required")):
            with self.assertRaises(ProvisioningBlocked) as caught:
                await provision_new_identity(self.path,self.digest,**kwargs)
            self.assertEqual(str(caught.exception),code)
        self.assertFalse(self.worker.calls)
    async def test_bad_artifact_never_reaches_worker_or_network(self):
        self.path.write_bytes(b"TAMPERED")
        with self.assertRaises(ProvisioningBlocked) as caught:await self.run_flow()
        self.assertEqual(str(caught.exception),"artifact_digest_mismatch")
        self.assertFalse(self.worker.calls);self.assertFalse(self.http.calls)
        self.assertTrue(self.worker.closed)
    async def test_missing_symlink_directory_or_unreviewed_artifact_rejected(self):
        original=self.path
        for kind in ("missing","symlink","directory"):
            self.path=Path(self.tmp.name)/kind
            if kind=="symlink":self.path.symlink_to(original)
            elif kind=="directory":self.path.mkdir()
            with self.subTest(kind=kind),self.assertRaises(ProvisioningBlocked):await self.run_flow()
        self.path=original;self.digest="not-reviewed"
        with self.assertRaises(ProvisioningBlocked):await self.run_flow()
        self.assertFalse(self.worker.calls);self.assertFalse(self.http.calls)
    async def test_both_bag_urls_validated_before_provisioning_payload(self):
        for value in ("https://attacker.example/PRIVATE","https://gsa.apple.com.evil/start",START+"?extra=1",FINISH):
            self.http=Http();self.http.responses[0]["urls"]["midStartProvisioning"]=value
            with self.subTest(value=value),self.assertRaises(ProvisioningBlocked) as caught:await self.run_flow()
            self.assertEqual(str(caught.exception),"provisioning_endpoints_changed")
            self.assertEqual(len(self.http.calls),1)
        self.http=Http();self.http.responses[0]["urls"]["midFinishProvisioning"]="https://attacker.example/"
        with self.assertRaises(ProvisioningBlocked):await self.run_flow()
        self.assertEqual(len(self.http.calls),1)
    async def test_injected_account_headers_are_rejected(self):
        async def prepare(_):return {"Authorization":"PRIVATE_ACCOUNT_PASSWORD"}
        self.worker.prepare=prepare
        with self.assertRaises(ProvisioningBlocked) as caught:await self.run_flow()
        self.assertEqual(str(caught.exception),"worker_identity_invalid")
        self.assertFalse(self.http.calls)
    async def test_failures_redacted_and_never_retried(self):
        self.http.error=RuntimeError("PRIVATE_TOKEN_AT_URL")
        with self.assertRaises(ProvisioningBlocked) as caught:await self.run_flow()
        self.assertEqual(str(caught.exception),"provisioning_failed")
        self.assertEqual(len(self.http.calls),1)
        self.assertTrue(self.http.closed);self.assertTrue(self.worker.closed)
    async def test_redirect_error_remains_blocked_without_retry(self):
        self.http.error=TransportBlocked("redirect_blocked")
        with self.assertRaises(ProvisioningBlocked) as caught:await self.run_flow()
        self.assertEqual(str(caught.exception),"redirect_blocked")
        self.assertEqual(len(self.http.calls),1)
    async def test_invalid_base64_or_missing_response_never_reaches_native_begin(self):
        for response in ({"Response":{"spim":"not base64!"}},{"Response":{}},{"Response":[]}):
            self.http=Http();self.worker=Worker();self.http.responses[1]=response
            with self.subTest(response=response),self.assertRaises(ProvisioningBlocked):await self.run_flow()
            self.assertEqual(len(self.worker.calls),1)
    async def test_timeout_and_cancel_close_resources_without_finish(self):
        entered=asyncio.Event()
        async def wait(_):entered.set();await asyncio.Event().wait()
        self.worker.begin=wait
        with self.assertRaises(ProvisioningBlocked) as caught:await self.run_flow(timeout=.02)
        self.assertEqual(str(caught.exception),"provisioning_timeout")
        self.assertTrue(self.worker.closed);self.assertTrue(self.http.closed)
        self.worker=Worker();self.worker.begin=wait;self.http=Http();entered.clear()
        task=asyncio.create_task(self.run_flow());await entered.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(self.worker.closed);self.assertTrue(self.http.closed)
        self.assertEqual(len(self.http.calls),2)
    async def test_artifact_file_io_runs_off_event_loop(self):
        from findmy_home import controlled_provisioning as module
        real=module._artifact;threads=[]
        def check(*args):threads.append(threading.get_ident());return real(*args)
        with patch.object(module,"_artifact",side_effect=check):await self.run_flow()
        self.assertNotEqual(threads,[threading.get_ident()])
    async def test_worker_cleanup_failure_never_returns_success(self):
        async def broken_close():raise RuntimeError("PRIVATE_WORKER_STATE")
        self.worker.close=broken_close
        with self.assertRaises(ProvisioningBlocked) as caught:await self.run_flow()
        self.assertEqual(str(caught.exception),"provisioning_cleanup_failed")
        self.assertTrue(self.http.closed)
    async def test_unowned_transport_is_refused(self):
        with self.assertRaises(ProvisioningBlocked) as caught:
            await provision_new_identity(self.path,self.digest,worker=self.worker,transport=object(),create_new_identity=True)
        self.assertEqual(str(caught.exception),"owned_transport_required")
        self.assertFalse(self.worker.calls)
    def test_provisioning_profile_has_three_exact_method_bound_routes(self):
        for method,url in (("GET",LOOKUP),("POST",START),("POST",FINISH)):
            self.assertEqual(validate_destination("provisioning",method,url),"gsa.apple.com")
        for method,url in (("POST",LOOKUP),("GET",START),("GET",FINISH),("POST",START+"?x=1"),("POST",START.replace("gsa.","gsas.")),("POST","https://gsa.apple.com/grandslam/GsService2"),("POST",START.replace("https:","http:"))):
            with self.subTest(method=method,url=url),self.assertRaises(TransportBlocked):
                validate_destination("provisioning",method,url)

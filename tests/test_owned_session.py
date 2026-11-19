"""Owned session envelope/restore tests; all state and native work synthetic."""
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from findmy_home.apple_transport import OwnedHttpSession
from findmy_home.offline_signer import OfflineSigner
from findmy_home.owned_session import snapshot_account,restore_account,SessionBlocked,_MAGIC

class Account:
    def __init__(self,provider,state_info=None,timeout=30):
        self._anisette=provider;self.state=state_info;self.timeout=timeout
        self._http=OwnedHttpSession(profile="account")
    def to_json(self):return copy.deepcopy(self.state)
    async def close(self):
        await self._anisette._owned_signer.close();await self._http.close()

class OwnedSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.library=Path(self.tmp.name)/"library"
        self.library.write_bytes(b"synthetic library");self.digest=hashlib.sha256(self.library.read_bytes()).hexdigest()
        self.key=b"synthetic-private-key-32-bytes!!!!"[:32]
        self.engine=SimpleNamespace(is_provisioned=True)
        self.signer=OfflineSigner(self.library,b"synthetic state",self.digest)
        self.build=patch("findmy_home.offline_signer._build_engine",return_value=self.engine);self.build.start()
        await self.signer.initialize()
        self.state={"type":"account","ids":{"uid":"00000000-0000-4000-8000-000000000001","devid":"00000000-0000-4000-8000-000000000002"},
            "account":{"username":"synthetic@example.invalid","password":"PRIVATE_PASSWORD","info":{}},
            "login":{"state":3,"data":{"dsid":"12345","adsid":"45678","idms_pet":"PRIVATE_PET","idms_hb":"PRIVATE_HEARTBEAT","mobileme_data":{"tokens":{"searchPartyToken":"PRIVATE_POLL_TOKEN"}}}},
            "anisette":{"type":"aniOwnedOffline","serial":"SYNTHETIC-SERIAL","library_sha256":self.digest,"prov_data":base64.b64encode(b"synthetic state").decode(),
                "identity":dict(model="SyntheticModel",os_name="SyntheticOS",os_version="1",os_build="1",cfnetwork="1",darwin="1")}}
        self.account=Account(SimpleNamespace(_owned_signer=self.signer),self.state)
    async def asyncTearDown(self):
        await self.account.close();self.build.stop();self.tmp.cleanup()
    async def save(self):return await snapshot_account(self.account,encryption_key=self.key,expires_at=2000,now=1000)
    async def restore(self,data,**kwargs):
        return await restore_account(data,encryption_key=kwargs.pop("encryption_key",self.key),library=self.library,expected_sha256=kwargs.pop("expected_sha256",self.digest),now=kwargs.pop("now",1001),**kwargs)
    def decrypt(self,data):
        offset=len(_MAGIC);return json.loads(AESGCM(self.key).decrypt(data[offset:offset+12],data[offset+12:],_MAGIC))
    def encrypt(self,value):
        nonce=b"synthetic123";return _MAGIC+nonce+AESGCM(self.key).encrypt(nonce,json.dumps(value).encode(),_MAGIC)
    async def test_snapshot_is_encrypted_password_free_and_does_not_mutate_live_account(self):
        data=await self.save();envelope=self.decrypt(data)
        for secret in (b"PRIVATE_PASSWORD",b"PRIVATE_PET",b"PRIVATE_POLL_TOKEN",b"synthetic@example.invalid"):self.assertNotIn(secret,data)
        self.assertIsNone(envelope["state"]["account"]["password"])
        self.assertNotIn("idms_pet",envelope["state"]["login"]["data"])
        self.assertNotIn("idms_hb",envelope["state"]["login"]["data"])
        self.assertEqual(self.account.state["account"]["password"],"PRIVATE_PASSWORD")
    async def test_restore_preserves_identity_and_installs_owned_transport_without_network_or_sdk_deserializer(self):
        data=await self.save()
        with patch("findmy_home.apple.ReportingAccount",Account),patch("findmy.reports.anisette.DeviceIdentity",lambda **kwargs:kwargs,create=True),patch("findmy_home.owned_session.provider_for",side_effect=lambda signer,**kwargs:SimpleNamespace(_owned_signer=signer,**kwargs)):
            restored=await self.restore(data)
        try:
            self.assertEqual(restored.state["ids"],self.state["ids"])
            self.assertEqual(restored._anisette.serial,"SYNTHETIC-SERIAL")
            self.assertEqual(restored._anisette.identity,self.state["anisette"]["identity"])
            self.assertIsNone(restored.state["account"]["password"])
            self.assertIsInstance(restored._http,OwnedHttpSession);self.assertEqual(restored._http.profile,"account")
        finally:await restored.close()
    async def test_tampering_wrong_key_truncation_and_unknown_version_fail_before_native_work(self):
        data=await self.save();self.build.stop()
        for bad,key in ((data[:-1]+bytes([data[-1]^1]),self.key),(data,b"k"*32),(data[:20],self.key),(b"unknown"+data,self.key)):
            with self.subTest(length=len(bad)),patch("findmy_home.owned_session.OfflineSigner") as signer:
                with self.assertRaises(SessionBlocked) as caught:await self.restore(bad,encryption_key=key)
                signer.assert_not_called();self.assertNotIn("PRIVATE",str(caught.exception))
        self.build.start()
    async def test_expired_future_and_excessive_lifetime_sessions_are_refused(self):
        data=await self.save()
        with self.assertRaisesRegex(SessionBlocked,"session_expired"):await self.restore(data,now=2000)
        for issue,expire in ((5000,6000),(1000,1000+31*86400)):
            value=self.decrypt(data);value.update(issued_at=issue,expires_at=expire)
            with self.assertRaises(SessionBlocked):await self.restore(self.encrypt(value))
    async def test_password_pet_missing_identity_incomplete_login_and_artifact_change_are_refused(self):
        good=self.decrypt(await self.save())
        mutations=[lambda s:s["account"].update(password="PRIVATE"),lambda s:s["login"]["data"].update(idms_pet="PRIVATE"),
            lambda s:s["anisette"]["identity"].pop("model"),lambda s:s["login"].update(state=1),lambda s:s["login"]["data"].update(mobileme_data={}),lambda s:s["anisette"].update(library_sha256="0"*64)]
        for mutate in mutations:
            value=copy.deepcopy(good);mutate(value["state"])
            with self.assertRaises(SessionBlocked):await self.restore(self.encrypt(value))
    async def test_invalid_key_or_expiry_is_refused(self):
        for key,expiry in ((b"short",2000),(self.key,999),(self.key,float("nan")),(self.key,1000+31*86400)):
            with self.assertRaises(SessionBlocked):await snapshot_account(self.account,encryption_key=key,expires_at=expiry,now=1000)
    async def test_constructor_failure_closes_signer_and_redacts_error(self):
        data=await self.save();created=[]
        def provider(signer,**kwargs):created.append(signer);raise RuntimeError("PRIVATE_EXCEPTION")
        with patch("findmy_home.owned_session.provider_for",side_effect=provider),patch("findmy.reports.anisette.DeviceIdentity",lambda **kwargs:kwargs,create=True):
            with self.assertRaisesRegex(SessionBlocked,"session_restore_failed"):await self.restore(data)
        self.assertFalse(created[0].ready)
    async def test_cancelled_initialization_is_closed(self):
        data=await self.save();entered=asyncio.Event();closed=asyncio.Event()
        class PendingSigner:
            MAX_STATE=OfflineSigner.MAX_STATE
            def __init__(self,*args):pass
            async def initialize(self):entered.set();await asyncio.Future()
            async def close(self):closed.set()
        with patch("findmy_home.owned_session.OfflineSigner",PendingSigner):
            task=asyncio.create_task(self.restore(data));await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertTrue(closed.is_set())

    async def test_snapshot_serialization_runs_off_event_loop(self):
        import threading
        seen=[];original=self.account.to_json
        def serialize():seen.append(threading.get_ident());return original()
        self.account.to_json=serialize
        await self.save()
        self.assertNotEqual(seen,[threading.get_ident()])
    async def test_duplicate_json_nonfinite_values_and_bad_encoding_are_refused(self):
        for plain in (b'{"version":1,"version":1}',b'{"expires_at":NaN}',b'not-json'):
            nonce=b"synthetic123"
            data=_MAGIC+nonce+AESGCM(self.key).encrypt(nonce,plain,_MAGIC)
            with self.assertRaises(SessionBlocked):await self.restore(data)

    async def test_snapshot_limits_service_tokens_and_requires_reporting_token(self):
        mobile=self.account.state["login"]["data"]["mobileme_data"]
        mobile["unrelated-service"]={"token":"PRIVATE_UNRELATED"}
        mobile["tokens"]["unrelatedAppleToken"]="PRIVATE_UNRELATED"
        envelope=self.decrypt(await self.save())
        saved=envelope["state"]["login"]["data"]["mobileme_data"]
        self.assertEqual(set(saved),{"tokens"})
        self.assertEqual(set(saved["tokens"]),{"searchPartyToken"})
        saved["tokens"]["unrelatedAppleToken"]="PRIVATE_UNRELATED"
        with self.assertRaisesRegex(SessionBlocked,"session_credentials_forbidden"):
            await self.restore(self.encrypt(envelope))
        mobile["tokens"].pop("searchPartyToken")
        with self.assertRaisesRegex(SessionBlocked,"reauthentication_required"):await self.save()

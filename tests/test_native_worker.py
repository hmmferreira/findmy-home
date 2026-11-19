"""Real process + Linux boundary tests over synthetic native implementation."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from findmy_home.controlled_provisioning import ProvisioningBlocked
from findmy_home.native_worker import IsolatedNativeWorker,ProcessOfflineSigner,_NativeChannel,_decode,_encode
from findmy_home.offline_signer import SignerBlocked

FIXTURE=Path(__file__).with_name("fixtures")/"native_worker_fixture.py"

class NativeWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.private=Path(self.tmp.name)/"private-sentinel"
        self.private.write_bytes(b"SYNTHETIC_PARENT_PRIVATE")
        self.write=Path(self.tmp.name)/"forbidden-write"
        self.artifact=json.dumps({"private_path":str(self.private),"write_path":str(self.write)}).encode()
        self.library=Path(self.tmp.name)/"synthetic-lib";self.library.write_bytes(self.artifact)
        self.digest=hashlib.sha256(self.artifact).hexdigest()
        self.patch=patch("findmy_home.native_worker._WORKER_SCRIPT",FIXTURE)
        self.patch.start();self.workers=[]
    async def asyncTearDown(self):
        for worker in self.workers:await worker.close()
        self.patch.stop();self.tmp.cleanup()
    async def prepare(self):
        worker=IsolatedNativeWorker();self.workers.append(worker)
        with patch.dict(os.environ,{"FINDMY_SYNTHETIC_PARENT_SECRET":"PRIVATE_ENV"}):
            identity=await worker.prepare(self.artifact)
        self.assertEqual(identity["X-Mme-Device-Id"],"SYNTHETIC-UUID")
        return worker
    async def test_real_boundary_blocks_files_parent_visibility_network_exec_and_inherited_env(self):
        worker=await self.prepare()
        self.assertFalse(self.write.exists())
        self.assertEqual(await worker.begin(b"SYNTHETIC_SPIM"),b"SYNTHETIC_CPIM")
        self.assertEqual(await worker.finish(b"SYNTHETIC_PTM",b"SYNTHETIC_TK"),b"SYNTHETIC_STATE_0")
        await worker.close()
        self.assertIsNotNone(worker._channel._process.returncode)
    async def test_explicit_identity_is_shared_by_provisioning_headers_and_native_config(self):
        import base64
        identity={"uid":"synthetic-local-uuid","devid":"synthetic-device-uuid","client_info":"Synthetic unified client"}
        artifact=json.loads(self.artifact);artifact["expected_identity"]=identity
        worker=IsolatedNativeWorker(**identity);self.workers.append(worker)
        headers=await worker.prepare(json.dumps(artifact).encode())
        self.assertEqual(headers,{"X-Mme-Device-Id":identity["devid"].upper(),
            "X-Apple-I-MD-LU":base64.b64encode(identity["uid"].encode()).decode(),
            "X-MMe-Client-Info":identity["client_info"]})
    async def test_cancel_hung_native_operation_kills_and_reaps_process(self):
        worker=await self.prepare();task=asyncio.create_task(worker.begin(b"hang"))
        await asyncio.sleep(.03);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNotNone(worker._channel._process.returncode)
    async def test_native_error_is_generic_and_process_reaped(self):
        worker=await self.prepare()
        with self.assertRaises(ProvisioningBlocked) as caught:await worker.begin(b"fail")
        self.assertEqual(str(caught.exception),"native_worker_failed")
        self.assertIsNotNone(worker._channel._process.returncode)
    async def test_process_signer_updates_snapshot_and_closes(self):
        signer=ProcessOfflineSigner(self.library,b"SYNTHETIC_SAVED_STATE",self.digest);self.workers.append(signer)
        await signer.initialize()
        self.assertTrue(signer.ready);self.assertEqual(signer.snapshot(),b"SYNTHETIC_STATE_0")
        self.assertEqual((await signer.headers())["X-Apple-I-MD"],"SYNTHETIC_OTP_1")
        self.assertEqual(signer.snapshot(),b"SYNTHETIC_STATE_1")
        self.assertIsNone(signer._state);self.assertNotIn("SYNTHETIC",repr(signer))
        await signer.close();self.assertFalse(signer.ready)
        with self.assertRaises(SignerBlocked):signer.snapshot()
        self.assertIsNotNone(signer._channel._process.returncode)
    async def test_process_signer_tampered_artifact_never_starts_worker(self):
        self.library.write_bytes(b"tampered")
        signer=ProcessOfflineSigner(self.library,b"SYNTHETIC_SAVED_STATE",self.digest);self.workers.append(signer)
        with self.assertRaises(SignerBlocked):await signer.initialize()
        self.assertIsNone(signer._channel._process)
    async def test_cancel_during_spawn_acquires_and_reaps_late_child(self):
        real=asyncio.create_subprocess_exec;entered=asyncio.Event()
        async def delayed_spawn(*args,**kwargs):
            entered.set();await asyncio.sleep(.03)
            return await real(*args,**kwargs)
        worker=IsolatedNativeWorker();self.workers.append(worker)
        with patch("findmy_home.native_worker.asyncio.create_subprocess_exec",side_effect=delayed_spawn):
            task=asyncio.create_task(worker.prepare(self.artifact))
            await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNotNone(worker._channel._process.returncode)
    async def test_spawn_failure_closes_both_control_pipe_descriptors(self):
        real_pipe=os.pipe;created=[]
        def record_pipe():
            pair=real_pipe();created.extend(pair);return pair
        worker=IsolatedNativeWorker();self.workers.append(worker)
        with patch("findmy_home.native_worker.os.pipe",side_effect=record_pipe),patch(
                "findmy_home.native_worker.asyncio.create_subprocess_exec",side_effect=OSError("PRIVATE_SPAWN_PATH")):
            with self.assertRaises(ProvisioningBlocked) as caught:await worker.prepare(self.artifact)
        self.assertEqual(str(caught.exception),"native_worker_failed")
        for fd in created:
            with self.assertRaises(OSError):os.fstat(fd)
    async def test_repeated_close_does_not_signal_reaped_pid(self):
        worker=await self.prepare();await worker.close()
        with patch("findmy_home.native_worker.os.killpg",side_effect=AssertionError("reaped PID signalled")):
            await worker.close()
    async def test_missing_boundary_fails_before_native_input(self):
        script=Path(self.tmp.name)/"unsupported.py"
        script.write_text('import os,struct,sys,json\nf=os.fdopen(int(sys.argv[1]),"wb",buffering=0)\nb=json.dumps({"ok":False,"error":"worker_boundary_unavailable"}).encode()\nf.write(struct.pack("!I",len(b))+b)\n')
        worker=IsolatedNativeWorker();self.workers.append(worker)
        with patch("findmy_home.native_worker._WORKER_SCRIPT",script):
            with self.assertRaises(ProvisioningBlocked) as caught:await worker.prepare(self.artifact)
        self.assertEqual(str(caught.exception),"worker_boundary_unavailable")
        self.assertIsNotNone(worker._channel._process.returncode)
    async def test_malformed_or_oversized_response_kills_worker(self):
        for payload in (b"not-json",None):
            script=Path(self.tmp.name)/"malformed.py"
            prefix=b"\\x7f\\xff\\xff\\xff" if payload is None else b""
            script.write_text('import os,struct,sys,json\nf=os.fdopen(int(sys.argv[1]),"wb",buffering=0)\nb=json.dumps({"ok":True,"ready":True,"boundary":"landlock3-seccomp-v1"}).encode()\nf.write(struct.pack("!I",len(b))+b)\nsys.stdin.buffer.read(4)\n'+('f.write(b"\\x7f\\xff\\xff\\xff")\n' if payload is None else 'b=b"not-json"\nf.write(struct.pack("!I",len(b))+b)\n'))
            worker=IsolatedNativeWorker();self.workers.append(worker)
            with patch("findmy_home.native_worker._WORKER_SCRIPT",script):
                with self.assertRaises(ProvisioningBlocked):await worker.prepare(self.artifact)
            self.assertIsNotNone(worker._channel._process.returncode)
    async def test_invalid_order_and_busy_snapshot_are_refused(self):
        worker=IsolatedNativeWorker();self.workers.append(worker)
        with self.assertRaises(ProvisioningBlocked):await worker.begin(b"spim")
        signer=ProcessOfflineSigner(self.library,b"SYNTHETIC_STATE",self.digest);self.workers.append(signer)
        await signer.initialize();signer._busy=True
        with self.assertRaises(SignerBlocked) as caught:signer.snapshot()
        self.assertEqual(str(caught.exception),"signer_busy")
    def test_partial_or_injected_identity_is_refused(self):
        for kwargs in ({"uid":"uid"},{"uid":"uid","devid":"device"},
                       {"uid":"uid","devid":"device","client_info":"bad\r\nheader"}):
            with self.assertRaises(ProvisioningBlocked):IsolatedNativeWorker(**kwargs)
    def test_binary_ipc_field_validation(self):
        for value in (None,"!", "", "AA=="):
            with self.assertRaises(ProvisioningBlocked):_decode(value,0)
        with self.assertRaises(ProvisioningBlocked):_encode(b"xx",1)
        with self.assertRaises(ProvisioningBlocked):_encode("PRIVATE",100)

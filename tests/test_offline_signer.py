"""Offline artifact/provisioning guards; synthetic state and mock native engine."""
import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from findmy_home.offline_signer import OfflineSigner,SignerBlocked,NoProvisioning,_build_engine

class OfflineSignerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"library.bin"
        self.path.write_bytes(b"synthetic-reviewed-library")
        self.digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.signer=OfflineSigner(self.path,b"PRIVATE_SYNTHETIC_STATE",self.digest)
        self.engine=SimpleNamespace(is_provisioned=True,get_data=Mock(return_value={"X-Apple-I-MD":"synthetic-otp","X-Apple-I-MD-M":"synthetic-machine","UNEXPECTED":"PRIVATE"}),
            save_provisioning=lambda stream:stream.write(b"PRIVATE_SYNTHETIC_UPDATED_STATE"))
    async def asyncTearDown(self):await self.signer.close();self.tmp.cleanup()
    async def ready(self):
        with patch("findmy_home.offline_signer._build_engine",return_value=self.engine) as build:
            await self.signer.initialize()
        build.assert_called_once_with(b"PRIVATE_SYNTHETIC_STATE",b"synthetic-reviewed-library")
    async def test_verified_artifact_and_existing_state_can_sign_without_network_interface(self):
        await self.ready()
        self.assertEqual(await self.signer.headers(),{"X-Apple-I-MD":"synthetic-otp","X-Apple-I-MD-M":"synthetic-machine"})
        self.assertNotIn("PRIVATE",repr(self.signer))
        self.assertEqual(self.signer.snapshot(),b"PRIVATE_SYNTHETIC_UPDATED_STATE")
        self.assertIsNone(self.signer._state)
    async def test_missing_or_changed_artifact_is_not_downloaded_or_executed(self):
        for kind in ("missing","modified","symlink","directory"):
            with self.subTest(kind=kind):
                path=Path(self.tmp.name)/kind
                if kind=="modified":path.write_bytes(b"unexpected")
                elif kind=="symlink":path.symlink_to(self.path)
                elif kind=="directory":path.mkdir()
                signer=OfflineSigner(path,b"state",self.digest)
                with patch("findmy_home.offline_signer._build_engine") as build:
                    with self.assertRaises(SignerBlocked):await signer.initialize()
                build.assert_not_called();await signer.close()
    async def test_unprovisioned_state_never_requests_automatic_provisioning(self):
        self.engine.is_provisioned=False
        with patch("findmy_home.offline_signer._build_engine",return_value=self.engine):
            with self.assertRaises(SignerBlocked) as caught:await self.signer.initialize()
        self.assertEqual(str(caught.exception),"provisioning_required")
        self.assertFalse(self.signer.ready)
        self.engine.get_data.assert_not_called()
    async def test_lost_provisioning_stops_before_get_data(self):
        await self.ready();self.engine.is_provisioned=False
        with self.assertRaises(SignerBlocked):await self.signer.headers()
        self.engine.get_data.assert_not_called()
    async def test_native_failures_are_redacted(self):
        await self.ready();self.engine.get_data.side_effect=RuntimeError("PRIVATE_NATIVE_STATE")
        with self.assertRaises(SignerBlocked) as caught:await self.signer.headers()
        self.assertEqual(str(caught.exception),"signing_failed")
    async def test_closed_signer_cannot_be_reused(self):
        await self.ready();await self.signer.close()
        self.assertFalse(self.signer.ready)
        self.assertIsNone(self.signer._engine)
        with self.assertRaises(SignerBlocked):await self.signer.headers()
    async def test_native_work_is_off_the_event_loop(self):
        import threading
        await self.ready();threads=[]
        def native():
            threads.append(threading.get_ident())
            return {"X-Apple-I-MD":"otp","X-Apple-I-MD-M":"machine"}
        self.engine.get_data.side_effect=native
        await self.signer.headers()
        self.assertNotEqual(threads,[threading.get_ident()])
    def test_empty_state_or_unreviewed_digest_is_rejected(self):
        for state,digest in ((b"",self.digest),(None,self.digest),(b"state",None),(b"state","unknown")):
            with self.assertRaises(SignerBlocked):OfflineSigner(self.path,state,digest)
    def test_native_factory_has_no_download_or_provisioning_fallback(self):
        fake=SimpleNamespace()
        with patch("anisette._ani_provider.AnisetteProvider.load",return_value=fake) as load,patch("anisette.Anisette.load",side_effect=AssertionError("Unsafe high-level loader")) as unsafe:
            engine=_build_engine(b"state",b"library")
        self.assertIs(engine._ani_provider,fake)
        self.assertTrue(all(isinstance(value,BytesIO) for value in load.call_args.args))
        with self.assertRaises(SignerBlocked):load.call_args.kwargs["fs_fallback"]()
        self.assertIsInstance(fake._provisioning_session,NoProvisioning)
        with self.assertRaises(SignerBlocked):fake._provisioning_session.provision(-2)
        unsafe.assert_not_called()

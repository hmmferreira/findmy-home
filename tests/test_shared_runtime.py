import asyncio
import base64
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from retrace.storage import Store
from retrace.shared_runtime import (RuntimeBlocked,SigningIdentityStore,read_options,
    configure_runtime,owned_session_available,compose_runtime,SIGNING_MANIFEST)
from retrace.owned_session import SessionBlocked

IDENTITY={key:'synthetic' for key in ('model','os_name','os_version','os_build','cfnetwork','darwin')}
DIGEST='a'*64
IDS={'uid':'00000000-0000-4000-8000-000000000001','devid':'00000000-0000-4000-8000-000000000002'}

class StartupTests(unittest.TestCase):
    def test_validated_options_are_handed_off_privately_before_privilege_drop(self):
        from retrace.shared_runtime import publish_runtime_options
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'private';root.mkdir(mode=0o700)
            source=Path(tmp)/'supervisor-options.json'
            source.write_text(json.dumps({'runtime_mode':'shared','private_evaluation':True}))
            source.chmod(0o600)
            options=read_options(source)
            path=publish_runtime_options(root,options)
            source.unlink()  # web process must not depend on Supervisor file access.
            self.assertEqual(read_options(path),options)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(root.stat().st_mode&0o777,0o700)

    def test_options_are_explicit_and_default_preserves_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'options.json'
            self.assertEqual(read_options(path)['runtime_mode'],'legacy')
            path.write_text(json.dumps({'runtime_mode':'shared','create_new_identity':True}))
            self.assertEqual(read_options(path)['runtime_mode'],'shared')
            for value in ({'runtime_mode':'guess'},{'create_new_identity':'true'},{'install_reviewed_component':'true'},{'private_evaluation':'true'},{'digest':'a'*64},{'shared_artifact_id':'../../file'}):
                path.write_text(json.dumps(value))
                with self.assertRaises(RuntimeBlocked):read_options(path)
            path.write_text('{"runtime_mode":"legacy","runtime_mode":"shared"}')
            with self.assertRaises(RuntimeBlocked):read_options(path)
    def test_private_evaluation_environment_only_comes_from_shared_checked_options(self):
        with patch.dict(os.environ,{},clear=False),patch('retrace.shared_runtime.require_shared_backend'):
            configure_runtime({'runtime_mode':'shared','private_evaluation':True})
            self.assertEqual(os.environ['RETRACE_PRIVATE_EVALUATION'],'1')
            configure_runtime({'runtime_mode':'shared','private_evaluation':False})
            self.assertEqual(os.environ['RETRACE_PRIVATE_EVALUATION'],'0')
            configure_runtime({'runtime_mode':'legacy','private_evaluation':True})
            self.assertEqual(os.environ['RETRACE_PRIVATE_EVALUATION'],'0')

    def test_shared_mode_never_falls_back_if_image_marker_is_missing(self):
        with patch('retrace.shared_runtime.require_shared_backend',side_effect=RuntimeBlocked('shared_image_required')):
            with self.assertRaisesRegex(RuntimeBlocked,'shared_image_required'):
                configure_runtime({'runtime_mode':'shared'})
    def test_shared_readiness_never_uses_legacy_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'account.json').write_text('{}')
            self.assertFalse(owned_session_available(root))
            (root/'owned-session.json').symlink_to(root/'missing')
            self.assertTrue(owned_session_available(root))

class SigningStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.store=SigningIdentityStore(self.root,DIGEST)
    def tearDown(self):self.tmp.cleanup()
    def test_encrypted_machine_state_survives_restart_without_account_credentials(self):
        self.store.save(b'synthetic-private-machine-state','b'*32,IDENTITY,IDS)
        self.assertEqual(SigningIdentityStore(self.root,DIGEST).load(),(b'synthetic-private-machine-state','b'*32,IDENTITY,IDS))
        self.assertTrue(self.store.exists())
        for path in self.root.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertNotIn(b'synthetic-private-machine-state',path.read_bytes())
    def test_corruption_and_policy_change_do_not_regenerate_identity(self):
        self.store.save(b'synthetic-state','b'*32,IDENTITY,IDS)
        with self.assertRaises(SessionBlocked):SigningIdentityStore(self.root,'c'*64).load()
        manifest=json.loads((self.root/SIGNING_MANIFEST).read_text())
        data=self.root/('signing-'+manifest['generation']+'.enc')
        value=data.read_bytes();data.write_bytes(value[:-1]+bytes([value[-1]^1]))
        with self.assertRaises(SessionBlocked):self.store.load()
        self.assertTrue(self.store.exists())
    def test_missing_key_and_symlink_fail_closed(self):
        self.store.save(b'synthetic-state','b'*32,IDENTITY,IDS)
        manifest=json.loads((self.root/SIGNING_MANIFEST).read_text())
        key=self.root/('signing-'+manifest['generation']+'.key');key.unlink()
        key.symlink_to(self.root/'missing')
        with self.assertRaises(SessionBlocked):self.store.load()
    def test_manifest_failure_preserves_prior_generation(self):
        self.store.save(b'old-state','b'*32,IDENTITY,IDS)
        with patch('retrace.shared_runtime.atomic_json',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):self.store.save(b'new-state','d'*32,IDENTITY,IDS)
        self.assertEqual(self.store.load(),(b'old-state','b'*32,IDENTITY,IDS))

class CompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name))
        self.boundary_patch=patch('retrace.native_worker.verify_native_boundary',new=AsyncMock())
        self.boundary=self.boundary_patch.start()
    async def asyncTearDown(self):self.boundary_patch.stop();self.tmp.cleanup()
    async def test_pending_artifact_review_blocks_before_credentials_or_provisioning(self):
        from retrace.artifact_policy import ArtifactBlocked
        with patch('retrace.shared_runtime.require_shared_backend'),patch('retrace.artifact_policy.reviewed_artifact',side_effect=ArtifactBlocked('artifact_review_required')):
            with self.assertRaisesRegex(ArtifactBlocked,'artifact_review_required'):
                await compose_runtime(self.store,{'shared_artifact_id':'applemusic-arm64-v8a','create_new_identity':True})
        self.assertFalse((self.store.root/SIGNING_MANIFEST).exists())
    async def test_unsupported_boundary_stops_before_component_install_or_credentials(self):
        from retrace.offline_signer import SignerBlocked
        self.boundary.side_effect=SignerBlocked('worker_boundary_unavailable')
        with patch('retrace.shared_runtime.require_shared_backend'),patch('retrace.artifact_policy.reviewed_artifact',return_value=SimpleNamespace(expected_sha256=DIGEST)),patch('retrace.component_installer.ensure_component',new=AsyncMock()) as install:
            with self.assertRaisesRegex(SignerBlocked,'worker_boundary_unavailable'):
                await compose_runtime(self.store,{'shared_artifact_id':'applemusic-arm64-v8a','create_new_identity':True,'install_reviewed_component':True})
            install.assert_not_awaited()
        self.assertFalse((self.store.root/SIGNING_MANIFEST).exists())

    async def test_missing_identity_requires_explicit_consent_and_corrupt_identity_never_reprovisions(self):
        provision=AsyncMock()
        with patch('retrace.shared_runtime.require_shared_backend'),patch('retrace.artifact_policy.reviewed_artifact',return_value=SimpleNamespace(expected_sha256=DIGEST)),patch('retrace.artifact_policy.verify_artifact',new=AsyncMock()),patch('retrace.controlled_provisioning.provision_new_identity',new=provision):
            worker,bridge=await compose_runtime(self.store,{'shared_artifact_id':'applemusic-arm64-v8a','create_new_identity':False})
            try:
                with self.assertRaisesRegex(RuntimeBlocked,'explicit_new_identity_required'):await worker.account_factory()
                provision.assert_not_awaited()
                (self.store.root/SIGNING_MANIFEST).write_text('{}');(self.store.root/SIGNING_MANIFEST).chmod(0o600)
                with self.assertRaises(SessionBlocked):await worker.account_factory()
                provision.assert_not_awaited()
            finally:await bridge.close()

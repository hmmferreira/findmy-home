import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
from findmy_home.private_session_store import PrivateSessionStore,restore_reporting_account,session_available
from findmy_home.owned_session import SessionBlocked
from findmy_home.storage import atomic_json,read_json

class PrivateSessionStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=PrivateSessionStore(self.root,library=self.root/'ani_libs.bin',expected_sha256='a'*64)
    async def test_generation_restores_matching_key_after_restart(self):
        keys=[]
        async def snapshot(account,**kw):keys.append(kw['encryption_key']);return b'private-ciphertext'
        with patch('findmy_home.private_session_store.snapshot_account',side_effect=snapshot):await self.store.save(object())
        manifest=read_json(self.root/'owned-session.json')
        self.assertNotIn('private-ciphertext',json.dumps(manifest))
        for suffix in ('key','enc'):self.assertEqual((self.root/('session-'+manifest['generation']+'.'+suffix)).stat().st_mode&0o777,0o600)
        restored=object()
        with patch('findmy_home.private_session_store.restore_account',new=AsyncMock(return_value=restored)) as restore:
            self.assertIs(await restore_reporting_account(self.root),restored)
            self.assertEqual(restore.call_args.kwargs['encryption_key'],keys[0])
            self.assertEqual(restore.call_args.args,(b'private-ciphertext',))
        self.assertTrue(session_available(self.root))
    async def test_failed_manifest_keeps_previous_generation(self):
        with patch('findmy_home.private_session_store.snapshot_account',new=AsyncMock(return_value=b'cipher')):
            await self.store.save(object());before=read_json(self.root/'owned-session.json')
            with patch('findmy_home.private_session_store.atomic_json',side_effect=OSError('synthetic')):
                with self.assertRaises(OSError):await self.store.save(object())
        self.assertEqual(read_json(self.root/'owned-session.json'),before)
        self.assertEqual(len(list(self.root.glob('session-*.key'))),1)
    async def test_owned_corruption_never_uses_legacy_account(self):
        atomic_json(self.root/'account.json',{'legacy':True})
        atomic_json(self.root/'owned-session.json',{'version':1,'generation':'../escape'})
        with patch('findmy_home.apple.ReportingAccount.from_json') as legacy:
            with self.assertRaises(SessionBlocked):await restore_reporting_account(self.root)
            legacy.assert_not_called()
    async def test_missing_owned_key_and_symlink_fail_closed(self):
        with patch('findmy_home.private_session_store.snapshot_account',new=AsyncMock(return_value=b'cipher')):await self.store.save(object())
        manifest=read_json(self.root/'owned-session.json');key=self.root/('session-'+manifest['generation']+'.key')
        key.unlink();key.symlink_to(self.root/'missing')
        with self.assertRaises(SessionBlocked):await restore_reporting_account(self.root)
    async def test_existing_legacy_mode_unchanged(self):
        self.assertFalse(session_available(self.root))
        atomic_json(self.root/'account.json',{'fixture':True})
        with patch('findmy_home.apple.ReportingAccount.from_json',return_value='legacy') as legacy:
            self.assertEqual(await restore_reporting_account(self.root),'legacy')
            legacy.assert_called_once()
    async def test_expired_owned_session_is_not_replaced_by_legacy(self):
        with patch('findmy_home.private_session_store.snapshot_account',new=AsyncMock(return_value=b'cipher')):await self.store.save(object())
        atomic_json(self.root/'account.json',{'legacy':True})
        with patch('findmy_home.private_session_store.restore_account',new=AsyncMock(side_effect=SessionBlocked('session_expired'))),patch('findmy_home.apple.ReportingAccount.from_json') as legacy:
            with self.assertRaises(SessionBlocked):await restore_reporting_account(self.root)
            legacy.assert_not_called()

    async def test_published_manifest_survives_post_replace_fsync_error(self):
        def publish_then_fail(path,value):
            atomic_json(path,value)
            raise OSError("synthetic post-replace directory fsync failure")
        with patch('findmy_home.private_session_store.snapshot_account',new=AsyncMock(return_value=b'cipher')),patch('findmy_home.private_session_store.atomic_json',side_effect=publish_then_fail):
            with self.assertRaises(OSError):await self.store.save(object())
        manifest=read_json(self.root/'owned-session.json')
        for suffix in ('key','enc'):self.assertTrue((self.root/('session-'+manifest['generation']+'.'+suffix)).exists())
        with patch('findmy_home.private_session_store.restore_account',new=AsyncMock(return_value='restored')):
            self.assertEqual(await restore_reporting_account(self.root),'restored')

    async def test_owner_only_permissions_required_for_every_session_part(self):
        with patch('findmy_home.private_session_store.snapshot_account',new=AsyncMock(return_value=b'cipher')):await self.store.save(object())
        manifest=read_json(self.root/'owned-session.json')
        paths=[self.root/'owned-session.json']+[self.root/('session-'+manifest['generation']+'.'+suffix) for suffix in ('key','enc')]
        for path in paths:
            with self.subTest(part=path.suffix):
                path.chmod(0o644)
                with self.assertRaises(SessionBlocked):await restore_reporting_account(self.root)
                path.chmod(0o600)

    async def test_duplicate_manifest_keys_rejected_before_restore(self):
        path=self.root/'owned-session.json';path.write_text('{"version":1,"version":1}')
        path.chmod(0o600)
        with patch('findmy_home.private_session_store.restore_account',new=AsyncMock()) as restore:
            with self.assertRaises(SessionBlocked):await restore_reporting_account(self.root)
            restore.assert_not_awaited()

    async def test_symlink_data_root_rejected(self):
        link=self.root/'alias';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(SessionBlocked):await restore_reporting_account(link)

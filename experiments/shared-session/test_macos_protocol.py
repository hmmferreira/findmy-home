"""Actual pinned SDK adapter tests with synthetic machine/session/native data."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from findmy import LoginState
from retrace.macos_identity import new_machine
from retrace.macos_worker import MacSigner
from retrace.macos_provider import account_for
from retrace.macos_artifact import LIBRARY_SHA
from retrace.owned_session import snapshot_account,restore_account

class MacProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mac_id_cloudkit_uuid_headers_and_password_free_restore(self):
        machine=new_machine();machine['saved']={'adi-000001F5.pb':base64.b64encode(b'synthetic state').decode()};machine['routing']=42
        async def initialize(signer):signer._initialized=True
        async def headers(signer):return {'X-Apple-I-MD':'b3Rw','X-Apple-I-MD-M':'bWlk','X-Apple-I-MD-RINFO':'42'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(MacSigner,'initialize',initialize),patch.object(MacSigner,'headers',headers):
            library=Path(tmp)/'coreadi.bin'
            signer=MacSigner(library,json.dumps(machine).encode(),LIBRARY_SHA);await signer.initialize()
            account=await account_for(signer)
            restored=None
            try:
                self.assertEqual(account._devid,machine['devid'])
                self.assertEqual(account.device_uuid,str(uuid.UUID(machine['host_uuid'])).upper())
                result=await account.get_anisette_headers()
                self.assertEqual(result['X-Mme-Device-Id'],machine['devid'])
                self.assertEqual(result['X-Apple-I-MD-RINFO'],'42')
                self.assertEqual(base64.b64decode(result['X-Apple-I-MD-LU']).decode(),machine['uid'])
                account._username='synthetic@example.invalid';account._password='SYNTHETIC_PASSWORD'
                account._set_login_state(LoginState.LOGGED_IN,{'dsid':'synthetic-dsid','adsid':'synthetic-adsid',
                    'idms_pet':'SYNTHETIC_PET','mobileme_data':{'tokens':{'searchPartyToken':'synthetic-token'}}})
                encrypted=await snapshot_account(account,encryption_key=b'k'*32,expires_at=2000,now=1000)
                self.assertNotIn(b'SYNTHETIC_PASSWORD',encrypted)
                restored=await restore_account(encrypted,encryption_key=b'k'*32,library=library,
                    expected_sha256=LIBRARY_SHA,now=1001,signer_factory=MacSigner)
                self.assertEqual(restored._devid,machine['devid'])
                self.assertEqual(restored.device_uuid,account.device_uuid)
                self.assertIsNone(restored._password)
                self.assertNotIn('idms_pet',restored._login_state_data)
                self.assertEqual(restored._http.profile,'account')
            finally:
                await account.close()
                if restored:await restored.close()

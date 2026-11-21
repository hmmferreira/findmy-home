import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock,patch
from retrace.apple_transport import OwnedHttpSession,TransportBlocked,validate_destination
from retrace.macos_artifact import URL,extract,OFFSET,LENGTH

class MacArtifactTests(unittest.IsolatedAsyncioTestCase):
    async def test_artifact_profile_cannot_send_account_credentials(self):
        http=OwnedHttpSession(profile='mac_artifact')
        try:
            with patch.object(http,'_session',new_callable=AsyncMock) as session:
                for options in ({'auth':('synthetic-user','synthetic-password')},{'headers':{'Authorization':'synthetic-token'}},{'json':{'password':'synthetic'}}):
                    with self.assertRaises(TransportBlocked):await http.request('GET',URL,**options)
                session.assert_not_awaited()
        finally:await http.close()
    def test_only_fixed_apple_url_and_method_are_allowed(self):
        self.assertEqual(validate_destination('mac_artifact','GET',URL),'secure-appldnld.apple.com')
        for method,url in [('POST',URL),('GET',URL+'?redirect=1'),('GET','https://example.com/file')]:
            with self.assertRaises(TransportBlocked):validate_destination('mac_artifact',method,url)
    def test_unknown_payload_never_reaches_extraction(self):
        with self.assertRaises(TransportBlocked):extract(b'unknown fixture')
    def test_pinned_engine_files_and_license_are_preserved(self):
        root=Path(__file__).resolve().parents[1]/'retrace/rootfs/app/retrace/mac_engine'
        pins=json.loads((root/'PROVENANCE.json').read_text())
        self.assertEqual(pins['revision'],'595d39810639d750715babc30b063d4ac8f2c437')
        for name,digest in pins['files'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
        self.assertIn('GNU GENERAL PUBLIC LICENSE',(root/'LICENSE').read_text())

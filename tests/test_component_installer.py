"""All vendor/archive/transport content is synthetic; no network access."""
import asyncio
from dataclasses import replace
import hashlib
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
import zipfile
from findmy_home import artifact_policy
from findmy_home.artifact_policy import ArtifactBlocked,reviewed_artifact
from findmy_home.apple_transport import OwnedHttpSession,TransportBlocked,ARTIFACT_URL,validate_destination
from findmy_home.component_installer import ensure_component,MAX_APK

class Fixture:
    def __init__(self):
        header=bytearray(40);header[:6]=b'\x7fELF\x02\x01';header[18:20]=b'\xb7\x00'
        elf=bytes(header)+b'synthetic-ELF-test-only'
        members={name:elf for name in ('lib/arm64-v8a/libCoreADI.so','lib/arm64-v8a/libstoreservicescore.so')}
        source=BytesIO()
        with zipfile.ZipFile(source,'w') as archive:
            for name,value in members.items():archive.writestr(name,value)
            archive.writestr('../../unrelated-account-looking-file',b'synthetic-not-included')
        self.apk=source.getvalue()
        manifest=json.loads(artifact_policy._MANIFEST.read_text());entry=manifest['artifacts'][0]
        entry.update(review_status='approved',host_architectures=['amd64'])
        entry['source'].update(version='SYNTHETIC-TEST-ONLY',sha256=hashlib.sha256(self.apk).hexdigest())
        entry['bundle']['member_sha256']={name:hashlib.sha256(value).hexdigest() for name,value in members.items()}
        spec=importlib.util.spec_from_file_location('installer_review_recipe',Path(__file__).resolve().parents[1]/'tools/review-native-artifact.py')
        recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
        self.bundle=recipe.bundle_from_apk(self.apk,entry)
        entry['bundle']['sha256']=hashlib.sha256(self.bundle).hexdigest()
        entry['review'].update(id='SYNTHETIC-TEST-REVIEW',date='2026-11-20',evidence='synthetic-fixture-only')
        entry['license'].update(native_review='approved',redistribution='local-use-only')
        self.manifest=manifest
    def policy(self):
        with patch('findmy_home.artifact_policy._load_manifest',return_value=self.manifest):
            return reviewed_artifact('applemusic-arm64-v8a',host_architecture='amd64')

class FakeDownload(OwnedHttpSession):
    def __init__(self,data):super().__init__(profile='artifact');self.data=data;self.calls=[]
    async def artifact_chunks(self,url,*,max_bytes):
        self.calls.append((url,max_bytes))
        for offset in range(0,len(self.data),31):yield self.data[offset:offset+31]

class ComponentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.fixture=Fixture();self.policy=self.fixture.policy()
    async def asyncTearDown(self):self.tmp.cleanup()
    async def test_explicit_install_matches_independent_recipe_private_permissions_and_reuses(self):
        http=FakeDownload(self.fixture.apk)
        result=await ensure_component(self.root,self.policy,install=True,transport=http)
        destination=self.root/'owned-libs.bin'
        self.assertEqual(result,{'installed':True});self.assertEqual(destination.read_bytes(),self.fixture.bundle)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode),0o600)
        self.assertEqual(http.calls,[(ARTIFACT_URL,MAX_APK)]);self.assertTrue(http._closed)
        self.assertFalse(list(self.root.glob('.component-*')))
        second=FakeDownload(b'never requested')
        self.assertEqual(await ensure_component(self.root,self.policy,install=True,transport=second),{'installed':False})
        self.assertFalse(second.calls);await second.close()
    async def test_missing_consent_and_forged_policy_do_not_download(self):
        for policy,install in ((self.policy,False),(replace(self.policy,_issuer=object()),True)):
            http=FakeDownload(self.fixture.apk)
            with self.assertRaises(ArtifactBlocked):await ensure_component(self.root,policy,install=install,transport=http)
            self.assertFalse(http.calls);await http.close()
        self.assertFalse(list(self.root.iterdir()))
    async def test_existing_invalid_or_symlink_is_not_overwritten_or_downloaded(self):
        target=self.root/'owned-libs.bin';target.write_bytes(b'existing-invalid')
        http=FakeDownload(self.fixture.apk)
        with self.assertRaises(ArtifactBlocked):await ensure_component(self.root,self.policy,install=True,transport=http)
        self.assertEqual(target.read_bytes(),b'existing-invalid');self.assertFalse(http.calls)
        target.unlink();target.symlink_to(self.root/'missing')
        with self.assertRaises(ArtifactBlocked):await ensure_component(self.root,self.policy,install=True,transport=http)
        self.assertTrue(target.is_symlink());self.assertFalse(http.calls);await http.close()
    async def test_full_source_hash_is_checked_before_zip_is_opened(self):
        http=FakeDownload(b'corrupt source')
        with patch('findmy_home.component_installer.zipfile.ZipFile',side_effect=AssertionError('must not open')) as open_zip:
            with self.assertRaisesRegex(ArtifactBlocked,'artifact_source_digest_mismatch'):
                await ensure_component(self.root,self.policy,install=True,transport=http)
            open_zip.assert_not_called()
        self.assertFalse(list(self.root.iterdir()));self.assertTrue(http._closed)
    async def test_member_and_final_bundle_hashes_are_both_required(self):
        for field in ('member','bundle'):
            entry=self.fixture.manifest['artifacts'][0]
            if field=='member':entry['bundle']['member_sha256']['lib/arm64-v8a/libCoreADI.so']='a'*64
            else:
                self.fixture=Fixture();entry=self.fixture.manifest['artifacts'][0];entry['bundle']['sha256']='b'*64
            http=FakeDownload(self.fixture.apk)
            with self.assertRaises(ArtifactBlocked):await ensure_component(self.root,self.fixture.policy(),install=True,transport=http)
            self.assertFalse(list(self.root.iterdir()));self.assertTrue(http._closed)
    async def test_duplicate_missing_and_wrong_architecture_members_are_rejected(self):
        for variant in ('duplicate','missing','architecture'):
            fixture=Fixture();original=zipfile.ZipFile(BytesIO(fixture.apk));output=BytesIO()
            target='lib/arm64-v8a/libCoreADI.so'
            with original,zipfile.ZipFile(output,'w') as changed:
                for info in original.infolist():
                    if variant=='missing' and info.filename==target:continue
                    value=original.read(info.filename)
                    if variant=='architecture' and info.filename==target:
                        value=value[:18]+b'\x3e\x00'+value[20:]
                        fixture.manifest['artifacts'][0]['bundle']['member_sha256'][target]=hashlib.sha256(value).hexdigest()
                    changed.writestr(info.filename,value)
                    if variant=='duplicate' and info.filename==target:
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter('ignore',UserWarning);changed.writestr(info.filename,value)
            fixture.apk=output.getvalue()
            fixture.manifest['artifacts'][0]['source']['sha256']=hashlib.sha256(fixture.apk).hexdigest()
            http=FakeDownload(fixture.apk)
            with self.subTest(variant=variant),self.assertRaises(ArtifactBlocked):
                await ensure_component(self.root,fixture.policy(),install=True,transport=http)
            self.assertFalse(list(self.root.iterdir()))

    async def test_destination_created_during_download_is_never_overwritten(self):
        root=self.root
        class RaceDownload(FakeDownload):
            async def artifact_chunks(self,url,*,max_bytes):
                yield self.data
                (root/'owned-libs.bin').write_bytes(b'competing-file')
        http=RaceDownload(self.fixture.apk)
        with self.assertRaisesRegex(ArtifactBlocked,'artifact_destination_changed'):
            await ensure_component(self.root,self.policy,install=True,transport=http)
        self.assertEqual((self.root/'owned-libs.bin').read_bytes(),b'competing-file')
        self.assertFalse(list(self.root.glob('.component-*')))

    async def test_cancellation_removes_partial_apk_and_never_publishes_bundle(self):
        entered=asyncio.Event()
        class WaitingDownload(FakeDownload):
            async def artifact_chunks(self,url,*,max_bytes):
                yield self.data[:10];entered.set();await asyncio.Event().wait()
        http=WaitingDownload(self.fixture.apk)
        task=asyncio.create_task(ensure_component(self.root,self.policy,install=True,transport=http))
        await asyncio.wait_for(entered.wait(),2);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(list(self.root.iterdir()));self.assertTrue(http._closed)
    async def test_oversized_stream_is_bounded_and_cleans_up(self):
        http=FakeDownload(self.fixture.apk)
        with patch('findmy_home.component_installer.MAX_APK',32):
            with self.assertRaisesRegex(ArtifactBlocked,'artifact_source_too_large'):
                await ensure_component(self.root,self.policy,install=True,transport=http)
        self.assertFalse(list(self.root.iterdir()))

class StreamingTests(unittest.IsolatedAsyncioTestCase):
    def response(self,*,status=200,headers=None,chunks=None):
        class Response:
            def __init__(self):self.status=status;self.headers=headers or {};self.content=self
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def iter_chunked(self,size):
                for chunk in chunks or [b'synthetic-vendor-bytes']:yield chunk
        return Response()
    async def run_stream(self,response,*,maximum=1024):
        http=OwnedHttpSession(profile='artifact');calls=[]
        class Session:
            def request(self,*args,**kwargs):calls.append((args,kwargs));return response
        try:
            with patch.object(http,'_session',new=AsyncMock(return_value=Session())):
                output=b''.join([chunk async for chunk in http.artifact_chunks(ARTIFACT_URL,max_bytes=maximum)])
            return output,calls
        finally:await http.close()
    async def test_fixed_get_stream_has_no_auth_body_redirect_proxy_or_decompression(self):
        body,calls=await self.run_stream(self.response())
        self.assertEqual(body,b'synthetic-vendor-bytes')
        args,kwargs=calls[0];self.assertEqual(args,('GET',ARTIFACT_URL))
        self.assertEqual(set(kwargs),{'allow_redirects','ssl','headers','auto_decompress'})
        self.assertFalse(kwargs['allow_redirects']);self.assertFalse(kwargs['auto_decompress'])
        self.assertEqual(kwargs['headers']['Accept-Encoding'],'identity')
        self.assertEqual(OwnedHttpSession.MAX_BODY,8*1024*1024)
    async def test_redirect_error_compressed_and_oversized_streams_are_rejected(self):
        for response in (self.response(status=307),self.response(status=401),
                         self.response(headers={'Content-Encoding':'gzip'}),
                         self.response(headers={'Content-Length':'999999'}),
                         self.response(chunks=[b'a'*1025])):
            with self.assertRaises(TransportBlocked):await self.run_stream(response)
    async def test_other_destinations_methods_and_credential_request_path_are_refused(self):
        for url in (ARTIFACT_URL+'?token=secret',ARTIFACT_URL.replace('https:','http:'),
                    ARTIFACT_URL.replace('apps.mzstatic.com','evil.invalid'),ARTIFACT_URL+'/'):
            with self.assertRaises(TransportBlocked):validate_destination('artifact','GET',url)
        with self.assertRaises(TransportBlocked):validate_destination('artifact','POST',ARTIFACT_URL)
        http=OwnedHttpSession(profile='artifact')
        try:
            with self.assertRaisesRegex(TransportBlocked,'artifact_stream_required'):
                await http.request('GET',ARTIFACT_URL,auth=('synthetic-user','synthetic-password'))
        finally:await http.close()

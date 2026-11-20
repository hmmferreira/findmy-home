"""Release policy tests; all approved entries and binary bytes are synthetic."""
import copy
from dataclasses import FrozenInstanceError,replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from retrace.artifact_policy import reviewed_artifact,verify_artifact,ArtifactBlocked,_MANIFEST

class ArtifactPolicyTests(unittest.IsolatedAsyncioTestCase):
    def manifest(self):
        value=json.loads(_MANIFEST.read_text());entry=value["artifacts"][0]
        entry.update(review_status="approved",host_architectures=["amd64"])
        entry["source"].update(version="SYNTHETIC-NOT-A-REAL-APPLE-RELEASE",sha256="a"*64)
        entry["bundle"].update(sha256=hashlib.sha256(b"synthetic-library").hexdigest())
        entry["bundle"]["member_sha256"]={name:"b"*64 for name in entry["bundle"]["member_sha256"]}
        entry["review"].update(id="SYNTHETIC-TEST-REVIEW",date="2026-11-19",evidence="synthetic-test-only")
        entry["license"].update(native_review="approved",redistribution="local-use-only")
        return value
    def selected(self,value=None,**kwargs):
        with patch("retrace.artifact_policy._load_manifest",return_value=value or self.manifest()):
            return reviewed_artifact("applemusic-arm64-v8a",host_architecture=kwargs.get("host_architecture","amd64"))
    def test_bundled_policy_requires_explicit_private_evaluation_context(self):
        with self.assertRaisesRegex(ArtifactBlocked,"artifact_review_required"):
            reviewed_artifact("applemusic-arm64-v8a",host_architecture="amd64")
    def test_private_evaluation_is_source_bound_and_does_not_claim_redistribution(self):
        policy=reviewed_artifact("applemusic-arm64-v8a",host_architecture="amd64",private_evaluation=True)
        self.assertEqual(policy.redistribution,"local-use-only")
        self.assertEqual(policy.expected_sha256,"1cc48641b9803e951eaf96439463e05790e5b14452155261dcc271cec53ad563")
        self.assertEqual(policy.source_version,"4.9.6.1447")
        with self.assertRaises(ArtifactBlocked):reviewed_artifact("applemusic-arm64-v8a",host_architecture="amd64",private_evaluation="yes")
        value=json.loads(_MANIFEST.read_text());value['artifacts'][0]['license']['redistribution']='permitted'
        with patch("retrace.artifact_policy._load_manifest",return_value=value),self.assertRaises(ArtifactBlocked):
            reviewed_artifact("applemusic-arm64-v8a",host_architecture="amd64",private_evaluation=True)
    def test_approved_source_digest_version_license_and_architecture_are_preserved(self):
        policy=self.selected(host_architecture="x86_64")
        self.assertEqual(policy.host_architecture,"amd64")
        self.assertEqual(policy.guest_architecture,"arm64-v8a")
        self.assertEqual(policy.source_version,"SYNTHETIC-NOT-A-REAL-APPLE-RELEASE")
        self.assertEqual(len(policy.member_sha256),2)
        with self.assertRaises(FrozenInstanceError):policy.expected_sha256="0"*64
    def test_incomplete_source_review_license_or_bundle_fails_closed(self):
        mutate=[lambda e:e["source"].update(sha256=None),lambda e:e["source"].update(version=None),
            lambda e:e["source"].update(url="https://third-party.invalid/library"),lambda e:e["bundle"].update(sha256=None),
            lambda e:e["bundle"]["member_sha256"].update({"lib/arm64-v8a/libCoreADI.so":None}),
            lambda e:e["review"].update(id=None),lambda e:e["review"].update(date="invalid"),
            lambda e:e["license"].update(native_review="pending"),lambda e:e["license"].update(redistribution="not-approved"),
            lambda e:e["wrapper"].update(version="unreviewed"),lambda e:e.update(guest_architecture="x86_64")]
        for mutation in mutate:
            value=self.manifest();mutation(value["artifacts"][0])
            with self.subTest(mutation=mutation),self.assertRaises(ArtifactBlocked):self.selected(value)
    def test_unknown_duplicate_and_unreviewed_architecture_are_rejected(self):
        for arch in ("aarch64","armv7","invalid"):
            with self.assertRaisesRegex(ArtifactBlocked,"artifact_architecture_unsupported"):self.selected(host_architecture=arch)
        value=self.manifest();value["artifacts"].append(copy.deepcopy(value["artifacts"][0]))
        with self.assertRaisesRegex(ArtifactBlocked,"artifact_policy_invalid"):self.selected(value)
        with self.assertRaisesRegex(ArtifactBlocked,"artifact_not_approved"):reviewed_artifact("unknown",host_architecture="amd64")
    async def test_local_artifact_is_hashed_off_loop_with_no_downloader(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"library";path.write_bytes(b"synthetic-library")
            seen=[];original=hashlib.sha256
            def hash(value):seen.append(threading.get_ident());return original(value)
            policy=self.selected()
            with patch("retrace.artifact_policy.hashlib.sha256",side_effect=hash):
                self.assertEqual(await verify_artifact(path,policy),b"synthetic-library")
            self.assertNotEqual(seen,[threading.get_ident()])
    async def test_changed_missing_symlink_and_nonregular_artifacts_are_refused(self):
        policy=self.selected()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"changed").write_bytes(b"unexpected")
            (root/"symlink").symlink_to(root/"changed");(root/"directory").mkdir()
            for name in ("changed","missing","symlink","directory"):
                with self.subTest(name=name),self.assertRaises(ArtifactBlocked):await verify_artifact(root/name,policy)
    async def test_runtime_manifest_or_constructed_descriptor_cannot_approve_digest(self):
        with self.assertRaisesRegex(ArtifactBlocked,"reviewed_artifact_required"):
            await verify_artifact("unused",{"sha256":"0"*64})
        forged=replace(self.selected(),_issuer=object())
        with self.assertRaisesRegex(ArtifactBlocked,"reviewed_artifact_required"):await verify_artifact("unused",forged)
    def test_malformed_manifest_and_duplicate_json_keys_are_refused(self):
        from retrace.artifact_policy import _load_manifest
        for data in (b'{"schema_version":1,"schema_version":1}',b'not-json',b''):
            with patch("pathlib.Path.read_bytes",return_value=data),self.assertRaisesRegex(ArtifactBlocked,"artifact_policy_invalid"):_load_manifest()

class NativeBundleRecipeTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        path=Path(__file__).resolve().parents[1]/"tools/review-native-artifact.py"
        spec=importlib.util.spec_from_file_location("native_recipe",path)
        self.recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.recipe)
    def fixture(self):
        from io import BytesIO
        import zipfile
        value=bytearray(40);value[:6]=b"\x7fELF\x02\x01";value[18:20]=b"\xb7\x00"
        data=bytes(value)+b"synthetic-test-only"
        names=("lib/arm64-v8a/libCoreADI.so","lib/arm64-v8a/libstoreservicescore.so")
        source=BytesIO()
        with zipfile.ZipFile(source,"w") as z:
            for name in names:z.writestr(name,data)
            z.writestr("unrelated-secret-looking-file",b"not included")
        apk=source.getvalue()
        entry={"source":{"sha256":hashlib.sha256(apk).hexdigest()},"bundle":{"member_sha256":{name:hashlib.sha256(data).hexdigest() for name in names}}}
        return apk,entry
    def test_recipe_is_deterministic_and_excludes_unreviewed_members(self):
        from io import BytesIO
        import tarfile
        apk,entry=self.fixture()
        first=self.recipe.bundle_from_apk(apk,entry)
        self.assertEqual(first,self.recipe.bundle_from_apk(apk,entry))
        with tarfile.open(fileobj=BytesIO(first)) as tar:
            self.assertEqual(tar.getnames(),["./libs/libCoreADI.so","./libs/libstoreservicescore.so","fs.json"])
            self.assertEqual(json.load(tar.extractfile("fs.json")),{"libs":"./libs"})
            self.assertTrue(all(member.isfile() and member.mtime==0 and member.uid==0 and member.gid==0 for member in tar))
    def test_recipe_rejects_source_member_and_architecture_mismatches(self):
        apk,entry=self.fixture()
        bad=copy.deepcopy(entry);bad["source"]["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"source_digest_mismatch"):self.recipe.bundle_from_apk(apk,bad)
        bad=copy.deepcopy(entry);bad["bundle"]["member_sha256"]["lib/arm64-v8a/libCoreADI.so"]="0"*64
        with self.assertRaisesRegex(ValueError,"source_member_digest_mismatch"):self.recipe.bundle_from_apk(apk,bad)
        bad=copy.deepcopy(entry);bad["bundle"]["member_sha256"]["../unexpected"]="0"*64
        with self.assertRaisesRegex(ValueError,"source_member_invalid"):self.recipe.bundle_from_apk(apk,bad)

    def test_recipe_rejects_non_arm64_bytes_even_with_matching_source_and_member_hashes(self):
        from io import BytesIO
        import zipfile
        apk,entry=self.fixture();source=BytesIO()
        with zipfile.ZipFile(BytesIO(apk)) as original,zipfile.ZipFile(source,"w") as replacement:
            for name in entry["bundle"]["member_sha256"]:
                data=bytearray(original.read(name));data[18:20]=b"\x3e\x00"
                replacement.writestr(name,data)
                entry["bundle"]["member_sha256"][name]=hashlib.sha256(data).hexdigest()
        apk=source.getvalue();entry["source"]["sha256"]=hashlib.sha256(apk).hexdigest()
        with self.assertRaisesRegex(ValueError,"source_architecture_invalid"):self.recipe.bundle_from_apk(apk,entry)

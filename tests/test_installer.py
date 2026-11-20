import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/"package"
        self.root.mkdir()
        shutil.copyfile(Path(__file__).parents[1]/"tools/installer.py",self.root/"install.py")
        for name in ("payload/retrace/config.yaml","payload/custom_components/retrace/manifest.json"):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("fixture")
        self.manifest()
        self.app=Path(self.tmp.name)/"addons/local/retrace"
        self.integration=Path(self.tmp.name)/"config/custom_components/retrace"
    def tearDown(self):
        self.tmp.cleanup()
    def manifest(self):
        manifest={str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file() and p.name!="SHA256SUMS.json"}
        (self.root/"SHA256SUMS.json").write_text(json.dumps(manifest))
    def run_install(self,apply=False):
        args=[sys.executable,str(self.root/"install.py"),"--addon-target",str(self.app),"--integration-target",str(self.integration)]
        if apply:args.append("--apply")
        return subprocess.run(args,capture_output=True,text=True)
    def test_dry_run_changes_nothing_then_apply_is_explicit(self):
        self.assertEqual(self.run_install().returncode,0)
        self.assertFalse(self.app.exists())
        self.assertEqual(self.run_install(True).returncode,0)
        self.assertTrue((self.app/"config.yaml").is_file())
        self.assertTrue((self.integration/"manifest.json").is_file())
    def test_refuses_tampered_package(self):
        (self.root/"payload/retrace/config.yaml").write_text("tampered")
        self.assertNotEqual(self.run_install(True).returncode,0)
        self.assertFalse(self.app.exists())
    def test_refuses_existing_target(self):
        self.app.mkdir(parents=True)
        marker=self.app/"do-not-touch";marker.write_text("existing")
        self.assertNotEqual(self.run_install(True).returncode,0)
        self.assertEqual(marker.read_text(),"existing")
    def test_rejects_symlink(self):
        p=self.root/"payload/retrace/config.yaml"
        p.unlink();p.symlink_to(self.root/"install.py")
        self.assertNotEqual(self.run_install(True).returncode,0)

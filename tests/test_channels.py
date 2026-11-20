import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("render_channel",ROOT/"tools/render-channel.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ChannelTests(unittest.TestCase):
    def test_edge_contains_only_install_files_and_matching_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"edge"
            module.render(ROOT,target,"edge","0.1.2-dev.2.1")
            config=(target/"findmy_home/config.yaml").read_text()
            self.assertEqual(json.loads((target/"findmy_home/rootfs/app/findmy_home/channel.json").read_text())["channel"],"edge")
            self.assertIn("name: Find My Home Edge",config)
            self.assertIn("version: 0.1.2-dev.2.1",config)
            self.assertIn("stage: experimental",config)
            manifest=json.loads((target/"custom_components/findmy_home/manifest.json").read_text())
            self.assertEqual(manifest["version"],"0.1.2-dev.2.1")
            self.assertFalse((target/"tools").exists())
            self.assertFalse((target/".git").exists())
            self.assertFalse((target/"data").exists())
            self.assertTrue((target/"LICENSE").exists())
            self.assertFalse(list(target.rglob("__pycache__")))
    def test_channel_versions_cannot_be_confused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for channel,version in [("edge","0.1.2"),("stable","0.1.2-dev.1.1"),("edge","../secret")]:
                with self.assertRaises(ValueError):
                    module.render(ROOT,Path(tmp)/"output",channel,version)
    def test_stable_keeps_experimental_marker_until_live_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"stable"
            module.render(ROOT,target,"stable","0.1.2")
            self.assertIn("stage: experimental",(target/"findmy_home/config.yaml").read_text())
            self.assertEqual(json.loads((target/"CHANNEL.json").read_text())["channel"],"stable")

    def test_shared_edge_renderer_selects_shared_dockerfile_and_explicit_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"shared-edge"
            module.render(ROOT,target,"edge","0.1.12-dev.1.1",runtime="shared")
            self.assertIn("  runtime_mode: shared",(target/"findmy_home/config.yaml").read_text())
            self.assertEqual((target/"findmy_home/Dockerfile").read_bytes(),(ROOT/"findmy_home/Dockerfile.shared").read_bytes())
            self.assertEqual(json.loads((target/"CHANNEL.json").read_text())["runtime"],"shared")
            self.assertIn("same authenticated account",(target/"findmy_home/DOCS.md").read_text())
            self.assertEqual((target/"findmy_home/apparmor.txt").read_bytes(),(ROOT/"findmy_home/apparmor.shared.txt").read_bytes())
            with self.assertRaises(ValueError):module.render(ROOT,Path(tmp)/"stable","stable","0.1.12",runtime="shared")

    def test_channel_render_excludes_private_component_and_session_files(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"source";source.mkdir()
            for folder in ('findmy_home','custom_components','docs'):
                shutil.copytree(ROOT/folder,source/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            for name in ('README.md','repository.yaml','hacs.json','LICENSE'):shutil.copyfile(ROOT/name,source/name)
            private=source/'findmy_home/rootfs/app/private-fixture';private.mkdir()
            for name in ('owned-libs.bin','source.apk','session.key','session.enc','account.json','owned-signing.json'):(private/name).write_text('SYNTHETIC_PRIVATE')
            target=Path(tmp)/'rendered'
            module.render(source,target,'edge','0.1.12-dev.1.1',runtime='shared')
            self.assertEqual(list((target/'findmy_home/rootfs/app/private-fixture').iterdir()),[])

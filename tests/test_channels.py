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

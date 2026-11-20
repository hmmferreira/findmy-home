import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('findmy_evaluation',ROOT/'tools/render-evaluation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class EvaluationChannelTests(unittest.TestCase):
    def test_side_by_side_render_preserves_existing_app_and_its_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp);old=target/'findmy_home';old.mkdir();(old/'config.yaml').write_text('existing working app')
            app=module.render(ROOT,target,'0.1.13-dev.1.1')
            self.assertEqual((old/'config.yaml').read_text(),'existing working app')
            config=(app/'config.yaml').read_text()
            self.assertIn('slug: findmy_home_shared',config)
            self.assertIn('name: Find My Home Shared Edge',config)
            self.assertIn('  runtime_mode: shared',config)
            self.assertIn('  private_evaluation: false',config)
            self.assertIn('  install_reviewed_component: false',config)
            self.assertEqual((app/'Dockerfile').read_bytes(),(ROOT/'findmy_home/Dockerfile.shared').read_bytes())
            self.assertEqual(sorted(p.name for p in target.iterdir()),['findmy_home','findmy_home_shared'])
            with self.assertRaises(ValueError):module.render(ROOT,target,'0.1.13-dev.1.2')

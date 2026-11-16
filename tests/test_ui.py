import os
from pathlib import Path
import shutil
import subprocess
import unittest

class UiTests(unittest.TestCase):
    def test_browser_dom_flows(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIsNotNone(shutil.which("node"),"UI tests require the test container or Node.js")
        env={**os.environ,"NODE_PATH":str(root/"tools/ui-tests/node_modules")}
        result=subprocess.run(["node","--test",str(root/"tests/ui.test.cjs")],
                              cwd=root,env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,(result.stdout+result.stderr)[-16000:])

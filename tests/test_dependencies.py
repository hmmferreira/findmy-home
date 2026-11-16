"""Guard runtime dependency drift between tests and the committed lock."""
import importlib.metadata
from pathlib import Path
import re
import unittest

class DependencyTests(unittest.TestCase):
    def test_installed_runtime_matches_lock_and_direct_intent(self):
        root=Path(__file__).resolve().parents[1]/"findmy_home"
        lock=root.joinpath("requirements.lock").read_text()
        pins=dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)",lock,re.M))
        self.assertGreater(len(pins),4)
        normalize=lambda name:re.sub(r"[-_.]+","-",name).lower()
        locked={normalize(name):version for name,version in pins.items()}
        for name,version in pins.items():
            self.assertEqual(importlib.metadata.version(name),version,name)
        for name,version in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s]+)",root.joinpath("requirements.txt").read_text(),re.M):
            self.assertEqual(locked[normalize(name)],version,name)

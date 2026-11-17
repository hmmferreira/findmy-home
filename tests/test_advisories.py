from datetime import date
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location("audit_python",Path(__file__).resolve().parents[1]/"tools/audit-python.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AdvisoryTests(unittest.TestCase):
    def note(self):
        return {"package":"fixture-package","version":"1.0","advisory":"GHSA-fixture","expires":"2026-12-17","reason":"Synthetic scoped reason","source":"https://example.invalid/advisory"}
    def test_note_never_ignores_new_advisory_or_changed_version(self):
        values=[{"package":"fixture_package","version":"1.0","advisories":["GHSA-fixture","GHSA-new"]},
                {"package":"fixture-package","version":"2.0","advisories":["GHSA-fixture"]}]
        findings=module.evaluate(values,[self.note()],date(2026,11,17))
        self.assertEqual(len(findings),2)
        self.assertEqual(findings[0]["advisory"],"GHSA-new")
    def test_expired_applicability_note_blocks_validation(self):
        with self.assertRaises(ValueError): module.evaluate([],[self.note()],date(2026,12,18))
    def test_unexplained_note_blocks_validation(self):
        value=self.note();value["reason"]=""
        with self.assertRaises(ValueError): module.evaluate([],[value],date(2026,11,17))

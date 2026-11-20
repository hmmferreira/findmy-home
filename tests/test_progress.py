import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock
from retrace.progress import QueryProgress,safe_progress
from retrace.storage import read_json

class ProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_instrumentation_retains_async_results_and_only_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"progress.json"
            progress=QueryProgress(path)
            account=SimpleNamespace(fetch_raw_reports=AsyncMock(return_value=["PRIVATE_REPORT"]))
            accessory=SimpleNamespace(keys_at=lambda index:{"PRIVATE_KEY"})
            progress.instrument(account,accessory)
            self.assertEqual(accessory.keys_at(12345),{"PRIVATE_KEY"})
            self.assertEqual(await account.fetch_raw_reports(["PRIVATE_ID"]),["PRIVATE_REPORT"])
            progress.complete()
            data=read_json(path)
            self.assertEqual(data["indices_checked"],1)
            self.assertEqual(data["report_batches"],1)
            self.assertEqual(data["reports_returned"],1)
            self.assertNotIn("PRIVATE",json.dumps(data))
            self.assertNotIn("12345",json.dumps(data))
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
    async def test_untrusted_fields_are_not_returned(self):
        result=safe_progress({"phase":"deriving_keys","indices_checked":3,"key":"PRIVATE","latitude":1,"item_id":"PRIVATE"})
        self.assertEqual(result,{"phase":"deriving_keys","indices_checked":3})
        self.assertEqual(safe_progress({"phase":"PRIVATE","report_batches":1}),{})

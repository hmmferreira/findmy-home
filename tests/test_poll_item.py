import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
from findmy_home.storage import atomic_json,read_json
from findmy_home.poll_item import query

class ChildQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_accessory_and_shared_account_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            item="a"*32
            session={"fixture":"token-only"}
            atomic_json(root/"account.json",session)
            atomic_json(root/"items.json",{item:{"enabled":True,"key_file":item+".json"}})
            atomic_json(root/"keys"/(item+".json"),{"fixture":"key"})
            accessory=SimpleNamespace(keys_at=lambda index:set(),to_json=lambda:{"fixture":"updated-alignment"})
            account=SimpleNamespace(_http=None,fetch_raw_reports=AsyncMock(return_value=[]),fetch_location=AsyncMock(return_value=None),close=AsyncMock())
            with patch.dict(os.environ,{"FINDMY_HOME_DATA":tmp}), patch("sys.stdin",SimpleNamespace(buffer=io.BytesIO(json.dumps({"id":item}).encode()))), patch("findmy_home.poll_item.ReportingAccount.from_json",return_value=account), patch("findmy.FindMyAccessory.from_json",return_value=accessory):
                self.assertEqual(await query(),{"ok":True,"report":None})
            account.fetch_location.assert_awaited_once_with(accessory)
            account.close.assert_awaited_once()
            self.assertEqual(read_json(root/"account.json"),session)
            self.assertEqual(read_json(root/"keys"/(item+".json")),{"fixture":"updated-alignment"})

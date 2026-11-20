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
            accessory=SimpleNamespace(get_min_index=lambda date:0,get_max_index=lambda date:10,keys_at=lambda index:set(),to_json=lambda:{"fixture":"updated-alignment"})
            account=SimpleNamespace(_http=None,fetch_raw_reports=AsyncMock(return_value=[]),fetch_location=AsyncMock(return_value=None),close=AsyncMock())
            with patch.dict(os.environ,{"FINDMY_HOME_DATA":tmp}), patch("sys.stdin",SimpleNamespace(buffer=io.BytesIO(json.dumps({"id":item}).encode()))), patch("findmy_home.poll_item.ReportingAccount.from_json",return_value=account), patch("findmy.FindMyAccessory.from_json",return_value=accessory):
                self.assertEqual(await query(),{"ok":True,"search_pending":False,"report":None})
            account.fetch_location.assert_awaited_once_with(accessory)
            account.close.assert_awaited_once()
            self.assertEqual(read_json(root/"account.json"),session)
            self.assertEqual(read_json(root/"keys"/(item+".json")),{"fixture":"updated-alignment"})

    async def test_owned_session_failure_requests_authentication_before_fetch(self):
        from findmy_home.owned_session import SessionBlocked
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);item="a"*32
            atomic_json(root/"items.json",{item:{"enabled":True,"key_file":item+".json"}})
            with patch.dict(os.environ,{"FINDMY_HOME_DATA":tmp}), patch("sys.stdin",SimpleNamespace(buffer=io.BytesIO(json.dumps({"id":item}).encode()))), patch("findmy_home.poll_item.restore_reporting_account",new=AsyncMock(side_effect=SessionBlocked("session_expired"))), patch("findmy.FindMyAccessory.from_json") as accessory:
                self.assertEqual(await query(),{"ok":False,"error":"authentication_required","diagnostic":{"stage":"session_restore","code":"session_expired"}})
                accessory.assert_not_called()

    async def test_missing_worker_boundary_requests_setup_instead_of_apple_login(self):
        from findmy_home.owned_session import SessionBlocked
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);item="a"*32
            atomic_json(root/"items.json",{item:{"enabled":True,"key_file":item+".json"}})
            with patch.dict(os.environ,{"FINDMY_HOME_DATA":tmp}),patch("sys.stdin",SimpleNamespace(buffer=io.BytesIO(json.dumps({"id":item}).encode()))),patch("findmy_home.poll_item.restore_reporting_account",new=AsyncMock(side_effect=SessionBlocked("worker_boundary_unavailable"))):
                self.assertEqual(await query(),{"ok":False,"error":"setup_required","diagnostic":{"stage":"session_restore","code":"worker_boundary_unavailable"}})

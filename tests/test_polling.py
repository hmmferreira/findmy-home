from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from findmy_home.storage import Store, atomic_json, read_json
from findmy_home.worker import AppleWorker

class PollTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name))
        self.store.items={"a":{"name":"Fixture","enabled":True,"key_file":"a.json"}}
        atomic_json(self.store.root/"account.json",{"fixture":True})
        self.worker=AppleWorker(self.store)
    async def asyncTearDown(self):
        self.tmp.cleanup()
    async def fetch(self,report=None,error=None):
        class Accessory:
            def to_json(self): return {"fixture":True}
        accessory=Accessory()
        account=SimpleNamespace(fetch_location=AsyncMock(return_value={accessory:report},side_effect=error),
            close=AsyncMock(),to_json=lambda:{"account":{"password":"DO_NOT_KEEP"}})
        with patch("findmy.AsyncAppleAccount.from_json",return_value=account), patch("findmy.FindMyAccessory.from_json",return_value=accessory):
            await self.worker._fetch({"fixture":True},self.store.items)
        return account
    async def test_original_timestamp_and_password_scrubbing(self):
        sighting=datetime.now(timezone.utc)-timedelta(hours=4)
        await self.fetch(SimpleNamespace(latitude=1.,longitude=2.,horizontal_accuracy=30.,timestamp=sighting))
        self.assertEqual(self.store.reports["a"]["timestamp"],sighting.isoformat())
        self.assertIsNone(read_json(self.store.root/"account.json")["account"]["password"])
        self.assertEqual(self.store.health["status"],"ok")
    async def test_no_report_preserves_old_sighting(self):
        old={"latitude":1,"longitude":2,"accuracy":10,"timestamp":(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}
        self.store.reports["a"]=old.copy()
        await self.fetch()
        self.assertEqual(self.store.reports["a"],old)
        self.assertEqual(self.store.health["status"],"ok")
    async def test_invalid_and_future_reports_are_ignored(self):
        for lat,when in [(float("nan"),datetime.now(timezone.utc)),(1,datetime.now(timezone.utc)+timedelta(days=1))]:
            await self.fetch(SimpleNamespace(latitude=lat,longitude=2,horizontal_accuracy=3,timestamp=when))
            self.assertNotIn("a",self.store.reports)
    async def test_expired_token_requires_ui_not_saved_password(self):
        account=await self.fetch(error=ValueError("No username or password specified"))
        self.assertEqual(self.store.health["status"],"reauth_required")
        account.close.assert_awaited_once()
    async def test_disabled_items_do_not_trigger_query(self):
        self.store.items["a"]["enabled"]=False
        with patch.object(self.worker,"_poll_thread") as query:
            await self.worker.poll()
            query.assert_not_called()
        self.assertEqual(self.store.health["status"],"select_items")

"""Synthetic range coverage and SDK compatibility; no Apple requests."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from findmy_home.search import fetch_bounded, RECENT_INDICES, OLDER_INDICES
from findmy_home.storage import atomic_json,read_json

class SearchTests(unittest.IsolatedAsyncioTestCase):
    def accessory(self,top=10000,floor=0):
        return SimpleNamespace(get_min_index=lambda date:floor,get_max_index=lambda date:top)

    async def test_resume_covers_every_index_without_repeating_older_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"search.json"
            accessory=self.accessory()
            bounds=[]
            async def fetch(item):
                now=datetime.now(timezone.utc)
                bounds.append((item.get_min_index(now),item.get_max_index(now)))
                return None
            account=SimpleNamespace(fetch_location=fetch)
            pending=True
            while pending:
                report,pending=await fetch_bounded(account,accessory,path)
                self.assertIsNone(report)
            recent=bounds[0]
            self.assertEqual(recent,(10000-RECENT_INDICES+1,10000))
            self.assertTrue(all(bounds[i]==recent for i in range(0,len(bounds),2)))
            older=[index for low,high in bounds[1::2] for index in range(high,low-1,-1)]
            self.assertEqual(older,list(range(recent[0]-1,-1,-1)))
            self.assertTrue(all(high-low+1<=OLDER_INDICES for low,high in bounds[1::2]))
            self.assertFalse(path.exists())
            self.assertEqual(accessory.get_max_index(None),10000)

    async def test_failed_older_request_does_not_advance_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"search.json"
            saved={"version":1,"next_index":5000}
            atomic_json(path,saved)
            accessory=self.accessory()
            original=(accessory.get_min_index,accessory.get_max_index)
            account=SimpleNamespace(fetch_location=AsyncMock(side_effect=[None,RuntimeError("synthetic network failure")]))
            with self.assertRaises(RuntimeError):
                await fetch_bounded(account,accessory,path)
            self.assertEqual(read_json(path),saved)
            self.assertEqual((accessory.get_min_index,accessory.get_max_index),original)

    async def test_recent_report_stops_and_clears_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"search.json"
            atomic_json(path,{"version":1,"next_index":5000})
            report=object()
            account=SimpleNamespace(fetch_location=AsyncMock(return_value=report))
            self.assertEqual(await fetch_bounded(account,self.accessory(),path),(report,False))
            account.fetch_location.assert_awaited_once()
            self.assertFalse(path.exists())

    async def test_short_search_finishes_in_one_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            account=SimpleNamespace(fetch_location=AsyncMock(return_value=None))
            self.assertEqual(await fetch_bounded(account,self.accessory(top=10),Path(tmp)/"s.json"),(None,False))
            account.fetch_location.assert_awaited_once()

    async def test_checkpoint_is_private_and_untrusted_cursor_is_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"search.json"
            atomic_json(path,{"version":1,"next_index":True})
            account=SimpleNamespace(fetch_location=AsyncMock(return_value=None))
            self.assertEqual(await fetch_bounded(account,self.accessory(),path),(None,True))
            self.assertEqual(read_json(path),{"version":1,"next_index":10000-RECENT_INDICES-OLDER_INDICES})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    async def test_real_sdk_batches_accept_bounded_accessory_and_restore_methods(self):
        from findmy import FindMyAccessory
        from findmy.reports.reports import LocationReportsFetcher
        accessory=FindMyAccessory(master_key=bytes(range(28)),skn=b"n"*32,sks=b"s"*32,
            paired_at=datetime.now(timezone.utc)-timedelta(days=2))
        raw=AsyncMock(return_value=[])
        account=SimpleNamespace(fetch_raw_reports=raw)
        fetcher=LocationReportsFetcher(account)
        async def fetch(item):
            reports=await fetcher.fetch_location_history(item)
            return reports[-1] if reports else None
        account.fetch_location=fetch
        original=(accessory.get_min_index,accessory.get_max_index)
        with tempfile.TemporaryDirectory() as tmp, patch("findmy_home.search.RECENT_INDICES",10), patch("findmy_home.search.OLDER_INDICES",20):
            self.assertEqual(await fetch_bounded(account,accessory,Path(tmp)/"search.json"),(None,True))
        self.assertEqual(raw.await_count,2)
        primary_counts=[len(call.args[0][0][0]) for call in raw.await_args_list]
        self.assertEqual(primary_counts,[10,20])
        self.assertEqual((accessory.get_min_index,accessory.get_max_index),original)

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from retrace.storage import Store, atomic_json
from retrace.worker import AppleWorker

class PollTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name))
        self.store.items={str(n):{"enabled":True} for n in range(6)}
        atomic_json(self.store.root/"account.json",{"fixture":True})
        self.worker=AppleWorker(self.store)
        self.worker.START_SPACING=0

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def report(self, age=1):
        return {"latitude":1.,"longitude":2.,"accuracy":30.,
                "timestamp":(datetime.now(timezone.utc)-timedelta(hours=age)).isoformat()}

    async def test_two_workers_publish_before_slow_item_and_keep_ui_unlocked(self):
        release=asyncio.Event()
        published=asyncio.Event()
        active=peak=0
        async def query(key):
            nonlocal active,peak
            active+=1
            peak=max(peak,active)
            try:
                if key=="0":
                    await release.wait()
                else:
                    await asyncio.sleep(.005)
                return {"ok":True,"report":self.report()}
            finally:
                active-=1
                if key=="1": published.set()
        with patch.object(self.worker,"_query_item",side_effect=query):
            task=asyncio.create_task(self.worker.poll())
            try:
                await asyncio.wait_for(published.wait(),1)
                await asyncio.sleep(.01)
                self.assertIn("1",self.store.reports)
                self.assertNotIn("0",self.store.reports)
                self.assertEqual(self.store.health["status"],"polling")
                self.assertFalse(self.worker.lock.locked())
                await self.worker.poll()  # Single-flight: no duplicate queries.
            finally:
                release.set()
                await task
        self.assertEqual(peak,2)
        self.assertEqual(self.store.health["items_completed"],6)
        self.assertEqual(self.store.health["reports_received"],6)

    async def test_rate_limit_stops_queued_items(self):
        async def query(key):
            return {"ok":False,"error":"rate_limited"}
        with patch.object(self.worker,"_query_item",side_effect=query) as call:
            await self.worker.poll()
        self.assertLessEqual(call.call_count,2)
        self.assertEqual(self.store.health["error_code"],"rate_limited")
        self.assertEqual(self.store.health["status"],"error")

    async def test_partial_failure_keeps_success_and_old_report(self):
        old=self.report(4)
        self.store.reports["0"]=old.copy()
        async def query(key):
            return {"ok":False,"error":"item_timeout"} if key=="0" else {"ok":True,"report":self.report()}
        with patch.object(self.worker,"_query_item",side_effect=query):
            await self.worker.poll()
        self.assertEqual(self.store.reports["0"],old)
        self.assertEqual(self.store.health["status"],"partial_results")
        self.assertEqual(self.store.health["items_failed"],1)

    async def test_no_report_does_not_refresh_old_sighting(self):
        old=self.report(4)
        self.store.reports["0"]=old.copy()
        with patch.object(self.worker,"_query_item",AsyncMock(return_value={"ok":True,"report":None})):
            await self.worker.poll()
        self.assertEqual(self.store.reports["0"],old)
        self.assertEqual(self.store.health["status"],"no_reports")

    async def test_rejects_invalid_future_and_older_report(self):
        self.assertFalse(self.worker._accept_report("0",{**self.report(),"latitude":float("nan")}))
        self.assertFalse(self.worker._accept_report("0",self.report(-1)))
        self.assertTrue(self.worker._accept_report("0",self.report(1)))
        self.assertFalse(self.worker._accept_report("0",self.report(2)))

    async def test_timeout_kills_cpu_bound_child_without_blocking_loop(self):
        self.worker.ITEM_TIMEOUT=.1
        self.worker._item_command=[sys.executable,"-c","while True: pass"]
        ticks=0
        async def heartbeat():
            nonlocal ticks
            for _ in range(5):
                await asyncio.sleep(.01)
                ticks+=1
        result,_=await asyncio.gather(self.worker._query_item("0"),heartbeat())
        self.assertEqual(result["error"],"item_timeout")
        self.assertEqual(ticks,5)

    async def test_cancellation_cleans_up_both_workers(self):
        active=0
        started=asyncio.Event()
        async def query(key):
            nonlocal active
            active+=1
            if active==2: started.set()
            try: await asyncio.Event().wait()
            finally: active-=1
        with patch.object(self.worker,"_query_item",side_effect=query):
            task=asyncio.create_task(self.worker.poll())
            await asyncio.wait_for(started.wait(),1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(active,0)
        self.assertFalse(self.worker.poll_lock.locked())

    async def test_disabled_items_do_not_trigger_query(self):
        for item in self.store.items.values(): item["enabled"]=False
        with patch.object(self.worker,"_query_item") as query:
            await self.worker.poll()
            query.assert_not_called()
        self.assertEqual(self.store.health["status"],"select_items")

    async def test_ui_wake_does_not_bypass_poll_cooldown(self):
        import time
        async def fake_poll(): self.worker.last_attempt=time.monotonic()
        with patch.object(self.worker,"poll",AsyncMock(side_effect=fake_poll)) as query:
            task=asyncio.create_task(self.worker.run())
            await asyncio.sleep(.02)
            self.worker.request_poll()
            await asyncio.sleep(.02)
            self.assertEqual(query.await_count,1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task

    async def test_pending_search_does_not_become_no_reports_or_error_backoff(self):
        with patch.object(self.worker,"_query_item",AsyncMock(return_value={"ok":True,"report":None,"search_pending":True})):
            await self.worker.poll()
        self.assertEqual(self.store.health["status"],"searching")
        self.assertEqual(self.store.health["items_searching"],6)
        self.assertEqual(self.store.health["items_failed"],0)
        self.assertEqual(self.worker.failures,0)

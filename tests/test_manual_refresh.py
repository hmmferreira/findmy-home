import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock,patch
from findmy_home.storage import Store,atomic_json
from findmy_home.worker import AppleWorker

class ManualRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name))
        self.store.items={str(n):{"enabled":True,"name":"Fixture"} for n in range(4)}
        atomic_json(self.store.root/"account.json",{"fixture":True})
        self.worker=AppleWorker(self.store)
        self.worker.START_SPACING=0
    async def asyncTearDown(self):
        await self.worker.close()
        self.tmp.cleanup()

    async def test_manual_refresh_bypasses_scheduled_interval_and_deduplicates(self):
        self.worker.last_attempt=time.monotonic()
        release=asyncio.Event()
        async def query(key):
            await release.wait()
            return {"ok":True,"report":None}
        with patch.object(self.worker,"_query_process",side_effect=query) as call:
            self.assertEqual(self.worker.request_refresh("0")["status"],"queued")
            self.assertEqual(self.worker.request_refresh("0")["status"],"queued")
            task=self.worker.manual_tasks["0"]
            await asyncio.sleep(0)
            self.assertEqual(self.worker.request_refresh("0")["status"],"refreshing")
            release.set()
            await task
            self.assertEqual(call.call_count,1)
            self.assertEqual(self.store.item_health["0"]["status"],"no_report")
            self.assertEqual(self.worker.request_refresh("0")["status"],"cooldown")

    async def test_manual_and_scheduled_work_share_two_slots(self):
        release=asyncio.Event()
        both_started=asyncio.Event()
        started=[]
        active=peak=0
        async def query(key):
            nonlocal active,peak
            started.append(key);active+=1;peak=max(peak,active)
            if len(started)==2: both_started.set()
            try:
                if key in ("0","1"): await release.wait()
                await asyncio.sleep(.01)
                return {"ok":True,"report":None}
            finally: active-=1
        with patch.object(self.worker,"_query_process",side_effect=query):
            automatic=asyncio.create_task(self.worker.poll())
            try:
                await asyncio.wait_for(both_started.wait(),1)
                self.assertEqual(self.worker.request_refresh("3")["status"],"queued")
                manual=self.worker.manual_tasks["3"]
                await asyncio.sleep(0)
                release.set()
                await asyncio.gather(automatic,manual)
            finally:
                release.set()
                if not automatic.done():
                    automatic.cancel()
                    await asyncio.gather(automatic,return_exceptions=True)
        self.assertEqual(peak,2)
        self.assertEqual(started.count("3"),1)
        self.assertEqual(len(started),4)

    async def test_manual_refresh_respects_persisted_apple_pause(self):
        atomic_json(self.store.root/"request-cooldown.json",{"until":time.time()+1800})
        with patch.object(self.worker,"_query_process") as call:
            result=self.worker.request_refresh("0")
            self.assertEqual(result["status"],"paused")
            self.assertGreater(result["retry_after"],1700)
            self.assertFalse(self.worker.manual_tasks)
            call.assert_not_called()

    async def test_disabled_item_is_not_refreshable(self):
        self.store.items["0"]["enabled"]=False
        with self.assertRaises(ValueError): self.worker.request_refresh("0")

    async def test_refresh_api_is_management_only_and_requires_csrf(self):
        from aiohttp.test_utils import TestClient,TestServer
        from findmy_home.server import make_app
        api=TestClient(TestServer(make_app(self.store,worker=self.worker)))
        ui=TestClient(TestServer(make_app(self.store,worker=self.worker,management=True,trusted_peer="127.0.0.1")))
        await api.start_server();await ui.start_server()
        try:
            token={"Authorization":"Bearer "+self.store.identity["read_token"]}
            self.assertEqual((await api.post("/ui/refresh",headers=token,json={"id":"0"})).status,404)
            owner={"X-Remote-User-Id":"alice"}
            self.assertEqual((await ui.post("/ui/refresh",headers=owner,json={"id":"0"})).status,403)
            snapshot=await (await ui.get("/v1/snapshot",headers=owner)).json()
            owner["X-CSRF-Token"]=snapshot["csrf"]
            with patch.object(self.worker,"request_refresh",return_value={"status":"queued"}) as call:
                self.assertEqual((await ui.post("/ui/refresh",headers=owner,json={"id":"0"})).status,200)
                call.assert_called_once_with("0")
        finally:
            await api.close();await ui.close()

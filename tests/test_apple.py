import unittest
from unittest.mock import AsyncMock,patch
from findmy import AsyncAppleAccount
from findmy.errors import EmptyResponseError
from findmy_home.apple import ReportingAccount,ReportSourceUnavailable

class AppleResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_response_escapes_the_library_no_sighting_fallback(self):
        account=object.__new__(ReportingAccount)
        account._loop=None
        account.close=AsyncMock()
        with patch.object(AsyncAppleAccount,"fetch_raw_reports",AsyncMock(side_effect=EmptyResponseError("private upstream body"))):
            with self.assertRaises(ReportSourceUnavailable) as result:
                await account.fetch_raw_reports([])
        self.assertEqual(str(result.exception),"empty_response")
        self.assertNotIn("private",str(result.exception))
    async def test_legitimate_empty_report_list_is_preserved(self):
        account=object.__new__(ReportingAccount)
        account._loop=None
        account.close=AsyncMock()
        with patch.object(AsyncAppleAccount,"fetch_raw_reports",AsyncMock(return_value=[])):
            self.assertEqual(await account.fetch_raw_reports([]),[])


class PacingTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_429_is_not_retried_or_exposed(self):
        from findmy_home.apple import PacedHttp,RateLimited
        from types import SimpleNamespace
        delegate=SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=429)))
        client=PacedHttp(delegate,None)
        with patch.object(client,"_reserve",return_value=0), patch.object(client,"_check_blocked"), patch.object(client,"_block"):
            with self.assertRaises(RateLimited):
                await client.post("https://example.invalid")
        delegate.post.assert_awaited_once()

    async def test_cross_worker_reservations_are_spaced(self):
        import asyncio,tempfile
        from pathlib import Path
        from findmy_home.apple import PacedHttp
        with tempfile.TemporaryDirectory() as tmp:
            gate=Path(tmp)/"gate"
            clients=[PacedHttp(None,gate),PacedHttp(None,gate)]
            delays=await asyncio.gather(*(asyncio.to_thread(c._reserve) for c in clients))
            self.assertLess(min(delays),.2)
            self.assertGreater(max(delays),.8)
            self.assertEqual(gate.stat().st_mode & 0o777,0o600)

    async def test_rate_limit_cooldown_is_shared_with_other_worker(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from findmy_home.apple import PacedHttp,RateLimited
        with tempfile.TemporaryDirectory() as tmp:
            delegate=SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=429)))
            gate=Path(tmp)/"gate"
            first,second=PacedHttp(delegate,gate),PacedHttp(delegate,gate)
            with self.assertRaises(RateLimited): await first.post("https://example.invalid")
            with self.assertRaises(RateLimited): await second.post("https://example.invalid")
            delegate.post.assert_awaited_once()

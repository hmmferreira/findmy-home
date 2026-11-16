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

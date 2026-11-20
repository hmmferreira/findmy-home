import json
import unittest
from findmy_home.progress import safe_query_diagnostic

class QueryDiagnosticTests(unittest.TestCase):
    def test_diagnostics_cannot_include_arbitrary_native_or_server_messages(self):
        for value in ({'stage':'session_restore','code':'PRIVATE_TOKEN'}, {'stage':'PRIVATE_ID','code':'session_invalid'},None):
            self.assertEqual(safe_query_diagnostic(value),{})
        clean=safe_query_diagnostic({'stage':'session_restore','code':'reporting_backend_unavailable','headers':'PRIVATE_TOKEN','item_id':'PRIVATE_ID'})
        self.assertEqual(clean,{'stage':'session_restore','code':'reporting_backend_unavailable'})
        self.assertNotIn('PRIVATE',json.dumps(clean))

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from retrace.reporting_runtime import report_launch
from retrace.shared_runtime import RuntimeBlocked
from retrace.storage import atomic_json

class ReportingRuntimeTests(unittest.TestCase):
    def test_shared_child_pins_sdk_and_reconstructs_evaluation_from_private_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            atomic_json(root/'runtime-options.json',{'runtime_mode':'shared','private_evaluation':True})
            environment={'FINDMY_RUNTIME_MODE':'shared','FINDMY_PRIVATE_EVALUATION':'0','PYTHONPATH':'/untrusted','SUPERVISOR_TOKEN':'SYNTHETIC_SECRET','APPLE_PASSWORD':'SYNTHETIC_SECRET','SSL_CERT_FILE':'/untrusted.pem'}
            with patch.dict(os.environ,environment,clear=True),patch('retrace.reporting_runtime.require_shared_backend') as checked:
                command,env=report_launch(root)
            checked.assert_called_once()
            self.assertIn('-I',command)
            self.assertIn("'/opt/findmy-shared','/app'",command[-1])
            self.assertEqual(env,{'FINDMY_HOME_DATA':tmp,'FINDMY_RUNTIME_MODE':'shared','FINDMY_PRIVATE_EVALUATION':'1'})
            self.assertNotIn('SYNTHETIC_SECRET',str(command)+str(env))
    def test_private_evaluation_is_not_taken_from_an_unchecked_parent_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);atomic_json(root/'runtime-options.json',{'runtime_mode':'shared','private_evaluation':False})
            with patch.dict(os.environ,{'FINDMY_RUNTIME_MODE':'shared','FINDMY_PRIVATE_EVALUATION':'1'}),patch('retrace.reporting_runtime.require_shared_backend'):
                _,env=report_launch(root)
            self.assertEqual(env['FINDMY_PRIVATE_EVALUATION'],'0')
    def test_missing_or_legacy_options_cannot_downgrade_shared_report_child(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'FINDMY_RUNTIME_MODE':'shared'}):
            with self.assertRaises(RuntimeBlocked):report_launch(Path(tmp))
    def test_default_legacy_report_keeps_its_original_command(self):
        with patch.dict(os.environ,{},clear=True),patch('retrace.reporting_runtime.Path.exists',return_value=False):
            command,env=report_launch(Path('/synthetic'))
        self.assertEqual(command[-2:],['-m','retrace.poll_item'])
        self.assertEqual(env,{'FINDMY_HOME_DATA':'/synthetic'})

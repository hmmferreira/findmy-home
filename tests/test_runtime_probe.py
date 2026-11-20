"""Diagnostic App profile and exact production boundary source checks."""
import asyncio
import ctypes
import sys
import importlib.util
import re
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/"retrace_runtime_probe"

class RuntimeProbeTests(unittest.TestCase):
    def test_probe_copies_exact_production_boundary(self):
        self.assertEqual((PROBE/"native_sandbox.py").read_bytes(),
            (ROOT/"retrace/rootfs/app/retrace/native_sandbox.py").read_bytes())
    def test_probe_requests_no_apis_privileges_ports_or_host_mounts(self):
        text=(PROBE/"config.yaml").read_text()
        # This diagnostic manifest uses flat scalars plus its one architecture;
        # no YAML parser/dependency is needed to verify its security contract.
        config=dict(re.findall(r"^([a-z_]+):[ \t]*(.*)$",text,re.MULTILINE))
        self.assertEqual(config["slug"],"findmy_runtime_probe")
        self.assertEqual(config["version"],"0.1.5")
        self.assertEqual(config["boot"],"manual")
        self.assertRegex(text,r"(?m)^arch:\n  - amd64\n")
        for key in ("ingress","hassio_api","homeassistant_api","docker_api","host_network","full_access"):
            self.assertEqual(config[key],"false")
        for key in ("ports","map","privileged","devices","udev","host_pid","host_dbus","host_ipc"):
            self.assertNotIn(key,config)
        self.assertEqual(config["options"],"{}")
        self.assertEqual(config["schema"],"{}")
    def test_probe_refuses_unexpected_effective_uid_before_spawning(self):
        spec=importlib.util.spec_from_file_location("probe_parent_uid_test",PROBE/"probe.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module.os,"geteuid",return_value=0),patch.object(module.asyncio,"create_subprocess_exec") as spawn:
            self.assertEqual(asyncio.run(module.run_probe()),{"result":"unexpected_uid"})
        spawn.assert_not_called()
    def load_probe_module(self,name):
        spec=importlib.util.spec_from_file_location("probe_"+name+"_test",PROBE/(name+".py"))
        module=importlib.util.module_from_spec(spec)
        old_path=sys.path[:]
        try:spec.loader.exec_module(module)
        finally:sys.path[:]=old_path
        return module
    def test_failure_reason_whitelist_never_echoes_exception_text(self):
        child=self.load_probe_module("child")
        details={"platform":"linux-amd64","uid":1000,"landlock_abi":-1,"landlock_errno":95,"boundary_errno":0,"boundary":"unavailable"}
        for error,expected in (("worker_landlock_unavailable","worker_landlock_unavailable"),
                               ("PRIVATE_SECRET_PATH","unclassified_boundary_failure")):
            ctypes.set_errno(95)
            with patch.object(child,"preflight",return_value=dict(details)),patch.object(child,"read_input",return_value={}),patch.object(
                    child,"restrict_worker",side_effect=child.SandboxUnavailable(error)):
                result=child.main()
            self.assertEqual(result["reason"],expected)
            self.assertEqual(result["diagnostics"]["boundary_errno"],95)
            self.assertNotIn("PRIVATE",str(result))
    def test_parent_rejects_unknown_reason_and_non_numeric_diagnostics(self):
        parent=self.load_probe_module("probe")
        details={"platform":"linux-amd64","uid":1000,"landlock_abi":-1,"landlock_errno":95,"boundary_errno":95,"boundary":"unavailable"}
        value={"result":"boundary_unavailable","reason":"worker_landlock_unavailable","diagnostics":details}
        self.assertEqual(parent.validate_result(value),value)
        with self.assertRaises(ValueError):parent.validate_result({**value,"reason":"PRIVATE_TOKEN"})
        for key,bad in (("uid",True),("landlock_abi",-10),("landlock_errno","PRIVATE"),("boundary_errno",-1)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                parent.validate_result({**value,"diagnostics":{**details,key:bad}})
        with self.assertRaises(ValueError):parent.validate_result({**value,"extra":"PRIVATE"})
    def test_preflight_records_errno_without_reading_host_files(self):
        child=self.load_probe_module("child")
        class Libc:
            class Call:
                restype=None
                def __call__(self,*args):ctypes.set_errno(95);return -1
            syscall=Call()
        with patch.object(child.platform,"system",return_value="Linux"),patch.object(child.platform,"machine",return_value="x86_64"),patch.object(
                child.os,"geteuid",return_value=1000),patch.object(child.ctypes,"CDLL",return_value=Libc()):
            self.assertEqual(child.preflight(),{"platform":"linux-amd64","uid":1000,"landlock_abi":-1,"landlock_errno":95,"boundary_errno":0,"boundary":"unavailable"})
    def test_stderr_classification_never_returns_raw_traceback_or_paths(self):
        parent=self.load_probe_module("probe")
        raw=b'Traceback (most recent call last):\n  File "/PRIVATE_PATH/child.py"\nPermissionError: [Errno 13] PRIVATE_TOKEN\n'
        summary=parent.stderr_summary(raw)
        self.assertEqual(summary,{"child_error":"PermissionError","child_errno":13,"child_phase":"child_bootstrap"})
        self.assertNotIn("PRIVATE",str(summary))
        self.assertEqual(parent.stderr_summary(b"PRIVATE_ONLY")["child_error"],"UnknownError")
        self.assertEqual(parent.stderr_summary(b"sys.stdout.buffer.write(data)")["child_phase"],"framed_output")
    def test_probe_child_and_parent_have_matching_bounded_check_schema(self):
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            return module
        # Parent import performs no probe or external operation.
        parent=load("probe_parent_test",PROBE/"probe.py")
        self.assertEqual(parent.MAX_MESSAGE,4096)
        self.assertEqual(len(parent.EXPECTED_CHECKS),10)
        self.assertEqual(set(parent.EXPECTED_CHECKS),{
            "private_file_open_denied","private_write_denied","parent_proc_open_denied",
            "metadata_change_denied","ipv4_socket_denied","ipv6_socket_denied",
            "unix_socket_denied","exec_denied","parent_signal_denied","dumpability_change_denied"})

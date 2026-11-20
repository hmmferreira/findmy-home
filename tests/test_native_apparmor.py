"""AppArmor transition invariants without modifying host policy."""
import ctypes
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from findmy_home.native_sandbox import _restrict_apparmor,SandboxUnavailable

class NativeAppArmorTests(unittest.TestCase):
    def library(self,contexts,change=0):
        buffers=[];events=[]
        def getcon(label,mode):
            name,state=contexts.pop(0);events.append("context")
            namebuf=ctypes.create_string_buffer(name);buffers.append(namebuf)
            ctypes.cast(label,ctypes.POINTER(ctypes.c_char_p))[0]=ctypes.cast(namebuf,ctypes.c_char_p)
            if state is not None:
                statebuf=ctypes.create_string_buffer(state);buffers.append(statebuf)
                ctypes.cast(mode,ctypes.POINTER(ctypes.c_char_p))[0]=ctypes.cast(statebuf,ctypes.c_char_p)
            return len(name)
        def change_profile(target):events.append(("transition",target));return change
        library=SimpleNamespace(aa_getcon=Mock(side_effect=getcon),aa_change_profile=Mock(side_effect=change_profile))
        return library,events,buffers
    def test_transition_is_exact_child_and_verified_enforced(self):
        library,events,buffers=self.library([(b"9c579022_findmy_home",b"enforce"),(b"9c579022_findmy_home//findmy-native",b"enforce")])
        libc=SimpleNamespace(free=Mock())
        with patch("findmy_home.native_sandbox.ctypes.CDLL",return_value=library):_restrict_apparmor(libc)
        self.assertEqual(events,["context",("transition",b"9c579022_findmy_home//findmy-native"),"context"])
        self.assertEqual(libc.free.call_count,2)
    def test_unconfined_complain_or_already_nested_context_is_refused(self):
        for name,mode in ((b"unconfined",None),(b"root",b"complain"),(b"root//child",b"enforce")):
            library,_,buffers=self.library([(name,mode)])
            with self.subTest(name=name,mode=mode),patch("findmy_home.native_sandbox.ctypes.CDLL",return_value=library):
                with self.assertRaises(SandboxUnavailable) as caught:_restrict_apparmor(SimpleNamespace(free=Mock()))
                self.assertEqual(str(caught.exception),"worker_apparmor_profile_invalid")
            library.aa_change_profile.assert_not_called()
    def test_different_or_complain_destination_never_counts_as_boundary(self):
        for after,mode in ((b"root",b"enforce"),(b"root//findmy-native",b"complain")):
            library,_,buffers=self.library([(b"root",b"enforce"),(after,mode)])
            with patch("findmy_home.native_sandbox.ctypes.CDLL",return_value=library):
                with self.assertRaises(SandboxUnavailable):_restrict_apparmor(SimpleNamespace(free=Mock()))
    def test_missing_library_and_refused_transition_fail_closed(self):
        with patch("findmy_home.native_sandbox.ctypes.CDLL",side_effect=OSError("PRIVATE_PATH")):
            with self.assertRaises(SandboxUnavailable) as caught:_restrict_apparmor(SimpleNamespace(free=Mock()))
        self.assertEqual(str(caught.exception),"worker_apparmor_unavailable")
        library,_,buffers=self.library([(b"root",b"enforce")],change=-1)
        with patch("findmy_home.native_sandbox.ctypes.CDLL",return_value=library):
            with self.assertRaises(SandboxUnavailable) as caught:_restrict_apparmor(SimpleNamespace(free=Mock()))
        self.assertEqual(str(caught.exception),"worker_apparmor_transition_failed")

    def test_probe_and_shared_runtime_have_identical_restrictive_child_policy(self):
        root=Path(__file__).resolve().parents[1]
        probe=(root/"findmy_runtime_probe/apparmor.txt").read_text()
        shared=(root/"findmy_home/apparmor.shared.txt").read_text()
        probe_child=probe.split("  profile findmy-native",1)[1]
        shared_child=shared.split("  profile findmy-native",1)[1]
        self.assertEqual(probe_child,shared_child)
        active=[line.strip() for line in shared_child.splitlines() if line.strip() and not line.strip().startswith("#")]
        self.assertNotIn("file,",active)
        self.assertIn("deny network,",active)
        self.assertFalse(any(line.startswith("change_profile") for line in active))
        self.assertFalse(any("abstractions/base" in line for line in active))
        self.assertTrue(all(line.endswith(" r,") for line in active if "/attr/" in line))

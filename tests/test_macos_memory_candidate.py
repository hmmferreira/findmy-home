import base64
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec=importlib.util.spec_from_file_location('mac_candidate',Path(__file__).resolve().parents[1]/'experiments/macos-signer/adapter.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def reply(ret=0,**outputs):return SimpleNamespace(rc=0,ret=ret,outputs=outputs)

class Core:
    def __init__(self):self.stubs=SimpleNamespace(files={});self.calls=[];self.routing=0
    def initialize(self):return reply()
    def is_machine_provisioned(self,ds):return reply(0 if self.stubs.files else -1)
    def provisioning_start(self,ds,spim):self.calls.append('begin');return reply(cpim=b'synthetic-cpim',session_id=4)
    def provisioning_end(self,handle,ptm,tk):
        self.calls.append('finish');self.stubs.files[m.STORE+'adi-000001F5.pb']=bytearray(b'synthetic-state');return reply()
    def set_routing(self,ds,routing):self.routing=routing;return reply()
    def request_otp(self,ds):return reply(otp=b'synthetic-otp',mid=b'synthetic-mid')
    def get_routing(self,ds):return reply(routing=self.routing)

class MemoryCandidateTests(unittest.TestCase):
    def test_virtual_store_accepts_bounded_metadata_and_empty_lock_files(self):
        core=Core()
        core.stubs.files={m.STORE+'adi-000001F5.pb':bytearray(b'synthetic'),
                          m.STORE+'adi.metadata':bytearray(b'fixture'),m.STORE+'adi.lock':bytearray()}
        encoded={name[len(m.STORE):]:base64.b64encode(value).decode() for name,value in core.stubs.files.items()}
        restored=m.MemoryCore(Core(),'a'*32,saved=encoded)
        self.assertEqual(restored.snapshot(),encoded)

    def test_dispatcher_nonnegative_success_is_not_an_error(self):
        core=Core()
        core.initialize=lambda:SimpleNamespace(rc=1,ret=1,outputs={})
        self.assertEqual(m.MemoryCore(core,'a'*32).phase,'new')

    def test_explicit_provision_restore_and_sign_are_separate(self):
        core=Core();adapter=m.MemoryCore(core,'a'*32)
        with self.assertRaises(m.CandidateBlocked):adapter.begin(b'synthetic-spim')
        self.assertEqual(core.calls,[])
        self.assertEqual(adapter.begin(b'synthetic-spim',consent=True),b'synthetic-cpim')
        saved=adapter.finish(b'synthetic-ptm',b'synthetic-tk',42)
        restored_core=Core();restored=m.MemoryCore(restored_core,'a'*32,saved=saved)
        headers,state=restored.headers()
        self.assertEqual(base64.b64decode(headers['X-Apple-I-MD']),b'synthetic-otp')
        self.assertEqual(saved,state);self.assertEqual(restored_core.calls,[])
        with self.assertRaises(m.CandidateBlocked):restored.begin(b'synthetic-spim',consent=True)

    def test_invalid_saved_state_never_provisions(self):
        for saved in ({},{'../outside':'YQ=='},{'adi.pb':'YQ=='},{'adi-000001F5.pb':'!'}):
            core=Core()
            with self.assertRaises(m.CandidateBlocked):m.MemoryCore(core,'a'*32,saved=saved)
            self.assertEqual(core.calls,[])

    def test_native_failure_cannot_be_replayed(self):
        core=Core();adapter=m.MemoryCore(core,'a'*32)
        core.provisioning_start=lambda *args:reply(-1)
        with self.assertRaises(m.CandidateBlocked):adapter.begin(b'synthetic',consent=True)
        with self.assertRaises(m.CandidateBlocked):adapter.begin(b'synthetic',consent=True)
        self.assertEqual(adapter.phase,'closed')

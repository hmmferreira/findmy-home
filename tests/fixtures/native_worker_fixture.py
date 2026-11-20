"""Synthetic protocol implementation loaded only by tests via patched script path.

The production worker still applies its real OS restrictions before invoking any
of these stand-ins. No test switch or synthetic backend exists in production.
"""
import ctypes
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import ModuleType,SimpleNamespace

APP=Path(__file__).resolve().parents[2]/"retrace/rootfs/app/retrace"
sys.path.insert(0,str(APP))
import native_worker_child

class Provider:
    _provisioning_session=None
    def __init__(self,options,signing):
        self.options=options;self.signed=0;self.provisioned=signing
        self.device=SimpleNamespace(unique_device_identifier="SYNTHETIC-UUID",server_friendly_description="Synthetic client",local_user_uuid="SYNTHETIC-LOCAL")
        self.adi=self
    @classmethod
    def load(cls,*files,**kwargs):
        libraries=files[-1].read()
        options=json.loads(libraries)
        provider=cls(options,len(files)==2)
        if options.get("expected_identity"):
            config=kwargs["default_device_config"]
            expected=options["expected_identity"]
            assert config.unique_device_id==expected["devid"].upper()
            assert config.local_user_uuid==expected["uid"]
            assert config.server_friendly_description==expected["client_info"]
            provider.device=SimpleNamespace(unique_device_identifier=config.unique_device_id,
                server_friendly_description=config.server_friendly_description,local_user_uuid=config.local_user_uuid)
        provider.check_boundary()
        return provider
    def check_boundary(self):
        # Landlock blocks both the supplied synthetic private sentinel and parent
        # process visibility. Nothing here reads a real session or host credential.
        for path in (self.options["private_path"],f"/proc/{os.getppid()}/environ"):
            try:
                with open(path,"rb") as stream:stream.read(1)
            except PermissionError:pass
            else:raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        for mutate in (lambda:os.chmod(self.options["private_path"],0o777),
                       lambda:os.utime(self.options["private_path"],(1,1))):
            try:mutate()
            except PermissionError:pass
            else:raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        try:
            with open(self.options["write_path"],"wb") as stream:stream.write(b"forbidden")
        except PermissionError:pass
        else:raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        for family in (socket.AF_INET,socket.AF_INET6,socket.AF_UNIX):
            try:s=socket.socket(family,socket.SOCK_STREAM)
            except PermissionError:pass
            else:s.close();raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        libc=ctypes.CDLL(None,use_errno=True)
        if libc.prctl(4,1,0,0,0)!=-1 or ctypes.get_errno()!=errno.EPERM:
            raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        try:os.kill(os.getppid(),0)
        except PermissionError:pass
        else:raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        try:subprocess.run(["/bin/true"],check=True)
        except PermissionError:pass
        else:raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        if "RETRACE_SYNTHETIC_PARENT_SECRET" in os.environ:raise RuntimeError("PRIVATE_BOUNDARY_FAILURE")
        # Public code remains readable, while native stdout/stderr are discarded.
        with open(native_worker_child.__file__,"rb") as stream:assert stream.read(1)
        print("PRIVATE_NATIVE_STDOUT",flush=True)
        print("PRIVATE_NATIVE_STDERR",file=sys.stderr,flush=True)
    def is_machine_provisioned(self,_):return self.provisioned
    def start_provisioning(self,dsid,spim):
        assert dsid==(1<<64)-2
        if spim==b"hang":time.sleep(60)
        if spim==b"fail":raise RuntimeError("PRIVATE_NATIVE_FAILURE")
        return SimpleNamespace(cpim=b"SYNTHETIC_CPIM",session=7)
    def end_provisioning(self,session,ptm,tk):
        assert session==7 and ptm==b"SYNTHETIC_PTM" and tk==b"SYNTHETIC_TK"
        self.provisioned=True
    def save(self,stream,exclude):
        assert exclude==["libs"]
        stream.write(f"SYNTHETIC_STATE_{self.signed}".encode())

class Engine:
    def __init__(self,provider):self.provider=provider
    @property
    def is_provisioned(self):return self.provider.provisioned
    def get_data(self):
        self.provider.signed+=1
        return {"X-Apple-I-MD":f"SYNTHETIC_OTP_{self.provider.signed}","X-Apple-I-MD-M":"SYNTHETIC_MACHINE"}

anisette=ModuleType("anisette");anisette.Anisette=Engine
provider_module=ModuleType("anisette._ani_provider");provider_module.AnisetteProvider=Provider
device_module=ModuleType("anisette._device")
class Config:
    @classmethod
    def default(cls):return SimpleNamespace(adi_id="synthetic-new-adi-id")
device_module.AnisetteDeviceConfig=Config
sys.modules["anisette"]=anisette;sys.modules["anisette._ani_provider"]=provider_module
sys.modules["anisette._device"]=device_module
native_worker_child.main()

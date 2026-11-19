"""Synthetic capability child. No account, SDK, artifact or secret contents."""
import ctypes
import errno
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys

MAX_MESSAGE=4096
CODE=Path(__file__).resolve().parent
sys.path.insert(0,str(CODE))
from native_sandbox import restrict_worker,SandboxUnavailable

CHECKS=("private_file_open_denied","private_write_denied","parent_proc_open_denied",
        "metadata_change_denied","ipv4_socket_denied","ipv6_socket_denied",
        "unix_socket_denied","exec_denied","parent_signal_denied","dumpability_change_denied")

def denied(operation):
    try:operation()
    except PermissionError:return True
    except OSError as exc:return exc.errno in (errno.EPERM,errno.EACCES)
    return False

def read_input():
    header=sys.stdin.buffer.read(4)
    if len(header)!=4:raise ValueError()
    size=struct.unpack("!I",header)[0]
    if not 0<size<=MAX_MESSAGE:raise ValueError()
    body=sys.stdin.buffer.read(size)
    if len(body)!=size:raise ValueError()
    value=json.loads(body)
    if not isinstance(value,dict) or set(value)!={"private_path","write_path"}:raise ValueError()
    if any(not isinstance(path,str) or not path.startswith("/tmp/") or len(path)>512 for path in value.values()):raise ValueError()
    return value

def main():
    try:
        values=read_input()
        restrict_worker([CODE,"/usr/lib","/usr/local/lib","/lib","/lib64","/etc/ld.so.cache","/dev/urandom"])
        def open_only(path,flags):
            fd=os.open(path,flags)
            os.close(fd)
        def create_socket(family):
            connection=socket.socket(family,socket.SOCK_STREAM)
            connection.close()  # No address resolution/connect or network traffic.
        libc=ctypes.CDLL(None,use_errno=True)
        def change_dumpability():
            if libc.prctl(4,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),"blocked")
        checks={
            "private_file_open_denied":denied(lambda:open_only(values["private_path"],os.O_RDONLY)),
            "private_write_denied":denied(lambda:open_only(values["write_path"],os.O_WRONLY|os.O_CREAT)),
            # Attempt opening only: no parent environment/process contents read.
            "parent_proc_open_denied":denied(lambda:open_only(f"/proc/{os.getppid()}/environ",os.O_RDONLY)),
            "metadata_change_denied":denied(lambda:os.chmod(values["private_path"],0o777)),
            "ipv4_socket_denied":denied(lambda:create_socket(socket.AF_INET)),
            "ipv6_socket_denied":denied(lambda:create_socket(socket.AF_INET6)),
            "unix_socket_denied":denied(lambda:create_socket(socket.AF_UNIX)),
            "exec_denied":denied(lambda:subprocess.run(["/bin/true"],check=True)),
            # Signal zero performs a permission check; it does not send a signal.
            "parent_signal_denied":denied(lambda:os.kill(os.getppid(),0)),
            "dumpability_change_denied":denied(change_dumpability),
        }
        return {"result":"supported" if all(checks.values()) else "restriction_failed","checks":checks}
    except SandboxUnavailable:
        return {"result":"boundary_unavailable"}
    except BaseException:
        return {"result":"probe_failed"}

if __name__=="__main__":
    data=json.dumps(main(),separators=(",",":")).encode()
    if 0<len(data)<=MAX_MESSAGE:
        sys.stdout.buffer.write(struct.pack("!I",len(data))+data)
        sys.stdout.buffer.flush()

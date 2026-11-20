"""One-shot diagnostic parent: synthetic temporary files, generic result only."""
import asyncio
import json
import os
from pathlib import Path
import signal
import struct
import sys
import tempfile

MAX_MESSAGE=4096
EXPECTED_CHECKS={"private_file_open_denied","private_write_denied","parent_proc_open_denied",
    "metadata_change_denied","ipv4_socket_denied","ipv6_socket_denied","unix_socket_denied",
    "exec_denied","parent_signal_denied","dumpability_change_denied"}

REASONS={"worker_platform_unsupported","worker_seccomp_unavailable","worker_landlock_unavailable",
    "worker_privilege_restriction_failed","worker_landlock_rule_failed","worker_landlock_restriction_failed",
    "worker_seccomp_rule_failed","worker_seccomp_restriction_failed","worker_seccomp_syscall_unavailable",
    "worker_apparmor_unavailable","worker_apparmor_profile_invalid","worker_apparmor_transition_failed",
    "unclassified_boundary_failure"}

def validate_result(value):
    if not isinstance(value,dict):raise ValueError()
    result=value.get("result")
    if result not in {"supported","restriction_failed","boundary_unavailable","probe_failed"}:raise ValueError()
    if result=="probe_failed":
        if set(value)=={"result"}:return value
        if set(value)!={"result","stage","error","errno"} or value.get("stage")!="child_restrictions_or_checks" or value.get("error") not in {"PermissionError","OSError","ValueError","RuntimeError","UnknownError"}:raise ValueError()
        if type(value["errno"]) is not int or not 0<=value["errno"]<=4095:raise ValueError()
        return value
    details=value.get("diagnostics")
    if not isinstance(details,dict) or set(details)!={"platform","uid","landlock_abi","landlock_errno","boundary_errno","boundary"}:raise ValueError()
    if details["boundary"] not in {"unavailable","landlock3-seccomp-v1","apparmor-seccomp-v1"}:raise ValueError()
    if details["platform"] not in {"linux-amd64","linux-arm64","unsupported"}:raise ValueError()
    if type(details["uid"]) is not int or not 0<=details["uid"]<=2**32-1:raise ValueError()
    if type(details["landlock_abi"]) is not int or not -1<=details["landlock_abi"]<=1024:raise ValueError()
    for key in ("landlock_errno","boundary_errno"):
        if type(details[key]) is not int or not 0<=details[key]<=4095:raise ValueError()
    if result in {"supported","restriction_failed"}:
        checks=value.get("checks")
        if set(value)!={"result","checks","diagnostics"} or not isinstance(checks,dict) or set(checks)!=EXPECTED_CHECKS or any(type(flag) is not bool for flag in checks.values()):raise ValueError()
        if (result=="supported")!=all(checks.values()):raise ValueError()
    elif set(value)!={"result","reason","diagnostics"} or value.get("reason") not in REASONS:raise ValueError()
    return value

SAFE_ERRORS={"PermissionError","OSError","TimeoutError","IncompleteReadError","JSONDecodeError","ValueError","CancelledError"}

def safe_failure(error,stage,child_exit=None):
    name=type(error).__name__
    number=getattr(error,"errno",0)
    return {"result":"probe_failed","stage":stage,"error":name if name in SAFE_ERRORS else "UnknownError",
        "errno":number if type(number) is int and 0<=number<=4095 else 0,
        "child_exit":child_exit if type(child_exit) is int and -255<=child_exit<=255 else None}

async def run_probe():
    if os.geteuid()!=1000:return {"result":"unexpected_uid"}
    process=None;stage="temporary_directory"
    try:
        with tempfile.TemporaryDirectory(prefix="findmy-capability-",dir="/tmp") as directory:
            stage="temporary_file"
            private=Path(directory)/"synthetic-private"
            private.write_bytes(b"synthetic probe data; not a credential")
            private.chmod(0o600)
            write=Path(directory)/"synthetic-write"
            request=json.dumps({"private_path":str(private),"write_path":str(write)},separators=(",",":")).encode()
            if len(request)>MAX_MESSAGE:raise ValueError()
            stage="spawn_child"
            process=await asyncio.create_subprocess_exec(sys.executable,"-I","-S","-B",str(Path(__file__).with_name("child.py")),
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
                close_fds=True,start_new_session=True,cwd="/",
                env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","PYTHONDONTWRITEBYTECODE":"1"})
            async with asyncio.timeout(15):
                stage="send_request"
                process.stdin.write(struct.pack("!I",len(request))+request)
                await process.stdin.drain();process.stdin.close()
                stage="read_header"
                size=struct.unpack("!I",await process.stdout.readexactly(4))[0]
                if not 0<size<=MAX_MESSAGE:raise ValueError()
                stage="read_body"
                value=json.loads(await process.stdout.readexactly(size))
                stage="wait_child"
                await process.wait()
                if process.returncode!=0:raise ValueError()
                stage="validate_response"
                return validate_result(value)
    except BaseException as error:
        return safe_failure(error,stage,process.returncode if process is not None else None)
    finally:
        if process is not None:
            if process.returncode is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            try:await asyncio.wait_for(process.wait(),2)
            except BaseException:pass
            if process.stdin is not None:process.stdin.close()

if __name__=="__main__":
    result=asyncio.run(run_probe())
    print(json.dumps({"probe":"findmy_runtime_probe","version":"0.1.3",**result},separators=(",",":")),flush=True)
    raise SystemExit(0 if result["result"]=="supported" else 1)

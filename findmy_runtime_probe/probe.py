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

async def run_probe():
    process=None
    try:
        with tempfile.TemporaryDirectory(prefix="findmy-capability-",dir="/tmp") as directory:
            private=Path(directory)/"synthetic-private"
            private.write_bytes(b"synthetic probe data; not a credential")
            private.chmod(0o600)
            write=Path(directory)/"synthetic-write"
            request=json.dumps({"private_path":str(private),"write_path":str(write)},separators=(",",":")).encode()
            if len(request)>MAX_MESSAGE:raise ValueError()
            process=await asyncio.create_subprocess_exec(sys.executable,"-I","-S","-B",str(Path(__file__).with_name("child.py")),
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
                close_fds=True,start_new_session=True,cwd="/",
                env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","PYTHONDONTWRITEBYTECODE":"1"})
            async with asyncio.timeout(15):
                process.stdin.write(struct.pack("!I",len(request))+request)
                await process.stdin.drain();process.stdin.close()
                size=struct.unpack("!I",await process.stdout.readexactly(4))[0]
                if not 0<size<=MAX_MESSAGE:raise ValueError()
                value=json.loads(await process.stdout.readexactly(size))
                await process.wait()
                if process.returncode!=0 or not isinstance(value,dict):raise ValueError()
                result=value.get("result")
                if result not in {"supported","restriction_failed","boundary_unavailable","probe_failed"}:raise ValueError()
                if result in {"supported","restriction_failed"}:
                    checks=value.get("checks")
                    if set(value)!={"result","checks"} or not isinstance(checks,dict) or set(checks)!=EXPECTED_CHECKS or any(type(flag) is not bool for flag in checks.values()):raise ValueError()
                    if (result=="supported")!=all(checks.values()):raise ValueError()
                elif set(value)!={"result"}:raise ValueError()
                return value
    except BaseException:
        return {"result":"probe_failed"}
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
    print(json.dumps({"probe":"findmy_runtime_probe","version":"0.1.0",**result},separators=(",",":")),flush=True)
    raise SystemExit(0 if result["result"]=="supported" else 1)

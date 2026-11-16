"""Local Portainer build/test helper. Never includes runtime data in build contexts."""
import argparse
import io
import json
import os
import re
from pathlib import Path
import struct
import tarfile
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument("mode",choices=["test","build","smoke"])
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
key=Path(os.environ.get("PORTAINER_KEY_FILE",Path.home()/".config/portainer/api-key")).read_text().strip()
base=os.environ.get("PORTAINER_DOCKER_API") or (Path.home()/".config/portainer/docker-api-url").read_text().strip()

def api(path,data=None,method=None):
    request=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),
        headers={"X-API-Key":key,"Content-Type":"application/json"},method=method)
    with urllib.request.urlopen(request,timeout=300) as response:
        data=response.read()
        return json.loads(data) if data else None

version=next(line.split(":",1)[1].strip() for line in (root/"findmy_home/config.yaml").read_text().splitlines() if line.startswith("version:"))
image="dragon/findmy-home-tests:"+version if args.mode=="test" else "dragon/findmy-home:"+version
if args.mode in ("test","build"):
    context=root if args.mode=="test" else root/"findmy_home"
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode="w") as tar:
        for path in sorted(context.rglob("*")):
            if any(part in (".git","__pycache__",".venv",".pytest_cache") for part in path.relative_to(context).parts):
                continue
            if path.is_file():
                tar.add(path,arcname=str(path.relative_to(context)))
    dockerfile="tools/test.Dockerfile" if args.mode=="test" else "Dockerfile"
    request=urllib.request.Request(base+"/build?t="+image+"&dockerfile="+dockerfile+"&rm=1",
        data=stream.getvalue(),headers={"X-API-Key":key,"Content-Type":"application/x-tar"},method="POST")
    with urllib.request.urlopen(request,timeout=1800) as response:
        for line in response:
            try: event=json.loads(line)
            except ValueError: continue
            if "error" in event: raise RuntimeError(event["error"])
            text=event.get("stream","").strip()
            if text and any(word in text for word in ("Step ","Successfully ","error","test result","Finished ")):
                print(text,flush=True)
if args.mode=="test":
    spec={"Image":image,"HostConfig":{"NetworkMode":"none","ReadonlyRootfs":True,
        "CapDrop":["ALL"],"SecurityOpt":["no-new-privileges:true"],"Tmpfs":{"/tmp":"rw,nosuid,size=128m"}}}
    cid=api("/containers/create",spec,"POST")["Id"]
    try:
        api("/containers/"+cid+"/start",{},"POST")
        result=api("/containers/"+cid+"/wait",{},"POST")
        request=urllib.request.Request(base+"/containers/"+cid+"/logs?stdout=1&stderr=1",headers={"X-API-Key":key})
        with urllib.request.urlopen(request,timeout=30) as response: raw=response.read()
        while len(raw)>=8:
            size=struct.unpack(">I",raw[4:8])[0]
            print(raw[8:8+size].decode(errors="replace"),end="")
            raw=raw[8+size:]
        print("Test exit:",result["StatusCode"])
        if result["StatusCode"]: raise SystemExit(result["StatusCode"])
    finally:
        api("/containers/"+cid+"?force=true",method="DELETE")

if args.mode=="smoke":
    spec={"Image":image,"User":"1000:1000","HostConfig":{"ReadonlyRootfs":True,"CapDrop":["ALL"],
        "SecurityOpt":["no-new-privileges:true"],"Tmpfs":{"/tmp":"rw,nosuid,size=64m","/data":"rw,nosuid,mode=1777,size=128m"}}}
    cid=api("/containers/create",spec,"POST")["Id"]
    try:
        api("/containers/"+cid+"/start",{},"POST")
        code="""import json,urllib.request,urllib.error,time,os,subprocess
from pathlib import Path
for _ in range(30):
 try:
  identity=json.loads(Path('/data/findmy_home/identity.json').read_text())
  req=urllib.request.Request('http://127.0.0.1:8100/v1/snapshot',headers={'Authorization':'Bearer '+identity['read_token']})
  with urllib.request.urlopen(req,timeout=3) as f: snapshot=json.load(f)
  break
 except Exception: time.sleep(1)
else: raise SystemExit('App startup failed')
assert snapshot['items']==[]
try:
 urllib.request.urlopen('http://127.0.0.1:8099/',timeout=3)
 raise AssertionError('Ingress trusted an untrusted peer')
except urllib.error.HTTPError as e: assert e.code==403
for _ in range(45):
 try:
  with urllib.request.urlopen('http://127.0.0.1:6969/',timeout=3) as f: assert f.status==200
  break
 except Exception: time.sleep(1)
else: raise SystemExit('Local helper not ready')
help=subprocess.run(['/usr/local/bin/findmy-export','--help'],capture_output=True,text=True,timeout=10)
assert help.returncode==0 and '--cached-only' in (help.stdout+help.stderr)
assert os.getuid()==1000
print('Smoke passed: non-root, private empty state, authenticated snapshot, ingress denied, local helper, patched exporter.')
"""
        eid=api("/containers/"+cid+"/exec",{"Cmd":["python","-c",code],"AttachStdout":True,"AttachStderr":True},"POST")["Id"]
        req=urllib.request.Request(base+"/exec/"+eid+"/start",data=b'{"Detach":false,"Tty":false}',
            headers={"X-API-Key":key,"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=110) as response: raw=response.read()
        while len(raw)>=8:
            size=struct.unpack(">I",raw[4:8])[0]
            print(raw[8:8+size].decode(errors="replace"),end="")
            raw=raw[8+size:]
        result=api("/exec/"+eid+"/json")
        print("Smoke exit:",result["ExitCode"])
        if result["ExitCode"]: raise SystemExit(result["ExitCode"])
    finally:
        api("/containers/"+cid+"?force=true",method="DELETE")

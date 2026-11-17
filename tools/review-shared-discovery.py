"""Developer-only prototype runner using the existing private Portainer configuration."""
import argparse,io,json,struct,subprocess,tarfile,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description="Offline runtime tests of the pinned discovery candidate; no production data")
parser.add_argument("backend",type=Path)
args=parser.parse_args()
backend=args.backend.resolve()
expected=json.loads((root/"experiments/shared-session/backend.json").read_text())["revision"]
revision=subprocess.check_output(["git","-C",str(backend),"rev-parse","HEAD"],text=True).strip()
if revision!=expected or subprocess.check_output(["git","-C",str(backend),"status","--porcelain"],text=True).strip():
 raise SystemExit("Backend must be a clean checkout at the reviewed revision")
key=(Path.home()/'.config/portainer/api-key').read_text().strip()
base=(Path.home()/'.config/portainer/docker-api-url').read_text().strip()
def api(path,data=None,method=None):
 req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'X-API-Key':key,'Content-Type':'application/json'},method=method)
 with urllib.request.urlopen(req,timeout=300) as r:
  raw=r.read();return json.loads(raw) if raw else None
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w') as tar:
 tar.add(root/'experiments/shared-session/Dockerfile',arcname='Dockerfile')
 tar.add(root/'findmy_home/requirements.lock',arcname='requirements.lock')
 tar.add(root/'tests/test_shared_discovery.py',arcname='test_shared_discovery.py')
 tar.add(root/'experiments/shared-session/test_controller_protocol.py',arcname='test_controller_protocol.py')
 for source,prefix in [(backend,'backend'),(root/'findmy_home/rootfs/app','app')]:
  for path in source.rglob('*'):
   if prefix=='backend' and path.relative_to(source).parts[0] not in ('findmy','tests','pyproject.toml','README.md','LICENSE.md'):continue
   if path.is_symlink():raise ValueError('Test context cannot contain symlinks')
   if any(x in ('.git','__pycache__','.venv','.pytest_cache') for x in path.relative_to(source).parts):continue
   if path.is_file():tar.add(path,arcname=str(Path(prefix)/path.relative_to(source)))
req=urllib.request.Request(base+'/build?t=dragon/findmy-shared-protocol-tests:prototype&rm=1',data=stream.getvalue(),headers={'X-API-Key':key,'Content-Type':'application/x-tar'},method='POST')
with urllib.request.urlopen(req,timeout=1800) as response:
 for line in response:
  event=json.loads(line)
  if 'error' in event:raise RuntimeError(event['error'])
  value=event.get('stream','').strip()
  if value and any(x in value for x in ('Step ','Successfully ','ERROR')):print(value,flush=True)
spec={'Image':'dragon/findmy-shared-protocol-tests:prototype','HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],'Tmpfs':{'/tmp':'rw,nosuid,size=256m'}}}
cid=api('/containers/create',spec,'POST')['Id']
try:
 api('/containers/'+cid+'/start',{},'POST')
 status=api('/containers/'+cid+'/wait',{},'POST')['StatusCode']
 req=urllib.request.Request(base+'/containers/'+cid+'/logs?stdout=1&stderr=1',headers={'X-API-Key':key})
 with urllib.request.urlopen(req,timeout=30) as r:raw=r.read()
 output=b''
 while len(raw)>=8:
  n=struct.unpack('>I',raw[4:8])[0];output+=raw[8:8+n];raw=raw[8+n:]
 # Results contain synthetic fixtures only; never mount real sessions into tests.
 print(output.decode()[-14000:])
 print('Test exit:',status)
 if status:raise SystemExit(status)
finally:api('/containers/'+cid+'?force=true',method='DELETE')

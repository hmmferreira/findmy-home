"""Private offline smoke: one fixed Apple library, no account or provisioning HTTP."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import urllib.request

p=argparse.ArgumentParser();p.add_argument('--library',type=Path,required=True);p.add_argument('--provision',action='store_true',help='Explicit anonymous Apple provisioning in a disposable container; never account login');args=p.parse_args()
library=args.library.read_bytes()
if hashlib.sha256(library).hexdigest()!='2eafc3c79c7f41a8afbfbeaaf23ee5dab5ad5bda55ec8e54dbc0ddf1d20ce630':raise ValueError('artifact_digest_mismatch')
key=(Path.home()/'.config/portainer/api-key').read_text().strip()
base=(Path.home()/'.config/portainer/docker-api-url').read_text().strip()
def call(path,data=None,method=None,content='application/json',raw=False):
    body=data if isinstance(data,bytes) else None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(base+path,data=body,headers={'X-API-Key':key,'Content-Type':content},method=method)
    with urllib.request.urlopen(req,timeout=90) as r:result=r.read()
    return result if raw else json.loads(result) if result else None
code='''import asyncio,base64
from pathlib import Path
from retrace.native_worker import _NativeChannel
async def main():
 channel=_NativeChannel()
 try:
  reply=await channel.exchange('mac_prepare',artifact=base64.b64encode(Path('/tmp/coreadi').read_bytes()).decode(),host_uuid='a'*32)
  assert reply=={'ok':True,'phase':'new'}
  print('Mac native smoke passed: restricted engine initialized offline, unprovisioned, no account sign-in.')
 except Exception as error:
  print('Native failure component:',getattr(error,'component','unknown'),'line:',getattr(error,'line',0))
  raise
 finally:await channel.close()
asyncio.run(main())
'''
if args.provision:
    code="""import asyncio,json
from pathlib import Path
from retrace.macos_runtime import provision
from retrace.macos_store import MachineStore
from retrace.macos_worker import MacSigner
from retrace.macos_artifact import LIBRARY_SHA
async def main():
 root=Path('/tmp/mac');root.mkdir(mode=0o700)
 library=root/'coreadi.bin';Path('/tmp/coreadi').rename(library)
 machine=await provision(library)
 store=MachineStore(root);store.save(machine)
 for _ in range(3):
  signer=MacSigner(library,json.dumps(store.load()).encode(),LIBRARY_SHA)
  try:
   await signer.initialize();headers=await signer.headers()
   assert set(headers)=={'X-Apple-I-MD','X-Apple-I-MD-M','X-Apple-I-MD-RINFO'}
  finally:await signer.close()
 print('Anonymous Mac provisioning and three cold signing/restoration cycles passed; no account login.')
try:asyncio.run(main())
except Exception as error:
 print('Smoke failed:',type(error).__name__,'component',getattr(error,'component','unknown'),'line',getattr(error,'line',0))
 raise SystemExit(1)
"""
image='dragon/retrace-shared-protocol-tests:prototype' if args.provision else 'dragon/retrace-tests:0.1.14'
spec={'Image':image,'User':'1000:1000','Cmd':['python','-c','import time;time.sleep(180)'],
      'HostConfig':{'NetworkMode':'bridge' if args.provision else 'none','CapDrop':['ALL'],
                    'SecurityOpt':['no-new-privileges:true']}}
cid=call('/containers/create',spec,'POST')['Id']
try:
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        info=tarfile.TarInfo('coreadi');info.size=len(library);info.uid=1000;info.gid=1000;info.mode=0o600
        tar.addfile(info,io.BytesIO(library))
    call('/containers/'+cid+'/archive?path=/tmp',stream.getvalue(),'PUT',content='application/x-tar',raw=True)
    call('/containers/'+cid+'/start',{},'POST')
    eid=call('/containers/'+cid+'/exec',{'Cmd':['python','-c',code],'User':'1000:1000','AttachStdout':True,'AttachStderr':True},'POST')['Id']
    raw=call('/exec/'+eid+'/start',{'Detach':False,'Tty':False},'POST',raw=True)
    while len(raw)>=8:
        size=struct.unpack('>I',raw[4:8])[0];print(raw[8:8+size].decode(),end='');raw=raw[8+size:]
    status=call('/exec/'+eid+'/json')['ExitCode']
    if status:raise SystemExit(status)
finally:call('/containers/'+cid+'?force=true',method='DELETE')

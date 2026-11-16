"""Build and validate a 0.1.0 -> 0.1.1 source patch; no runtime files."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tarfile,tempfile
root=Path(__file__).resolve().parents[1]
output=root.parent/"findmy-home-dist";output.mkdir(exist_ok=True)
name="findmy-home-polling-0.1.1"
files=["rootfs/app/findmy_home/apple.py","rootfs/app/findmy_home/worker.py",
       "rootfs/app/findmy_home/server.py","rootfs/app/findmy_home/static/app.js",
       "rootfs/app/findmy_home/static/index.html","CHANGELOG.md","config.yaml"]
with tempfile.TemporaryDirectory() as temp:
    base=Path(temp);stage=base/name;stage.mkdir()
    manifest=[]
    target=base/"test-app";target.mkdir()
    for relative in files:
        source=root/"findmy_home"/relative
        old=subprocess.run(["git","-C",str(root),"show","fa116d9:findmy_home/"+relative],capture_output=True)
        previous=old.stdout if old.returncode==0 else None
        if previous is not None:
            path=target/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(previous)
        dest=stage/"payload"/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        manifest.append({"path":relative,"old_sha256":hashlib.sha256(previous).hexdigest() if previous is not None else None,
                         "new_sha256":hashlib.sha256(source.read_bytes()).hexdigest()})
    (stage/"update-manifest.json").write_text(json.dumps(manifest,indent=2))
    shutil.copyfile(root/"tools/update-local.py",stage/"update.py")
    # Exercise the exact generated patch against the original code, then refusal to reapply.
    args=[sys.executable,str(stage/"update.py"),"--target",str(target),"--backup-root",str(base/"backup")]
    subprocess.run(args,check=True)
    subprocess.run(args+["--apply"],check=True)
    repeated=subprocess.run(args+["--apply"],capture_output=True)
    assert repeated.returncode!=0
    archive=output/(name+".tar.gz")
    with tarfile.open(archive,"w:gz") as tar:tar.add(stage,arcname=name)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name+".sha256").write_text(digest+"  "+archive.name+chr(10))
    print("Update archive:",archive,"SHA256:",digest)

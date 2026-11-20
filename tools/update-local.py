"""Apply a source-only app patch; preserve runtime data and back up old code."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def update(package,target,backup_root,apply=False):
    manifest=json.loads((package/"update-manifest.json").read_text())
    for item in manifest:
        relative=Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid patch path")
        source=package/"payload"/relative
        dest=target/relative
        if source.is_symlink() or dest.is_symlink() or digest(source)!=item["new_sha256"]:
            raise ValueError("Patch integrity check failed")
        if digest(dest)!=item["old_sha256"]:
            raise ValueError("Installed source differs from expected 0.1.0: "+str(relative))
    print("Verified patch files:",len(manifest))
    print("App source:",target)
    print("Runtime account, keys and locations: untouched")
    if not apply:
        print("Dry run only. Repeat with --apply to back up and replace app source.")
        return
    backup=backup_root/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup.mkdir(parents=True)
    applied=[]
    try:
        # config.yaml is last so the app store sees the new version after code is ready.
        for item in sorted(manifest,key=lambda i:i["path"]=="config.yaml"):
            relative=Path(item["path"]);source=package/"payload"/relative;dest=target/relative
            if dest.exists():
                saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
            dest.parent.mkdir(parents=True,exist_ok=True)
            fd,temp=tempfile.mkstemp(prefix=".findmy-patch-",dir=dest.parent)
            try:
                with os.fdopen(fd,"wb") as stream:
                    stream.write(source.read_bytes());stream.flush();os.fsync(stream.fileno())
                os.chmod(temp,0o644);os.replace(temp,dest)
            finally:
                Path(temp).unlink(missing_ok=True)
            applied.append(item)
    except Exception:
        for item in reversed(applied):
            relative=Path(item["path"]);dest=target/relative;saved=backup/relative
            if saved.exists():shutil.copy2(saved,dest)
            else:dest.unlink(missing_ok=True)
        raise
    print("Source patch applied. Code backup:",backup)
    print("Reload the app store and update Retrace to 0.1.1. Do not uninstall it.")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--target",type=Path)
    parser.add_argument("--backup-root",type=Path,default=Path("/config/findmy-home-code-backups"))
    args=parser.parse_args()
    target=args.target
    if target is None:
        mount=next((p for p in (Path("/local_apps"),Path("/addons")) if (p/"retrace").is_dir()),None)
        if mount is None:parser.exit(1,"Local app source mount not found"+chr(10))
        target=mount/"retrace"
    try:update(Path(__file__).resolve().parent,target,args.backup_root,args.apply)
    except (ValueError,OSError) as e:parser.exit(1,str(e)+chr(10))

if __name__=="__main__":main()

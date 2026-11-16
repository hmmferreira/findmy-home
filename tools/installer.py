#!/usr/bin/env python3
"""Install only the beta app/integration after verifying the local package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

def verify(root):
    manifest=json.loads((root/"SHA256SUMS.json").read_text())
    if not isinstance(manifest,dict):
        raise ValueError("Invalid manifest")
    allowed=set(manifest)|{"SHA256SUMS.json"}
    actual={str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    if actual != allowed:
        raise ValueError("Unexpected or missing package files")
    for name,expected in manifest.items():
        rel=Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Invalid package path")
        path=root/rel
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError("Package integrity check failed")
    return len(manifest)

def install(root,addon,component,apply=False):
    count=verify(root)
    for target in (addon,component):
        if target.exists() or target.is_symlink():
            raise ValueError("Beta target already exists; refusing to overwrite: "+str(target))
        parent=target.parent
        while not parent.exists() and parent != parent.parent:
            parent=parent.parent
        if not os.access(parent,os.W_OK):
            raise ValueError("Target parent is not writable: "+str(parent))
    print("Verified files:",count)
    print("App target:",addon)
    print("Integration target:",component)
    if not apply:
        print("Dry run only. Repeat with --apply to copy the two beta directories.")
        return
    staged=[]
    published=[]
    try:
        for source,target in ((root/"payload/findmy_home",addon),(root/"payload/custom_components/findmy_home",component)):
            target.parent.mkdir(parents=True,exist_ok=True)
            stage=Path(tempfile.mkdtemp(prefix=".findmy-home-stage-",dir=target.parent))
            staged.append(stage)
            shutil.copytree(source,stage/"content")
        for stage,target in zip(staged,(addon,component)):
            # Staging on each target filesystem makes each directory publication atomic.
            if target.exists() or target.is_symlink():
                raise ValueError("Target appeared during install")
            (stage/"content").rename(target)
            published.append(target)
    except Exception:
        for target in published:
            shutil.rmtree(target)
        raise
    finally:
        for stage in staged:
            shutil.rmtree(stage,ignore_errors=True)
    print("Copied beta code only. No services started and no Home Assistant restart performed.")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--addon-target",type=Path,default=None)
    parser.add_argument("--integration-target",type=Path,default=Path("/config/custom_components/findmy_home"))
    args=parser.parse_args()
    try:
        addon=args.addon_target
        if addon is None:
            mount=next((p for p in (Path("/local_apps"),Path("/addons")) if p.is_dir()),None)
            if mount is None:
                raise ValueError("No local app mount found: expected /local_apps or /addons in the editor")
            addon=mount/"findmy_home"
        install(Path(__file__).resolve().parent,addon,args.integration_target,args.apply)
    except (ValueError,OSError) as error:
        parser.exit(1,str(error)+chr(10))

if __name__=="__main__":
    main()

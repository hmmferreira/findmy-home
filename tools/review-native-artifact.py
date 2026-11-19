#!/usr/bin/env python3
"""Reproduce the release-pinned library bundle from a separately acquired APK.

Review/build utility only: no download, native execution, provisioning or approval.
Output is not a license grant or authorization to redistribute Apple's libraries.
"""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import tarfile
import zipfile

MANIFEST=Path(__file__).resolve().parents[1]/"findmy_home/rootfs/app/findmy_home/trusted_artifacts.json"
MAX_APK=200*1024*1024
MAX_LIBRARY=16*1024*1024


def bundle_from_apk(apk,entry):
    """Independent deterministic USTAR recipe; only the two pinned ELF members."""
    if hashlib.sha256(apk).hexdigest()!=entry["source"]["sha256"]:raise ValueError("source_digest_mismatch")
    if set(entry["bundle"]["member_sha256"])!={"lib/arm64-v8a/libCoreADI.so","lib/arm64-v8a/libstoreservicescore.so"}:
        raise ValueError("source_member_invalid")
    output=BytesIO()
    with zipfile.ZipFile(BytesIO(apk)) as archive,tarfile.open(fileobj=output,mode="w",format=tarfile.USTAR_FORMAT) as tar:
        names=archive.namelist()
        for name,digest in sorted(entry["bundle"]["member_sha256"].items()):
            if name not in ("lib/arm64-v8a/libCoreADI.so","lib/arm64-v8a/libstoreservicescore.so") or names.count(name)!=1:
                raise ValueError("source_member_invalid")
            info=archive.getinfo(name)
            if not 0<info.file_size<=MAX_LIBRARY:raise ValueError("source_member_invalid")
            value=archive.read(name)
            if hashlib.sha256(value).hexdigest()!=digest:raise ValueError("source_member_digest_mismatch")
            if value[:6]!=b"\x7fELF\x02\x01" or value[18:20]!=b"\xb7\x00":raise ValueError("source_architecture_invalid")
            member=tarfile.TarInfo("./libs/"+Path(name).name)
            member.size=len(value);member.mode=0o644;member.mtime=0
            tar.addfile(member,BytesIO(value))
        index=b'{"libs":"./libs"}'
        member=tarfile.TarInfo("fs.json");member.size=len(index);member.mode=0o644;member.mtime=0
        tar.addfile(member,BytesIO(index))
    return output.getvalue()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads(MANIFEST.read_text())
    entry=next(item for item in manifest["artifacts"] if item["id"]=="applemusic-arm64-v8a")
    fd=os.open(args.apk,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=MAX_APK:raise ValueError("source_file_invalid")
        source=stream.read(MAX_APK+1)
    bundle=bundle_from_apk(source,entry)
    digest=hashlib.sha256(bundle).hexdigest()
    if digest!=entry["bundle"]["sha256"]:raise ValueError("bundle_digest_mismatch")
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as stream:stream.write(bundle)
    print(json.dumps({"bundle_sha256":digest,"bundle_bytes":len(bundle),"review_status":entry["review_status"],"executed":False}))

if __name__=="__main__":main()

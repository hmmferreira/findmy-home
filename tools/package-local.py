"""Build a source-only package; runtime directories are never read."""
from pathlib import Path
import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
root=Path(__file__).resolve().parents[1]
output=root.parent/"retrace-dist"
output.mkdir(exist_ok=True)
name="retrace-local-0.1.0"
with tempfile.TemporaryDirectory() as temp:
    stage=Path(temp)/name
    stage.mkdir()
    for source,target in ((root/"retrace",stage/"payload/retrace"),
                          (root/"custom_components/findmy_home",stage/"payload/custom_components/findmy_home")):
        shutil.copytree(source,target,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    shutil.copyfile(root/"tools/installer.py",stage/"install.py")
    shutil.copytree(root/"docs",stage/"docs")
    shutil.copyfile(root/"README.md",stage/"README.md")
    hashes={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(stage.rglob("*")) if p.is_file()}
    (stage/"SHA256SUMS.json").write_text(json.dumps(hashes,indent=2))
    archive=output/(name+".tar.gz")
    with tarfile.open(archive,"w:gz") as tar: tar.add(stage,arcname=name)
    zip_path=output/(name+".zip")
    with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as zipper:
        for p in sorted(stage.rglob("*")):
            if p.is_file(): zipper.write(p,arcname=str(Path(name)/p.relative_to(stage)))
    for path in (archive,zip_path):
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(path.name+".sha256").write_text(digest+"  "+path.name+chr(10))
        print(path,"bytes:",path.stat().st_size,"SHA256:",digest)

"""Render an installable channel from source; never read runtime directories."""
import argparse
import json
from pathlib import Path
import re
import shutil


def render(source, target, channel, version):
    if channel not in ("edge", "stable"):
        raise ValueError("Unknown channel")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-dev\.[0-9]+\.[0-9]+)?", version):
        raise ValueError("Invalid version")
    if (channel == "edge") != ("-dev." in version):
        raise ValueError("Edge must use a development version")
    target.mkdir(parents=True, exist_ok=False)
    for name in ("findmy_home", "custom_components", "docs"):
        shutil.copytree(source/name, target/name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("README.md", "repository.yaml", "hacs.json", "LICENSE"):
        shutil.copyfile(source/name, target/name)
    config=target/"findmy_home/config.yaml"
    text=config.read_text()
    text=re.sub(r"(?m)^version:.*$", "version: "+version, text)
    title="Find My Home Edge" if channel=="edge" else "Find My Home"
    text=re.sub(r"(?m)^name:.*$", "name: "+title, text)
    text=re.sub(r"(?m)^panel_title:.*$", "panel_title: "+title, text)
    config.write_text(text)
    # Channel name alone never removes experimental status: live validation is required.
    repo=target/"repository.yaml"
    repo.write_text(repo.read_text().replace("Find My Home — development", "Find My Home — "+channel))
    manifest=target/"custom_components/findmy_home/manifest.json"
    data=json.loads(manifest.read_text())
    data["version"]=version
    manifest.write_text(json.dumps(data,indent=2)+"\n")
    (target/"CHANNEL.json").write_text(json.dumps({"channel":channel,"version":version},indent=2)+"\n")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("channel",choices=["edge","stable"])
    parser.add_argument("version")
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    render(Path(__file__).resolve().parents[1],args.output,args.channel,args.version)

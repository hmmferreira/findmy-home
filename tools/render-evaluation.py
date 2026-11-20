"""Render only a new side-by-side shared Edge app; preserve existing delivery."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('findmy_channel_renderer',ROOT/'tools/render-channel.py')
channels=importlib.util.module_from_spec(spec);spec.loader.exec_module(channels)

def render(source,target,version):
    target=Path(target)
    destination=target/'retrace_shared'
    if destination.exists():raise ValueError('Evaluation app already exists; review its update explicitly')
    target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='findmy-evaluation-') as tmp:
        stage=Path(tmp)/'rendered'
        channels.render(Path(source),stage,'edge',version,runtime='shared')
        app=stage/'retrace'
        config=app/'config.yaml'
        text=config.read_text()
        for key,value in (('slug','findmy_home_shared'),('name','Retrace Shared Edge'),('panel_title','Retrace Shared Edge')):
            text=re.sub(r'(?m)^'+key+r':.*$',key+': '+value,text)
        config.write_text(text)
        (app/'EVALUATION.json').write_text(json.dumps({'channel':'edge','scope':'side-by-side-private-evaluation','version':version},indent=2)+'\n')
        shutil.copytree(app,destination)
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('version');parser.add_argument('output',type=Path)
    args=parser.parse_args();render(ROOT,args.output,args.version)

"""Distinct encrypted Mac machine store. No access to the Android identity files."""
import asyncio
import json
import os
from pathlib import Path
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .private_session_store import _private_bytes,_write_new,_unique_pairs
from .storage import atomic_json
from .macos_identity import validate_machine
from .owned_session import SessionBlocked

AAD=b'retrace-macos-machine-v1'
class MachineStore:
    def __init__(self,root):self.root=Path(root)
    def exists(self):return (self.root/'machine.json').exists() or (self.root/'machine.json').is_symlink()
    def load(self):
        try:
            if self.root.is_symlink():raise ValueError()
            manifest=json.loads(_private_bytes(self.root/'machine.json',4096),object_pairs_hook=_unique_pairs)
            if set(manifest)!={'version','generation'} or type(manifest['version']) is not int or manifest['version']!=1:raise ValueError()
            generation=manifest['generation']
            import re
            if not isinstance(generation,str) or not re.fullmatch('[a-f0-9]{32}',generation):raise ValueError()
            key=_private_bytes(self.root/('machine-'+generation+'.key'),32)
            cipher=_private_bytes(self.root/('machine-'+generation+'.enc'),8*1024*1024)
            raw=AESGCM(key).decrypt(cipher[:12],cipher[12:],AAD)
            return validate_machine(json.loads(raw,object_pairs_hook=_unique_pairs))
        except Exception:raise SessionBlocked('signing_identity_invalid') from None
    def save(self,machine):
        validate_machine(machine)
        if self.root.is_symlink():raise SessionBlocked('session_storage_invalid')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True);self.root.chmod(0o700)
        generation=secrets.token_hex(16);key=secrets.token_bytes(32);nonce=secrets.token_bytes(12)
        payload=nonce+AESGCM(key).encrypt(nonce,json.dumps(machine,separators=(',',':')).encode(),AAD)
        _write_new(self.root/('machine-'+generation+'.key'),key)
        _write_new(self.root/('machine-'+generation+'.enc'),payload)
        atomic_json(self.root/'machine.json',{'version':1,'generation':generation})

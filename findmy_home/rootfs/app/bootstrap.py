"""Prepare an app-owned private directory, drop root, supervise helper + web worker."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

os.umask(0o077)
root = Path("/data/findmy_home")
root.mkdir(parents=True, exist_ok=True, mode=0o700)
if os.geteuid() == 0:
    os.chown(root, 1000, 1000)
    for directory, dirs, files in os.walk(root):
        os.chown(directory, 1000, 1000)
        os.chmod(directory, 0o700)
        for name in files:
            path = Path(directory) / name
            if path.is_symlink():
                raise RuntimeError("Symlinks are not allowed in private app state")
            os.chown(path, 1000, 1000)
            os.chmod(path, 0o600)
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)
os.environ["XDG_CONFIG_HOME"] = str(root / "config")
(root / "config").mkdir(exist_ok=True, mode=0o700)
state = root / "anisette"
state.mkdir(exist_ok=True, mode=0o700)
children = []
def stop(signum=None, frame=None):
    for child in children:
        child.terminate()
    for child in children:
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
children.append(subprocess.Popen(["/opt/anisette-v3-server", "--host", "127.0.0.1", "--adi-path", str(root / "config" / "anisette-v3")], cwd=state, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    env={key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR", "XDG_CONFIG_HOME") if key in os.environ}))
children.append(subprocess.Popen([sys.executable, "-m", "findmy_home.server"]))
while all(child.poll() is None for child in children):
    time.sleep(1)
stop()

"""Fetch version-pinned Leaflet distribution and record build hashes."""
from pathlib import Path
import hashlib
import json
import urllib.request
root = Path(__file__).resolve().parents[1] / "findmy_home/rootfs/app/findmy_home/static/vendor"
files = ["leaflet.js","leaflet.css","images/marker-icon.png","images/marker-icon-2x.png","images/marker-shadow.png","images/layers.png","images/layers-2x.png"]
hashes = {}
for name in files:
    data = urllib.request.urlopen("https://unpkg.com/leaflet@1.9.4/dist/" + name, timeout=30).read()
    path = root / name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    hashes[name] = hashlib.sha256(data).hexdigest()
(root / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2))
license_data = urllib.request.urlopen("https://unpkg.com/leaflet@1.9.4/LICENSE",timeout=30).read()
(root / "LICENSE").write_bytes(license_data)
print("Vendored Leaflet 1.9.4 assets; recorded SHA-256 hashes.")

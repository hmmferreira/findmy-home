"""Query public locked package versions only; never read private app state."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import re
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
def normalize(name):
    return re.sub(r"[-_.]+","-",name).lower()

def evaluate(results,exceptions,today=None):
    today=today or date.today()
    allowed=set()
    for entry in exceptions:
        if not entry.get("reason") or not entry.get("source") or date.fromisoformat(entry["expires"])<today:
            raise ValueError("Advisory applicability note is incomplete or expired")
        allowed.add((normalize(entry["package"]),entry["version"],entry["advisory"]))
    return [{"package":item["package"],"version":item["version"],"advisory":advisory}
            for item in results for advisory in item["advisories"]
            if (normalize(item["package"]),item["version"],advisory) not in allowed]

def query(group):
    payload={"queries":[{"package":{"name":name,"ecosystem":"PyPI"},"version":version} for name,version in group]}
    request=urllib.request.Request("https://api.osv.dev/v1/querybatch",data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(request,timeout=45) as response:
        values=json.load(response)["results"]
    if len(values)!=len(group):
        raise ValueError("Incomplete advisory response")
    return [{"package":name,"version":version,"advisories":[v["id"] for v in value.get("vulns",[])]}
            for (name,version),value in zip(group,values)]

def main():
    locks=[ROOT/"retrace/requirements.lock",ROOT/"retrace/requirements-shared.lock"]
    pins=[]
    for lock in locks:
        if lock.exists():pins.extend(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)",lock.read_text(),re.M))
    versions={}
    for name,version in pins:
        normalized=normalize(name)
        if normalized in versions and versions[normalized]!=version:raise ValueError("Runtime locks disagree")
        versions[normalized]=version
    pins=list(versions.items())
    if not pins: raise ValueError("Runtime lock is empty")
    groups=[pins[i:i+10] for i in range(0,len(pins),10)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=[item for group in pool.map(query,groups) for item in group]
    exceptions=json.loads((ROOT/"security/advisory-exceptions.json").read_text())
    findings=evaluate(results,exceptions)
    noted=sum(len(item["advisories"]) for item in results)-len(findings)
    print(json.dumps({"packages_checked":len(results),"unreviewed_findings":findings,"documented_applicability_notes":noted},indent=2))
    return 1 if findings else 0

if __name__=="__main__":
    raise SystemExit(main())

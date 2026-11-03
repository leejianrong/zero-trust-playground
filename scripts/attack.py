"""Run an attack through the observer and print the outcome. No name lists the attacks."""
import json
import sys
import urllib.error
import urllib.request

OBSERVER = "http://localhost:8765"


def call(path: str, method: str = "GET"):
    try:
        with urllib.request.urlopen(urllib.request.Request(OBSERVER + path, method=method), timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{e.code}: {e.read().decode()}")
    except OSError as e:
        sys.exit(f"cannot reach the observer on {OBSERVER} ({e}). Run `make observer`.")


if len(sys.argv) < 2:
    for a in call("/attacks"):
        print(f"{a['name']:<26} {a['title']}")
else:
    ev = call(f"/attacks/{sys.argv[1]}/run", "POST")["evidence"]
    print(f"{ev['attack']}: {ev['outcome'].upper()} (with no layers: {ev['expected']})")
    print(json.dumps(ev["detail"], indent=2))

from pathlib import Path

import yaml

from observer.adapters import TRAFFIC

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"


def http_services() -> set[tuple[str, str]]:
    """Every deployed workload that is launched by clinic.serve and so logs HTTP events."""
    found = set()
    for manifest in [DEPLOY / "clinic/app.yaml", DEPLOY / "agent.yaml"]:
        for doc in yaml.safe_load_all(manifest.read_text()):
            if doc and doc["kind"] == "Deployment":
                command = doc["spec"]["template"]["spec"]["containers"][0].get("command", [])
                if command[:3] == ["python", "-m", "clinic.serve"]:
                    found.add((doc["metadata"]["namespace"], doc["metadata"]["name"]))
    return found


def test_the_observer_watches_every_service_that_logs_http_events():
    watched = {(ns, app) for ns, apps in TRAFFIC.items() for app in apps}
    assert http_services() == watched

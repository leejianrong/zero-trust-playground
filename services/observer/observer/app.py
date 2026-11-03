import asyncio
import json
import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import adapters, links
from .normalize import event
from .store import Store

CATALOG = Path(__file__).resolve().parents[2] / "clinic/clinic/attacks/catalog.json"


async def kubectl_exec(namespace, deploy, *cmd) -> str:
    return await adapters.run(*adapters.KUBECTL, "-n", namespace, "exec", f"deploy/{deploy}", "--", *cmd)


def create_app(store: Store | None = None, sources=adapters.ALL, exec_in=kubectl_exec, catalog=CATALOG,
               probe_url=links.probe):
    store = store or Store("observer.db")
    attacks = {a["name"]: a for a in json.loads(Path(catalog).read_text())}

    def emit(ev):
        # Workload logs repeat on every reconnect; an SVID serial is only news once.
        serial = ev.get("evidence", {}).get("serial")
        if serial and store.has_serial(serial):
            return
        store.append(ev)

    @asynccontextmanager
    async def lifespan(_):
        tasks = [asyncio.create_task(src(emit)) for src in sources]
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="ztp observer", lifespan=lifespan)

    @app.get("/events")
    async def events(request: Request, since: int = 0, last_event_id: str | None = Header(None),
                     follow: bool = True, trace: str | None = None):
        cursor = max(since, int(last_event_id or 0))

        async def stream():
            nonlocal cursor
            while True:
                for ev in store.since(cursor, trace=trace):
                    cursor = ev["id"]
                    yield f"id: {ev['id']}\ndata: {json.dumps(ev)}\n\n"
                if not follow or await request.is_disconnected():
                    return
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/attacks")
    def list_attacks():
        return list(attacks.values())

    @app.post("/attacks/{name}/run")
    async def run_attack(name: str):
        attack = attacks.get(name)
        if not attack:
            raise HTTPException(404, f"unknown attack {name}")
        out = await exec_in("attacker", "attacker", "python", "-m", "clinic.attacks.run", name)
        try:
            result = json.loads(out.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            raise HTTPException(502, "attacker pod gave no result; is `make clinic` deployed?") from None
        verdict = "allow" if result["outcome"] == "succeeds" else "deny"
        ev = store.append(event("app", "attack_result", verdict, src="attacker", dst=attack["target"],
                                attack=name, outcome=result["outcome"], expected=attack["expected"]["all_off"],
                                detail=result["evidence"]))
        return ev

    @app.post("/app/use")
    async def use_app():
        patient = random.randint(1, 5)
        script = f"import urllib.request as u;print(u.urlopen('http://localhost:8080/visit/{patient}').status)"
        out = await exec_in("clinic", "web", "python", "-c", script)
        if out.strip() != "200":
            raise HTTPException(502, "web did not answer; is `make clinic` deployed?")
        return {"ok": True, "patient": patient}

    @app.get("/links")
    async def tool_links():
        return await links.check(probe_url=probe_url)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app

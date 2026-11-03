import asyncio
import json
import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import adapters, layers, links, network
from .normalize import event
from .store import Store

PAGE = 500  # events per store read; matches Store.since's default limit
CATALOG = Path(__file__).resolve().parents[2] / "clinic/clinic/attacks/catalog.json"


async def kubectl_exec(namespace, deploy, *cmd) -> str:
    return await adapters.run(*adapters.KUBECTL, "-n", namespace, "exec", f"deploy/{deploy}", "--", *cmd)


async def kubectl(*args) -> str:
    return await adapters.run(*adapters.KUBECTL, *args)


class ModeChange(BaseModel):
    mode: str


def create_app(store: Store | None = None, sources=adapters.ALL, exec_in=kubectl_exec, catalog=CATALOG,
               probe_url=links.probe, kube=kubectl, wait=asyncio.sleep, net=network):
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
                page = store.since(cursor, trace=trace)
                for ev in page:
                    cursor = ev["id"]
                    yield f"id: {ev['id']}\ndata: {json.dumps(ev)}\n\n"
                if await request.is_disconnected():
                    return
                if len(page) == PAGE:  # a full page means more history is waiting
                    continue
                if not follow:
                    return
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def stopped_by(trace: str | None, phase: str | None, target: str, modes: dict) -> str | None:
        """The layer of the first deny recorded under the attack's trace id. Workload logs reach the store a moment
        after the request, so look a few times. A refusal at the TLS handshake has no request, so no event.
        A refused connection never reaches a workload, so there is nothing to wait for: if the network layer is
        enforced and covers the target, name it, as an inference (ADR-0011)."""
        if phase == "connect":
            return "network (inferred)" if modes["network"] == "enforce" and net.protects(target) else None
        for _ in range(6 if trace else 0):
            denies = [e for e in store.since(trace=trace) if e["verdict"] == "deny" and e["kind"] != "attack_result"]
            if denies:
                return denies[0]["layer"]
            await wait(0.5)
        return None

    @app.get("/attacks")
    def list_attacks():
        return list(attacks.values())

    @app.post("/attacks/{name}/run")
    async def run_attack(name: str):
        attack = attacks.get(name)
        if not attack:
            raise HTTPException(404, f"unknown attack {name}")
        origin = attack.get("from", {"namespace": "attacker", "deploy": "attacker"})
        out = await exec_in(origin["namespace"], origin["deploy"], "python", "-m", "clinic.attacks.run", name)
        try:
            result = json.loads(out.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            raise HTTPException(502, "attacker pod gave no result; is `make clinic` deployed?") from None
        modes = await current_modes()
        outcome, trace = result["outcome"], result.get("trace")
        expected = layers.expected(attack, modes)
        extra = {"stopped_by": await stopped_by(trace, result["evidence"].get("phase"), attack["target"], modes)} if outcome == "blocked" else {}
        return store.append(event("app", "attack_result", "allow" if outcome == "succeeds" else "deny", src=origin["deploy"],
                                  dst=attack["target"], trace=trace, attack=name, outcome=outcome, expected=expected,
                                  as_expected=outcome == expected, modes=modes, detail=result["evidence"], **extra))

    @app.post("/app/use")
    async def use_app():
        patient = random.randint(1, 5)
        script = f"import urllib.request as u;print(u.urlopen('http://localhost:8080/visit/{patient}').status)"
        out = await exec_in("clinic", "web", "python", "-c", script)
        if out.strip() != "200":
            raise HTTPException(502, "web did not answer; is `make clinic` deployed?")
        return {"ok": True, "patient": patient}

    async def cluster(fn):
        try:
            return await asyncio.to_thread(fn)
        except RuntimeError as e:
            raise HTTPException(502, f"kubectl failed: {e}") from e

    async def current_modes() -> dict:
        ns, name = layers.CONFIGMAP
        out = await kube("-n", ns, "get", "configmap", name, "-o", "json")
        if not out.strip():
            raise HTTPException(502, "layer-modes ConfigMap not found; is `make clinic` deployed?")
        applied = await cluster(net.applied)
        return {**layers.parse(out), "network": "enforce" if applied else "off"}

    @app.get("/layers")
    async def get_layers():
        return await current_modes()

    @app.put("/layers/{layer}")
    async def put_layer(layer: str, body: ModeChange):
        if layer not in layers.LAYERS:
            raise HTTPException(422, f"unknown layer {layer}; known: {', '.join(layers.LAYERS)}")
        if body.mode not in layers.MODES:
            raise HTTPException(422, f"unknown mode {body.mode}; use one of {', '.join(layers.MODES)}")
        before = await current_modes()
        if why := layers.refusal(before, layer, body.mode):
            raise HTTPException(409, why)
        if layer == "network":
            await cluster(net.apply if body.mode == "enforce" else net.remove)
        else:
            ns, name = layers.CONFIGMAP
            await kube("-n", ns, "patch", "configmap", name, "--type", "merge", "-p", layers.patch(layer, body.mode))
        if before[layer] != body.mode:
            store.append(event(layer, "layer_mode_changed", "info", src="learner", reason=f"{layer} set to {body.mode}",
                               before=before[layer], after=body.mode))
        return {**before, layer: body.mode}

    @app.get("/links")
    async def tool_links():
        return await links.check(probe_url=probe_url)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app

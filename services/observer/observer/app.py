import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request
from fastapi.responses import StreamingResponse

from . import adapters
from .store import Store


def create_app(store: Store | None = None, sources=(adapters.spire_entries, adapters.workload_logs)):
    store = store or Store("observer.db")

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
                     follow: bool = True):
        cursor = max(since, int(last_event_id or 0))

        async def stream():
            nonlocal cursor
            while True:
                for ev in store.since(cursor):
                    cursor = ev["id"]
                    yield f"id: {ev['id']}\ndata: {json.dumps(ev)}\n\n"
                if not follow or await request.is_disconnected():
                    return
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app

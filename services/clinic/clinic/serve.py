"""Run a service on a plain port (8080) and, if asked, an mTLS port (8443) in one process.

    python -m clinic.serve clinic.records_api:app --mtls

The mTLS listener starts once the workload holds an SVID, and the plain one never waits for it,
so a service is always reachable while the identity layer is off or SPIRE is slow."""
import asyncio
import contextlib
import signal
import sys

import uvicorn
from uvicorn.importer import import_from_string

from clinic.common import _runtime
from clinic.mtls import PEERS, protocol_class, ssl_context_factory


class Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self):  # two servers share one process, so main() owns the signals
        yield


async def wait_for_identity():
    while not (identity := _runtime.get("identity")) or identity.material() is None:
        await asyncio.sleep(0.5)
    return identity.material


async def main(target: str, mtls: bool) -> None:
    app = import_from_string(target)
    servers = [Server(uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="warning"))]

    def stop():
        for s in servers:
            s.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop)
    tasks = [asyncio.create_task(servers[0].serve())]
    if mtls:
        material = await wait_for_identity()
        # The app's lifespan already runs under the plain server; running it twice would fail.
        servers.append(Server(uvicorn.Config(
            app, host="0.0.0.0", port=8443, log_level="warning", lifespan="off",
            http=protocol_class(PEERS), ssl_context_factory=ssl_context_factory(material))))
        tasks.append(asyncio.create_task(servers[1].serve()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], "--mtls" in sys.argv))

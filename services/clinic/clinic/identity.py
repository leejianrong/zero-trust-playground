"""A workload's own SPIFFE identity: fetched in the background, logged on every rotation.

The service keeps serving when it has no identity (the identity layer is off, or SPIRE has
no entry for it yet). `material()` is None until the first SVID arrives."""
import threading
import time
from datetime import datetime

from clinic.common import emit
from clinic.mtls import Material


def snapshot(workload: str, spiffe_id: str, leaf) -> dict:
    """The log line the observer turns into an identity event (same shape the echo spike used)."""
    return {
        "event": "x509_svid",
        "workload": workload,
        "spiffe_id": spiffe_id,
        "serial": format(leaf.serial_number, "x"),
        "not_before": leaf.not_valid_before_utc.isoformat(),
        "not_after": leaf.not_valid_after_utc.isoformat(),
        "observed_at": datetime.now().timestamp(),
    }


class Identity:
    def __init__(self, service: str, make_source=None, retry: float = 5.0):
        self.service = service
        self._make_source = make_source
        self._retry = retry
        self._source = None
        self._last_serial = None

    def material(self) -> Material | None:
        if self._source is None:
            return None
        from clinic.spiffe_material import current

        return current(self._source)()

    def _publish(self) -> None:
        svid = self._source.get_x509_context().default_svid
        snap = snapshot(self.service, str(svid.spiffe_id), svid.leaf)
        if snap["serial"] != self._last_serial:
            self._last_serial = snap["serial"]
            emit(**snap)

    def run(self) -> None:
        while self._source is None:
            try:
                make = self._make_source
                if make is None:
                    from spiffe import X509Source as make
                source = make()
                self._source = source
                self._publish()
                # py-spiffe calls subscribers with no arguments.
                source.subscribe_for_updates(self._publish)
            except Exception as exc:  # noqa: BLE001 - any failure means "no identity yet", retry
                self._source = None
                emit(event="identity_unavailable", service=self.service, error=str(exc)[:120])
                time.sleep(self._retry)

    def start(self) -> "Identity":
        threading.Thread(target=self.run, daemon=True).start()
        return self

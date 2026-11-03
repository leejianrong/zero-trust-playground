"""V1 spike workload: fetch SVIDs from the SPIFFE Workload API, log every rotation,
and expose the current identity on /identity. Replaced by the clinic services in V2."""
import json, logging, os, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer

from spiffe import JwtSource, X509Source

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("echo")
NAME = os.environ.get("WORKLOAD_NAME", "echo")
AUDIENCE = "playground-spike"

state = {"history": []}
lock = threading.Lock()


def record_x509(source):
    svid = source.get_x509_context().default_svid
    cert = svid.leaf
    snap = {
        "spiffe_id": str(svid.spiffe_id),
        "serial": format(cert.serial_number, "x"),
        "not_before": cert.not_valid_before_utc.isoformat(),
        "not_after": cert.not_valid_after_utc.isoformat(),
        "observed_at": time.time(),
    }
    with lock:
        if not state["history"] or state["history"][-1]["serial"] != snap["serial"]:
            state["history"].append(snap)
            log.info(json.dumps({"event": "x509_svid", "workload": NAME, **snap}))


def jwt_loop(jwt_source):
    while not jwt_source.is_closed():
        try:
            tok = jwt_source.fetch_svid(audience={AUDIENCE})
            log.info(json.dumps({"event": "jwt_svid", "workload": NAME,
                                 "spiffe_id": str(tok.spiffe_id), "expiry": tok.expiry}))
            with lock:
                state["jwt_expiry"] = tok.expiry
        except Exception as exc:  # keep the spike alive and visible
            log.info(json.dumps({"event": "jwt_error", "workload": NAME, "error": str(exc)}))
        time.sleep(30)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            body = json.dumps({"workload": NAME, **state}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    x509 = X509Source()
    record_x509(x509)
    # py-spiffe calls subscribers with no arguments; re-read the source inside.
    x509.subscribe_for_updates(lambda: record_x509(x509))
    jwt = JwtSource()
    threading.Thread(target=jwt_loop, args=(jwt,), daemon=True).start()
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()

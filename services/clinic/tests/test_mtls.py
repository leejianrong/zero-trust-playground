"""Spike (AAL-50): caller identity and live rotation on uvicorn, with no cluster."""
import datetime as dt
import socket
import threading
import time
from dataclasses import replace

import httpx
import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, Request

from clinic.mtls import (
    Material,
    Peers,
    client_context,
    peer_id,
    protocol_class,
    ssl_context_factory,
)

PEM = serialization.Encoding.PEM
NOKEY = serialization.NoEncryption()


class Ca:
    def __init__(self, name: str):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        self.cert = self._sign(self.name, self.key.public_key(), None, ca=True)

    def _sign(self, subject, pub, san, ca=False):
        now = dt.datetime.now(dt.UTC)
        b = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.name)
            .public_key(pub)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        )
        if san:
            b = b.add_extension(x509.SubjectAlternativeName(san), critical=False)
        return b.sign(self.key, hashes.SHA256())

    def issue(self, spiffe_id: str) -> Material:
        key = ec.generate_private_key(ec.SECP256R1())
        san = [x509.UniformResourceIdentifier(spiffe_id)]
        cert = self._sign(x509.Name([]), key.public_key(), san)
        return Material(
            chain_pem=cert.public_bytes(PEM).decode(),
            key_pem=key.private_bytes(PEM, serialization.PrivateFormat.PKCS8, NOKEY).decode(),
            bundle_pem=self.cert.public_bytes(PEM).decode(),
        )


def spiffe(name: str) -> str:
    return f"spiffe://playground.local/ns/clinic/sa/{name}"


@pytest.fixture
def server():
    ca = Ca("playground")
    state = {"server": ca.issue(spiffe("records-api")), "verify": True}
    peers = Peers()
    app = FastAPI()

    @app.get("/who")
    def who(request: Request):
        return {"caller": peers.caller(request.scope)}

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        http=protocol_class(peers),
        ssl_context_factory=ssl_context_factory(lambda: state["server"], lambda: state["verify"]),
    )
    srv = uvicorn.Server(config)
    state["apply"] = config.ssl_context_factory.apply
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.01)
    port = srv.servers[0].sockets[0].getsockname()[1]
    yield ca, state, f"https://localhost:{port}"
    srv.should_exit = True


def get(url, ca, me):
    with httpx.Client(verify=client_context(me)) as c:
        return c.get(url + "/who").json()["caller"]


def test_caller_is_the_spiffe_id_in_its_certificate(server):
    ca, _, url = server
    assert get(url, ca, ca.issue(spiffe("billing"))) == spiffe("billing")
    assert get(url, ca, ca.issue(spiffe("web"))) == spiffe("web")


def test_client_can_check_the_servers_spiffe_id(server):
    ca, _, url = server
    with httpx.Client(verify=client_context(ca.issue(spiffe("web")))) as c:
        assert peer_id(c.get(url + "/who")) == spiffe("records-api")


def test_no_certificate_connects_with_no_caller(server):
    ca, _, url = server
    assert get(url, ca, None) is None


def test_certificate_from_another_ca_fails_the_handshake(server):
    ca, _, url = server
    # The forger trusts the real bundle, so only the server can reject its certificate.
    forged = replace(Ca("forger").issue(spiffe("web")), bundle_pem=ca.cert.public_bytes(PEM).decode())
    # TLS 1.3 finishes the client side first, so the refusal shows up on the first request.
    with pytest.raises(httpx.TransportError) as err:
        get(url, ca, forged)
    assert "VERIFY_FAILED" not in str(err.value)  # the server refused it, not the client


def test_with_checking_off_a_forged_certificate_is_accepted_and_means_nothing(server):
    ca, state, url = server
    forged = replace(Ca("forger").issue(spiffe("web")), bundle_pem=ca.cert.public_bytes(PEM).decode())
    state["verify"] = False
    state["apply"]()
    assert get(url, ca, forged) is None  # connected, but the server never looked at the certificate
    state["verify"] = True  # the next connection is checked, with no restart
    state["apply"]()
    with pytest.raises(httpx.TransportError):
        get(url, ca, forged)


def test_rotated_server_certificate_reaches_new_connections_and_keeps_old_ones(server):
    ca, state, url = server
    verify = client_context(ca.issue(spiffe("web")))
    with httpx.Client(verify=verify) as long_lived:
        assert long_lived.get(url + "/who").json()["caller"] == spiffe("web")
        state["server"] = ca.issue(spiffe("records-api"))
        assert long_lived.get(url + "/who").json()["caller"] == spiffe("web")

    def served_serial() -> int:
        addr = ("127.0.0.1", int(url.rsplit(":", 1)[1]))
        with socket.create_connection(addr) as s, verify.wrap_socket(
            s, server_hostname="localhost"
        ) as t:
            return x509.load_der_x509_certificate(t.getpeercert(True)).serial_number

    before = served_serial()
    state["server"] = ca.issue(spiffe("records-api"))
    assert served_serial() != before


def test_each_concurrent_connection_keeps_its_own_identity(server):
    ca, _, url = server
    names = ["web", "billing", "agent", "records-mcp"]
    clients = [httpx.Client(verify=client_context(ca.issue(spiffe(n)))) for n in names]
    try:
        for _ in range(3):
            got = [c.get(url + "/who").json()["caller"] for c in clients]
            assert got == [spiffe(n) for n in names]
    finally:
        for c in clients:
            c.close()

"""mTLS for uvicorn with a rotating certificate and the caller's SPIFFE ID (ADR-0010).

uvicorn exposes no peer certificate to the ASGI app, so a protocol subclass reads it
after the handshake and records the SPIFFE ID under the client address. The app looks
it up from `scope["client"]`. The server certificate is swapped on a live listener by
the SNI callback, so rotation needs no restart.
"""
import os
import ssl
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

from uvicorn.protocols.http.h11_impl import H11Protocol


@dataclass
class Material:
    """What a workload holds: its certificate chain and key, and the bundle it trusts."""

    chain_pem: str
    key_pem: str
    bundle_pem: str


def spiffe_id_of(cert: dict | None) -> str | None:
    """The URI SAN of a verified peer certificate, or None if there is no usable one."""
    for kind, value in (cert or {}).get("subjectAltName", ()):
        if kind == "URI" and value.startswith("spiffe://"):
            return value
    return None


class Peers:
    """Caller identity by client address. The address is unique while the connection lives."""

    def __init__(self) -> None:
        self._by_addr: dict[tuple[str, int], str | None] = {}

    def set(self, addr: tuple[str, int] | None, spiffe_id: str | None) -> None:
        if addr:
            self._by_addr[addr] = spiffe_id

    def drop(self, addr: tuple[str, int] | None) -> None:
        self._by_addr.pop(addr, None) if addr else None

    def caller(self, scope: dict) -> str | None:
        return self._by_addr.get(tuple(scope["client"])) if scope.get("client") else None


PEERS = Peers()


def protocol_class(peers: Peers = PEERS) -> type[H11Protocol]:
    class PeerProtocol(H11Protocol):
        def connection_made(self, transport) -> None:  # type: ignore[override]
            super().connection_made(transport)
            tls = transport.get_extra_info("ssl_object")
            peers.set(self.client, spiffe_id_of(tls.getpeercert()) if tls else None)

        def connection_lost(self, exc) -> None:  # type: ignore[override]
            peers.drop(self.client)
            super().connection_lost(exc)

    return PeerProtocol


def _context(material: Material) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    # CERT_OPTIONAL: a client with no certificate still connects, so the app can log and
    # refuse it with a reason. A certificate that does not chain to the bundle fails the
    # handshake in every mode, because the connection cannot be attributed to anyone.
    ctx.verify_mode = ssl.CERT_OPTIONAL
    ctx.load_verify_locations(cadata=material.bundle_pem)
    load_chain(ctx, material)
    return ctx


def load_chain(ctx: ssl.SSLContext, material: Material) -> None:
    """ssl only loads certificates from files, so write the in-memory SVID to a private temp dir."""
    with tempfile.TemporaryDirectory() as d:
        cert, key = os.path.join(d, "c.pem"), os.path.join(d, "k.pem")
        with open(cert, "w") as f, open(key, "w") as g:
            f.write(material.chain_pem)
            g.write(material.key_pem)
        os.chmod(key, 0o600)
        ctx.load_cert_chain(cert, key)


def ssl_context_factory(current: Callable[[], Material], verify: Callable[[], bool] = lambda: True):
    """For uvicorn's `ssl_context_factory`. `current()` returns the latest material.

    The listener keeps one context. On every handshake the SNI callback installs a context
    built from the latest material, so a rotated SVID reaches new connections.

    Whether a client certificate is requested cannot be swapped that way: a connection keeps the
    verify mode of the listener's own context. `factory.apply()` sets it from `verify()`, and the
    caller runs it whenever the layer mode may have changed.
    """
    cache: dict[str, tuple[Material, ssl.SSLContext]] = {}
    listener: list[ssl.SSLContext] = []

    def latest() -> ssl.SSLContext:
        material = current()
        hit = cache.get("ctx")
        if not hit or hit[0] != material:
            cache["ctx"] = (material, _context(material))
        return cache["ctx"][1]

    def apply() -> None:
        for ctx in listener:
            ctx.verify_mode = ssl.CERT_OPTIONAL if verify() else ssl.CERT_NONE

    def factory(_config, _default) -> ssl.SSLContext:
        base = _context(current())
        base.verify_mode = ssl.CERT_OPTIONAL if verify() else ssl.CERT_NONE

        def swap(sock, _name, _ctx) -> None:
            sock.context = latest()

        base.sni_callback = swap
        listener.append(base)
        return base

    factory.apply = apply  # type: ignore[attr-defined]
    return factory


def client_context(material: Material | None) -> ssl.SSLContext:
    """A client context. SPIRE certificates carry a SPIFFE ID and no DNS name, so hostname
    checking is off and the caller must compare `peer_id` with the ID it expects."""
    ctx = ssl.create_default_context(cadata=material.bundle_pem if material else None)
    ctx.check_hostname = False
    if material:
        load_chain(ctx, material)
    else:  # no bundle to check the server against
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def peer_id(response) -> str | None:
    """The SPIFFE ID of the server that sent an httpx response."""
    tls = response.extensions["network_stream"].get_extra_info("ssl_object")
    return spiffe_id_of(tls.getpeercert()) if tls else None

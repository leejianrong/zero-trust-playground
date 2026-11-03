"""Turn the SPIFFE Workload API into `Material` for clinic.mtls, always the latest SVID."""
from cryptography.hazmat.primitives import serialization
from spiffe import X509Source

from clinic.mtls import Material

PEM = serialization.Encoding.PEM


def current(source: X509Source):
    """A `current()` callable for `ssl_context_factory` and `client_context`."""

    def material() -> Material:
        ctx = source.get_x509_context()
        svid = ctx.default_svid
        chain = b"".join(c.public_bytes(PEM) for c in svid.cert_chain)
        key = svid.private_key.private_bytes(
            PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        bundle = ctx.x509_bundle_set.get_bundle_for_trust_domain(svid.spiffe_id.trust_domain)
        roots = b"".join(a.public_bytes(PEM) for a in bundle.x509_authorities)
        return Material(chain.decode(), key.decode(), roots.decode())

    return material

import datetime as dt
import json
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from clinic.identity import Identity, snapshot


def leaf():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "x")])
    now = dt.datetime.now(dt.UTC)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(0xAB12).not_valid_before(now).not_valid_after(now + dt.timedelta(minutes=2))
            .sign(key, hashes.SHA256()))


def test_snapshot_has_what_the_observer_reads():
    snap = snapshot("billing", "spiffe://playground.local/ns/clinic/sa/billing", leaf())
    assert snap["event"] == "x509_svid" and snap["workload"] == "billing"
    assert snap["serial"] == "ab12" and snap["not_after"] > snap["not_before"]


class FakeSource:
    def get_x509_context(self):
        svid = SimpleNamespace(spiffe_id="spiffe://playground.local/ns/clinic/sa/billing", leaf=leaf())
        return SimpleNamespace(default_svid=svid)

    def subscribe_for_updates(self, callback):
        self.callback = callback


def test_a_service_without_an_identity_retries_and_logs_the_identity_once_it_has_one(capsys):
    attempts = iter([RuntimeError("no registration"), FakeSource()])

    def make_source():
        item = next(attempts)
        if isinstance(item, Exception):
            raise item
        return item

    ident = Identity("billing", make_source=make_source, retry=0)
    ident.run()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["event"] for line in lines] == ["identity_unavailable", "x509_svid"]
    assert lines[1]["spiffe_id"].endswith("/sa/billing")

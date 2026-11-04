import httpx

from clinic.modes import Modes


def modes_with(*responses):
    """A Modes whose ConfigMap reads return, in turn, a dict or raise the given error."""
    queue = list(responses)

    def fetch():
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return Modes("records-api", fetch=fetch)


def test_every_layer_starts_off():
    assert Modes("x", fetch=dict).get("mtls") == "off"


def test_a_changed_mode_is_followed_on_the_next_poll():
    m = modes_with({"mtls": "audit"}, {"mtls": "enforce"})
    m.refresh()
    assert m.get("mtls") == "audit"
    m.refresh()
    assert m.get("mtls") == "enforce"


def test_the_last_mode_stays_when_the_api_fails():
    m = modes_with({"mtls": "enforce"}, httpx.ConnectError("down"), OSError("no token"))
    m.refresh()
    m.refresh()
    m.refresh()
    assert m.get("mtls") == "enforce"


def test_a_value_that_is_not_a_mode_is_ignored():
    m = modes_with({"mtls": "audit"}, {"mtls": "yes please"})
    m.refresh()
    m.refresh()
    assert m.get("mtls") == "audit"


def test_a_starting_service_knows_the_modes_before_it_serves_anything(monkeypatch):
    # Otherwise a restarted pod runs as `off` for the first poll: a revoked password is tried, or mTLS is not asked for.
    monkeypatch.setattr("clinic.modes.os.path.exists", lambda path: True)
    m = Modes("records-api", fetch=lambda: {"mtls": "enforce", "secrets": "enforce"}, interval=3600).start()
    assert (m.get("mtls"), m.get("secrets")) == ("enforce", "enforce")

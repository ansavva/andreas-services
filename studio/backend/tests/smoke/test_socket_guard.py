"""The guard that lets this suite out of the house, and keeps it off the bill.

These two tests reach nothing and write nothing, which is deliberate: they pin
the *fixture*, so a regression shows up here rather than as five confusing
connection failures in `test_prod_api.py`.

The bug they exist for: `tests/conftest.py` autouses a `_no_outbound_sockets`
that refuses every non-loopback socket. `tests/integration/conftest.py` overrides
the name; this tree was added later and did not, so every test here died before
reaching the API and every prod deploy reported failure.
"""

import socket

import pytest

from tests.smoke.conftest import BILLING_HOSTS


def test_this_tree_may_resolve_a_name_the_unit_guard_would_refuse():
    """The override is in force, so the parent's loopback-only rule is not.

    Resolution only — no connection, no request. If the parent fixture were
    still the effective one this suite could not reach its own API, which is the
    entire failure this pins.
    """
    assert socket.getaddrinfo("localhost", 80)
    assert socket.gethostbyname("localhost")


@pytest.mark.parametrize("host", BILLING_HOSTS)
def test_a_model_provider_is_refused_by_name(host):
    """Denied at `getaddrinfo`, which is the only call that sees a hostname.

    `socket.create_connection` resolves first and hands `connect` the resolved
    address, so a denylist checked against `connect`'s argument compares against
    `('52.72.53.31', 443)` and can never match. That is not a subtlety worth
    rediscovering — hence a test that fails if the guard is moved back down.
    """
    with pytest.raises(RuntimeError, match="which bills"):
        socket.getaddrinfo(host, 443)

    with pytest.raises(RuntimeError, match="which bills"):
        socket.getaddrinfo(f"sub.{host}", 443)

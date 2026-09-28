"""Stage-2 suite v3 addition routed by the analyst (repair 1, part 1): capture at or just after expires_at."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from adv2 import W2, assert_error, fx2, new_key, parse_ts


def _wait_until(t):
    while datetime.now(timezone.utc) < t:
        time.sleep(0.005)


@pytest.mark.slow
@pytest.mark.obl("S2-057", "S2-067")
@pytest.mark.decision("D2-09")
@pytest.mark.parametrize("offset_ms", [0, 50, 250])
def test_capture_at_or_just_after_deadline(api, offset_ms, record_property):
    w = W2(api, fx2(authorization_ttl_seconds=1))
    a = w.authorize("ada", "bob", 2000).json
    exp = parse_ts(a["expires_at"])
    _wait_until(exp + timedelta(milliseconds=offset_ms))
    sent = datetime.now(timezone.utc)
    r = w.capture("bob", a["authorization_id"], {"amount": 100}, key=new_key())
    record_property("observation", f"sent {(sent - exp).total_seconds() * 1000:.1f} ms after expires_at -> {r.status}")
    assert_error(r, 409, "authorization_expired")
    assert w.held("ada") == 0 and w.me("bob")["total"] == 2500 and w.me("ada")["total"] == 10000

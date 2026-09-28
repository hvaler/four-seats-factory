"""Risk probes: optional robustness beyond the contract. A failure here is NOT a defect
unless the analyst's register makes it one; it is reported separately."""
import time

import pytest

from advlib import World, assert_error, fixture, new_key, user

pytestmark = pytest.mark.risk


@pytest.mark.obl("S1-013a")
def test_reset_100_users_under_10s(api):
    fx = fixture(users=[user(f"u_{i}", f"h{i}", 1) for i in range(100)], payments=[], requests=[],
                 settlement_operator_ids=[])
    t0 = time.monotonic()
    api.reset(fx)
    dt = time.monotonic() - t0
    assert dt < 10, dt
    assert api.login("h99@example.com")


@pytest.mark.obl("S1-043")
@pytest.mark.decision("D-31")
def test_non_integral_decimal_that_rounds_to_integer(w):
    raw = '{"to_handle":"bob","amount":1000.00000000000001}'
    r = w.api.call("POST", "/payments", raw=raw, token=w.tok["ada"], key=new_key())
    assert_error(r, 422, "validation_failed")


@pytest.mark.obl("S1-058")
@pytest.mark.parametrize("raw", ['{"to_handle":"bob","amount":1e400}', '{"to_handle":"bob","amount":-1e400}',
                                 '{"to_handle":"bob","amount":' + "9" * 400 + '}',
                                 '{"a":' + "[" * 5000 + "]" * 5000 + '}',
                                 '{"to_handle":"bob","amount":1,"note":"' + "x" * 200000 + '"}'])
def test_hostile_bodies_no_5xx(w, raw):
    r = w.api.call("POST", "/payments", raw=raw, token=w.tok["ada"], key=new_key())
    assert 400 <= r.status < 500, r
    assert w.bal("ada") == 10000


@pytest.mark.obl("S1-058")
def test_invalid_utf8_body_no_5xx(w):
    r = w.api.call("POST", "/payments", raw=b'{"to_handle":"bob","amount":1,"note":"\xff\xfe"}',
                   token=w.tok["ada"], key=new_key())
    assert 400 <= r.status < 500, r

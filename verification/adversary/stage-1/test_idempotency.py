"""§7 idempotency on the five write paths."""
import json

import pytest

from advlib import World, assert_error, fixture, new_key


def paths(w):
    """(token, path, valid body, different valid body, invalid body) per write path."""
    rq_a = w.api.request(w.tok["bob"], "ada", 5).json["request_id"]
    return {
        "payments": (w.tok["ada"], "/payments", {"to_handle": "bob", "amount": 100},
                     {"to_handle": "bob", "amount": 101}, {"to_handle": "bob", "amount": -5}),
        "requests": (w.tok["ada"], "/requests", {"payer_handle": "bob", "amount": 100},
                     {"payer_handle": "bob", "amount": 101}, {"payer_handle": "ghost", "amount": 1}),
        "pay": (w.tok["ada"], f"/requests/{rq_a}/pay", {"visibility": "private"},
                {"visibility": "public"}, {"visibility": "nope"}),
        "splits": (w.tok["ada"], "/splits", {"amount": 9, "participant_handles": ["ada", "bob"]},
                   {"amount": 8, "participant_handles": ["ada", "bob"]},
                   {"amount": 9, "participant_handles": []}),
        "settlements": (w.tok["op"], "/settlements",
                        {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 100}]},
                        {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 101}]},
                        {"transfers": []}),
    }


P = ["payments", "requests", "pay", "splits", "settlements"]


@pytest.mark.obl("S1-073", "S1-074", "S1-075", "S1-079", "S1-080")
@pytest.mark.parametrize("name", P)
def test_replay_conflict_and_invalid_body_on_claimed_key(w, name):
    tok, path, body, other, invalid = paths(w)[name]
    k = new_key()
    first = w.api.call("POST", path, body, token=tok, key=k)
    assert first.status == 201, first
    bal = w.balances()
    rep = w.api.call("POST", path, body, token=tok, key=k)
    assert rep.status == 200 and rep.json == first.json, rep
    assert_error(w.api.call("POST", path, other, token=tok, key=k), 409, "idempotency_key_reuse")
    assert_error(w.api.call("POST", path, invalid, token=tok, key=k), 409, "idempotency_key_reuse")
    assert w.balances() == bal


@pytest.mark.obl("S1-076")
@pytest.mark.parametrize("name", P)
def test_failed_key_is_reusable(w, name):
    tok, path, body, other, invalid = paths(w)[name]
    k = new_key()
    assert 400 <= w.api.call("POST", path, invalid, token=tok, key=k).status < 500
    r = w.api.call("POST", path, body, token=tok, key=k)
    assert r.status == 201, r


@pytest.mark.obl("S1-076", "S1-092")
def test_key_after_insufficient_funds_is_first_use(w):
    k = new_key()
    assert_error(w.api.pay(w.tok["cy"], "ada", 50, key=k), 409, "insufficient_funds")
    w.api.pay(w.tok["ada"], "cy", 50)
    r = w.api.pay(w.tok["cy"], "ada", 50, key=k)
    assert r.status == 201, r
    assert w.bal("cy") == 0


@pytest.mark.obl("S1-071")
def test_key_scoped_per_user_and_shared_across_sessions(w):
    k = new_key()
    ra = w.api.pay(w.tok["ada"], "cy", 10, key=k)
    rd = w.api.pay(w.tok["dee"], "cy", 10, key=k)
    assert ra.status == 201 and rd.status == 201
    assert ra.json["payment_id"] != rd.json["payment_id"]
    t2 = w.api.login("ada@example.com")
    rep = w.api.pay(t2, "cy", 10, key=k)
    assert rep.status == 200 and rep.json == ra.json, rep
    assert_error(w.api.pay(t2, "cy", 11, key=k), 409, "idempotency_key_reuse")
    assert w.bal("cy") == 20


@pytest.mark.obl("S1-072")
@pytest.mark.decision("D-19")
def test_key_namespace_includes_path(w):
    k = new_key()
    assert w.api.call("POST", "/payments", {"to_handle": "bob", "amount": 1}, token=w.tok["ada"], key=k).status == 201
    r = w.api.call("POST", "/requests", {"payer_handle": "bob", "amount": 1}, token=w.tok["ada"], key=k)
    assert r.status == 201, r
    r1 = w.api.request(w.tok["bob"], "ada", 3).json["request_id"]
    r2 = w.api.request(w.tok["bob"], "ada", 4).json["request_id"]
    k2 = new_key()
    assert w.api.pay_request(w.tok["ada"], r1, {}, key=k2).status == 201
    r = w.api.pay_request(w.tok["ada"], r2, {}, key=k2)
    assert r.status == 201 and r.json["amount"] == 4, r
    r = w.api.pay_request(w.tok["ada"], "rq_1", {"visibility": "private"}, key=k2)
    assert r.status == 201, r


@pytest.mark.obl("S1-072")
def test_same_key_same_body_different_path_succeeds(w):
    k = new_key()
    body = {"to_handle": "bob", "payer_handle": "bob", "amount": 2}
    assert w.api.call("POST", "/payments", body, token=w.tok["ada"], key=k).status == 201
    assert w.api.call("POST", "/requests", body, token=w.tok["ada"], key=k).status == 201


@pytest.mark.obl("S1-077", "S1-111")
def test_body_equality_is_json_value(w):
    k = new_key()
    first = w.api.call("POST", "/payments", raw='{"to_handle":"bob","amount":7,"note":"café"}',
                       token=w.tok["ada"], key=k)
    assert first.status == 201, first
    for raw in ['{ "amount" : 7 ,\n "note":"caf\\u00e9", "to_handle":"bob"}',
                '{"note":"café","amount":7,"to_handle":"bob"}']:
        r = w.api.call("POST", "/payments", raw=raw, token=w.tok["ada"], key=k)
        assert r.status == 200 and r.json == first.json, (raw, r)
    k2 = new_key()
    assert w.api.pay_request(w.tok["ada"], "rq_1", {}, key=k2).status == 201
    assert_error(w.api.pay_request(w.tok["ada"], "rq_1", {"visibility": "public"}, key=k2),
                 409, "idempotency_key_reuse")
    assert w.bal("ada") == 10000 - 7 - 1200


@pytest.mark.obl("S1-077")
@pytest.mark.decision("D-06")
def test_numeric_forms_equal_for_replay(w):
    k = new_key()
    first = w.api.call("POST", "/payments", raw='{"to_handle":"bob","amount":100}', token=w.tok["ada"], key=k)
    assert first.status == 201
    for raw in ['{"to_handle":"bob","amount":100.0}', '{"to_handle":"bob","amount":1e2}']:
        r = w.api.call("POST", "/payments", raw=raw, token=w.tok["ada"], key=k)
        assert r.status == 200 and r.json == first.json, (raw, r)


@pytest.mark.obl("S1-077")
@pytest.mark.decision("D-26")
def test_unknown_fields_count_for_equality(w):
    k = new_key()
    assert w.api.pay(w.tok["ada"], "bob", 5, key=k, extra=1).status == 201
    assert_error(w.api.pay(w.tok["ada"], "bob", 5, key=k), 409, "idempotency_key_reuse")


@pytest.mark.obl("S1-113", "S1-079")
def test_pay_replay_after_paid_and_after_balance_change(w):
    k = new_key()
    first = w.api.pay_request(w.tok["ada"], "rq_1", {"visibility": "private"}, key=k)
    assert first.status == 201
    w.api.pay(w.tok["ada"], "cy", 5000)
    rep = w.api.pay_request(w.tok["ada"], "rq_1", {"visibility": "private"}, key=k)
    assert rep.status == 200 and rep.json == first.json, rep
    assert w.bal("ada") == 10000 - 1200 - 5000 and w.bal("bob") == 3700


@pytest.mark.obl("S1-079")
def test_request_replay_after_cancel(w):
    k = new_key()
    first = w.api.request(w.tok["bob"], "ada", 50, key=k)
    w.api.call("POST", f"/requests/{first.json['request_id']}/cancel", token=w.tok["bob"])
    rep = w.api.request(w.tok["bob"], "ada", 50, key=k)
    assert rep.status == 200 and rep.json == first.json and rep.json["status"] == "pending", rep
    got = [x for x in w.api.requests(w.tok["bob"]).json["requests"]
           if x["request_id"] == first.json["request_id"]]
    assert len(got) == 1 and got[0]["status"] == "cancelled"
    assert len(w.api.requests(w.tok["bob"], limit=200).json["requests"]) == 2


@pytest.mark.obl("S1-057")
def test_key_length_bounds(w):
    assert w.api.pay(w.tok["ada"], "bob", 1, key="k" * 255).status == 201
    assert_error(w.api.pay(w.tok["ada"], "bob", 1, key="k" * 256), 422, "validation_failed")
    assert w.api.pay(w.tok["ada"], "bob", 1, key="x").status == 201
    assert w.bal("bob") == 2502


@pytest.mark.obl("S1-080")
def test_claimed_pay_key_resolved_before_state_checks(w):
    k = new_key()
    assert w.api.pay_request(w.tok["ada"], "rq_1", {}, key=k).status == 201
    # a different body on a request that is no longer pending: key reuse wins
    assert_error(w.api.pay_request(w.tok["ada"], "rq_1", {"visibility": "private"}, key=k),
                 409, "idempotency_key_reuse")

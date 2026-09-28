"""§11 atomic net settlements."""
import pytest

from advlib import World, assert_error, assert_ts, fixture, new_key, total, user


def settle(w, transfers, key=None, tok=None, raw=None):
    if raw is not None:
        return w.api.call("POST", "/settlements", raw=raw, token=tok or w.tok["op"], key=key or new_key())
    return w.api.call("POST", "/settlements", {"transfers": transfers},
                      token=tok or w.tok["op"], key=key or new_key())


def t(f, to, amount, **extra):
    return {"from_handle": f, "to_handle": to, "amount": amount, **extra}


@pytest.mark.obl("S1-198", "S1-193", "S1-200")
def test_settlement_happy_path(w):
    r = settle(w, [t("ada", "bob", 100, note="n1", visibility="private"), t("bob", "cy", 50)])
    assert r.status == 201, r
    s = r.json
    assert_ts(s["committed_at"]) and 1 <= len(s["settlement_id"]) <= 64
    ps = s["payments"]
    assert [(p["from_handle"], p["to_handle"], p["amount"]) for p in ps] == [("ada", "bob", 100), ("bob", "cy", 50)]
    assert ps[0]["note"] == "n1" and ps[0]["visibility"] == "private"
    assert ps[1]["note"] == "" and ps[1]["visibility"] == "public"
    for p in ps:
        assert p["settlement_id"] == s["settlement_id"] and p["request_id"] is None
        assert p["created_at"] == s["committed_at"] and p["currency"] == "EUR"
    assert len({p["payment_id"] for p in ps}) == 2
    assert w.bal("ada") == 9900 and w.bal("bob") == 2550 and w.bal("cy") == 50
    # feed: private member hidden from third parties and the operator
    ids = lambda h: {p["payment_id"] for p in w.api.activity(w.tok[h], limit=200).json["payments"]}
    assert ps[0]["payment_id"] in ids("ada") and ps[0]["payment_id"] in ids("bob")
    assert ps[0]["payment_id"] not in ids("cy") | ids("op") | ids("dee")
    assert ps[1]["payment_id"] in ids("dee") and ps[1]["payment_id"] in ids("op")
    feed_member = [p for p in w.api.activity(w.tok["cy"]).json["payments"]
                   if p["payment_id"] == ps[1]["payment_id"]][0]
    assert feed_member == ps[1]


@pytest.mark.obl("S1-196")
def test_net_affordability_not_sequential(w):
    # cy has 0: cy->dee 300 comes first, but ada->cy 300 later makes cy's net 0
    r = settle(w, [t("cy", "dee", 300), t("ada", "cy", 300)])
    assert r.status == 201, r
    assert w.bal("cy") == 0 and w.bal("dee") == 5300


@pytest.mark.obl("S1-196", "S1-197")
def test_net_short_by_one(w):
    k = new_key()
    before = w.balances()
    feed_before = w.api.activity(w.tok["dee"], limit=200).json["payments"]
    r = settle(w, [t("cy", "dee", 301), t("ada", "cy", 300)], key=k)
    assert_error(r, 409, "insufficient_funds")
    assert w.balances() == before
    assert w.api.activity(w.tok["dee"], limit=200).json["payments"] == feed_before
    r = settle(w, [t("cy", "dee", 300), t("ada", "cy", 300)], key=k)  # key not claimed
    assert r.status == 201, r


@pytest.mark.obl("S1-205")
def test_net_zero_cycle_duplicates_and_32_entries(api):
    fx = fixture(users=[user("u_a", "a", 0), user("u_b", "b", 0), user("u_o", "o", 0),
                        user("u_c", "c", 64)], payments=[], requests=[],
                 settlement_operator_ids=["u_o"])
    w = World(api, fx)
    r = settle(w, [t("a", "b", 100), t("b", "a", 100)], tok=w.tok["o"])
    assert r.status == 201, r
    r = settle(w, [t("c", "a", 1)] * 32, tok=w.tok["o"])
    assert r.status == 201 and len(r.json["payments"]) == 32, r
    assert w.bal("a") == 32 and w.bal("c") == 32
    assert_error(settle(w, [t("c", "a", 1)] * 33, tok=w.tok["o"]), 422, "validation_failed")
    # duplicates summed in the net: c has 32, two entries of 17 → short
    assert_error(settle(w, [t("c", "b", 17), t("c", "b", 17)], tok=w.tok["o"]), 409, "insufficient_funds")
    assert w.sum() == total(fx)


@pytest.mark.obl("S1-192", "S1-190")
def test_settlement_auth(w):
    body = [t("ada", "bob", 1)]
    assert_error(w.api.call("POST", "/settlements", {"transfers": body}, key=new_key()), 401, "unauthenticated")
    assert_error(settle(w, body, tok=w.tok["ada"]), 403, "forbidden")
    assert_error(w.api.call("POST", "/settlements", {"transfers": body}, token=w.tok["op"]), 400,
                 "missing_idempotency_key")


@pytest.mark.obl("S1-190")
def test_no_operator_when_field_absent(api):
    fx = fixture()
    del fx["settlement_operator_ids"]
    w = World(api, fx)
    for h in w.tok:
        assert_error(settle(w, [t("ada", "bob", 1)], tok=w.tok[h]), 403, "forbidden")


@pytest.mark.obl("S1-194", "S1-193")
@pytest.mark.decision("D-28")
@pytest.mark.parametrize("raw", ['{}', '{"transfers": null}', '{"transfers": {}}', '{"transfers": "x"}',
                                 '{"transfers": []}', '{"transfers": [1]}', '{"transfers": [null]}',
                                 '{"transfers": [["ada","bob",1]]}',
                                 '{"transfers": [{"from_handle": 1, "to_handle": "bob", "amount": 1}]}'])
def test_batch_shape_422(w, raw):
    assert_error(settle(w, None, raw=raw), 422, "validation_failed")


@pytest.mark.obl("S1-194", "S1-195")
def test_entry_errors(w):
    assert_error(settle(w, [t("ada", "ada", 1)]), 422, "self_payment")
    assert_error(settle(w, [t("ada", "ghost", 1)]), 404, "not_found")
    assert_error(settle(w, [t("ghost", "ada", 1)]), 404, "not_found")
    assert_error(settle(w, [t("ada", "bob", 0)]), 422, "validation_failed")
    assert_error(settle(w, [t("ada", "bob", "1")]), 422, "validation_failed")
    assert_error(settle(w, [t("ada", "bob", 1, note=None)]), 422, "validation_failed")
    assert_error(settle(w, [t("ada", "bob", 1, visibility="x")]), 422, "validation_failed")
    assert_error(settle(w, [t("ada", "bob", 1, note="n" * 201)]), 422, "validation_failed")
    # input order decides, and entry errors beat insufficient funds
    assert_error(settle(w, [t("ada", "ghost", 1), t("bob", "bob", 1)]), 404, "not_found")
    assert_error(settle(w, [t("bob", "bob", 1), t("ada", "ghost", 1)]), 422, "self_payment")
    assert_error(settle(w, [t("cy", "ada", 999999), t("ada", "ghost", 1)]), 404, "not_found")
    assert_error(settle(w, [t("cy", "ada", 999999), t("ada", "bob", 0)]), 422, "validation_failed")
    assert w.bal("ada") == 10000


@pytest.mark.obl("S1-195")
@pytest.mark.decision("D-28")
def test_within_entry_precedence(w):
    assert_error(settle(w, [t("ada", "ghost", 0)]), 422, "validation_failed")
    assert_error(settle(w, [t("ada", "ada", 0)]), 422, "validation_failed")


@pytest.mark.obl("S1-193", "S1-019")
def test_unknown_fields_ignored_in_entries(w):
    r = settle(w, [t("ada", "bob", 1, zzz=True)])
    assert r.status == 201, r


@pytest.mark.obl("S1-201", "S1-197")
def test_settlement_replay(w):
    k = new_key()
    body = [t("ada", "bob", 100), t("dee", "cy", 7)]
    first = settle(w, body, key=k)
    assert first.status == 201
    rep = settle(w, body, key=k)
    assert rep.status == 200 and rep.json == first.json, rep
    assert w.bal("ada") == 9900 and w.bal("cy") == 7


@pytest.mark.obl("S1-191")
def test_operator_gets_no_request_access(w):
    op = w.tok["op"]
    assert_error(w.api.pay_request(op, "rq_1"), 403, "forbidden")
    assert_error(w.api.call("POST", "/requests/rq_1/decline", token=op), 403, "forbidden")
    assert_error(w.api.call("POST", "/requests/rq_1/cancel", token=op), 403, "forbidden")
    assert w.api.requests(op).json["requests"] == []


@pytest.mark.obl("S1-202")
def test_reset_preserves_operator_from_fixture(api):
    w = World(api, fixture(settlement_operator_ids=["u_ada"]))
    assert settle(w, [t("bob", "cy", 1)], tok=w.tok["ada"]).status == 201
    assert_error(settle(w, [t("bob", "cy", 1)], tok=w.tok["op"]), 403, "forbidden")

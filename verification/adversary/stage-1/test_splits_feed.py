"""§8 POST /splits, §9 rounding, §4 feed contract, §8 GET /activity."""
import pytest

from advlib import World, assert_error, assert_ts, fixture, new_key, total, user


def split(api, tok, amount, handles, key=None, **extra):
    return api.call("POST", "/splits",
                    {"amount": amount, "participant_handles": handles, **extra},
                    token=tok, key=key or new_key())


def many_users(n, bal=0):
    return [user(f"u_{c}", c, bal) for c in ["ada", "bob", "cy", "dee", "eve", "fay", "gus"][:n]]


@pytest.mark.obl("S1-140", "S1-160")
@pytest.mark.parametrize("amount,n,shares", [(1000, 3, [334, 333, 333]), (1, 3, [1, 0, 0]),
                                             (10, 3, [4, 3, 3]), (999, 3, [333, 333, 333]),
                                             (5, 5, [1, 1, 1, 1, 1]),
                                             (1000000000, 7, [142857143] * 6 + [142857142]),
                                             (2, 7, [1, 1, 0, 0, 0, 0, 0])])
def test_split_table(api, amount, n, shares):
    fx = fixture(users=many_users(7), payments=[], requests=[], settlement_operator_ids=[])
    w = World(api, fx)
    handles = [u["handle"] for u in fx["users"]][:n]
    r = split(api, w.tok["ada"], amount, handles, note="dinner")
    assert r.status == 201, r
    s = r.json
    assert s["amount"] == amount and s["currency"] == "EUR" and s["note"] == "dinner"
    assert_ts(s["created_at"]) and 1 <= len(s["split_id"]) <= 64
    assert s["shares"] == [{"handle": h, "amount": a} for h, a in zip(handles, shares)]
    assert sum(x["amount"] for x in s["shares"]) == amount
    assert [x["payer_handle"] for x in s["requests"]] == handles[1:]
    assert [x["amount"] for x in s["requests"]] == shares[1:]
    for x in s["requests"]:
        assert x["requester_handle"] == "ada" and x["status"] == "pending"
        assert x["note"] == "dinner"


@pytest.mark.obl("S1-140")
def test_caller_omitted_gets_no_share(w):
    r = split(w.api, w.tok["ada"], 10, ["bob", "cy", "dee"])
    assert r.status == 201, r
    assert r.json["shares"] == [{"handle": "bob", "amount": 4}, {"handle": "cy", "amount": 3},
                                {"handle": "dee", "amount": 3}]
    assert [x["payer_handle"] for x in r.json["requests"]] == ["bob", "cy", "dee"]


@pytest.mark.obl("S1-140", "S1-161")
def test_caller_position_counts_for_remainder(w):
    r = split(w.api, w.tok["cy"], 10, ["ada", "cy", "bob"])
    assert [x["amount"] for x in r.json["shares"]] == [4, 3, 3]
    assert [(x["payer_handle"], x["amount"]) for x in r.json["requests"]] == [("ada", 4), ("bob", 3)]
    r = split(w.api, w.tok["cy"], 10, ["cy", "bob", "ada"])
    assert [(x["payer_handle"], x["amount"]) for x in r.json["requests"]] == [("bob", 3), ("ada", 3)]
    r = split(w.api, w.tok["cy"], 10, ["bob", "ada", "cy"])
    assert [(x["payer_handle"], x["amount"]) for x in r.json["requests"]] == [("bob", 4), ("ada", 3)]


@pytest.mark.obl("S1-142")
def test_split_only_caller(w):
    r = split(w.api, w.tok["cy"], 500, ["cy"])
    assert r.status == 201, r
    assert r.json["shares"] == [{"handle": "cy", "amount": 500}] and r.json["requests"] == []


@pytest.mark.obl("S1-141")
def test_split_validation(w):
    a = w.tok["ada"]
    assert_error(split(w.api, a, 3, []), 422, "validation_failed")
    assert_error(split(w.api, a, 3, ["bob", "bob"]), 422, "validation_failed")
    assert_error(split(w.api, a, 3, ["ada", "bob", "ada"]), 422, "validation_failed")
    assert_error(split(w.api, a, 0, ["bob"]), 422, "validation_failed")
    assert_error(split(w.api, a, 1000000001, ["bob"]), 422, "validation_failed")
    assert_error(split(w.api, a, 2.5, ["bob"]), 422, "validation_failed")
    assert_error(split(w.api, a, "3", ["bob"]), 422, "validation_failed")
    assert_error(split(w.api, a, 3, ["bob"], note="n" * 201), 422, "validation_failed")
    assert_error(split(w.api, a, 3, ["bob", "nobody"]), 404, "not_found")
    r = w.api.call("POST", "/splits", {"amount": 3}, token=a, key=new_key())
    assert_error(r, 422, "validation_failed")
    r = w.api.call("POST", "/splits", {"amount": 3, "participant_handles": "bob"}, token=a, key=new_key())
    assert_error(r, 400, "malformed_request")
    # nothing was created by any failure
    assert [x["request_id"] for x in w.api.requests(w.tok["bob"]).json["requests"]] == ["rq_1"]


@pytest.mark.obl("S1-144")
def test_split_unknown_handle_is_atomic(w):
    before = w.api.requests(w.tok["bob"]).json["requests"]
    assert_error(split(w.api, w.tok["ada"], 30, ["bob", "cy", "ghost"]), 404, "not_found")
    assert w.api.requests(w.tok["bob"]).json["requests"] == before
    assert w.api.requests(w.tok["cy"]).json["requests"] == []


@pytest.mark.obl("S1-143", "S1-145", "S1-144")
def test_zero_share_request_is_payable_and_decline_cancel_work(w):
    r = split(w.api, w.tok["ada"], 1, ["ada", "cy", "bob", "dee"])
    assert r.status == 201, r
    zero = {x["payer_handle"]: x for x in r.json["requests"]}
    assert all(x["amount"] == 0 for x in zero.values())
    p = w.api.pay_request(w.tok["cy"], zero["cy"]["request_id"])  # cy has balance 0
    assert p.status == 201, p
    assert p.json["amount"] == 0 and p.json["request_id"] == zero["cy"]["request_id"]
    d = w.api.call("POST", f"/requests/{zero['bob']['request_id']}/decline", token=w.tok["bob"])
    assert d.status == 200 and d.json["status"] == "declined"
    c = w.api.call("POST", f"/requests/{zero['dee']['request_id']}/cancel", token=w.tok["ada"])
    assert c.status == 200 and c.json["status"] == "cancelled"
    assert w.bal("cy") == 0


@pytest.mark.obl("S1-041", "S1-162")
def test_split_not_in_feed_and_paid_splits_conserve(api):
    fx = fixture(users=many_users(4, 10**6), payments=[], requests=[], settlement_operator_ids=[])
    w = World(api, fx)
    for amount, order in [(1000, ["ada", "bob", "cy"]), (7, ["cy", "bob", "dee", "ada"]),
                          (1, ["bob", "cy", "dee"]), (999999, ["dee", "cy"])]:
        r = split(api, w.tok["ada"], amount, order)
        assert r.status == 201
        for rq in r.json["requests"]:
            assert api.pay_request(w.tok[rq["payer_handle"]], rq["request_id"]).status == 201
    assert w.sum() == total(fx)
    # feed only contains the payments made by paying requests
    for h in w.tok:
        for p in api.activity(w.tok[h], limit=200).json["payments"]:
            assert p["request_id"] is not None


@pytest.mark.obl("S1-039", "S1-042", "S1-038", "S1-150", "S1-191")
def test_feed_contract(w):
    a, b, c = w.tok["ada"], w.tok["bob"], w.tok["cy"]
    pub = w.api.pay(a, "bob", 10, visibility="public").json
    prv = w.api.pay(a, "bob", 11, visibility="private").json
    prq = w.api.pay_request(a, "rq_1", {"visibility": "private"}).json
    w.api.request(b, "cy", 5)  # a request is never a feed item
    ids = lambda t: [p["payment_id"] for p in w.api.activity(t, limit=200).json["payments"]]
    for tok in (a, b):
        got = ids(tok)
        assert {pub["payment_id"], prv["payment_id"], prq["payment_id"], "p_1"} == set(got)
    for tok in (c, w.tok["dee"], w.tok["op"]):
        assert set(ids(tok)) == {pub["payment_id"], "p_1"}
    # the representation is the same for everybody who can see it
    def find(tok, pid):
        return [p for p in w.api.activity(tok, limit=200).json["payments"] if p["payment_id"] == pid][0]
    assert find(a, prv["payment_id"]) == find(b, prv["payment_id"]) == prv
    assert find(a, pub["payment_id"]) == find(c, pub["payment_id"]) == pub
    assert find(b, prq["payment_id"])["visibility"] == "private"
    feed = w.api.activity(a, limit=200).json["payments"]
    assert feed[-1]["payment_id"] == "p_1"  # D-32 seeded is oldest


@pytest.mark.obl("S1-039")
def test_private_seeded_payment_hidden_from_third_party(api):
    fx = fixture(payments=[{"id": "p_priv", "from_user_id": "u_ada", "to_user_id": "u_bob",
                            "amount": 1, "note": "secret", "visibility": "private"}])
    w = World(api, fx)
    assert [p["payment_id"] for p in api.activity(w.tok["bob"]).json["payments"]] == ["p_priv"]
    assert api.activity(w.tok["cy"]).json["payments"] == []
    assert api.activity(w.tok["op"]).json["payments"] == []

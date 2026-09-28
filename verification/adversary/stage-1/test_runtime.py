"""§3 runtime contract, §4 fixture, §5 error envelope."""
import pytest

from advlib import (PASSWORD, Api, World, assert_error, fixture, new_key,
                    total, user)


@pytest.mark.obl("S1-015")
def test_health(api):
    r = api.call("GET", "/health")
    assert r.status == 200 and r.json == {"status": "ok"}, r


@pytest.mark.obl("S1-017")
def test_content_type_on_success_and_error(w):
    ok = w.api.call("GET", "/me", token=w.tok["ada"])
    err = w.api.call("GET", "/me")
    for r in (ok, err, w.api.call("GET", "/health")):
        ct = r.headers.get("content-type", "").replace(" ", "").lower()
        assert ct.startswith("application/json"), r.headers
        assert "charset=utf-8" in ct, r.headers


@pytest.mark.obl("S1-016", "S1-179")
def test_reset_replaces_all_state(api):
    w1 = World(api, fixture())
    old_tok = w1.tok["ada"]
    k = new_key()
    assert api.pay(old_tok, "bob", 100, key=k).status == 201
    fx2 = fixture(users=[user("u_x", "xan", 700), user("u_y", "yol", 300)],
                  payments=[], requests=[], settlement_operator_ids=[])
    api.reset(fx2)
    assert_error(api.call("GET", "/me", token=old_tok), 401, "unauthenticated")
    r = api.call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD})
    assert_error(r, 401, "unauthenticated")
    t = api.login("xan@example.com")
    assert api.activity(t).json["payments"] == []
    assert api.requests(t).json["requests"] == []
    # the key used before reset is free again
    assert api.pay(t, "yol", 100, key=k).status == 201
    # repeated reset
    api.reset(fx2)
    t = api.login("xan@example.com")
    assert api.balance(t) == 700


@pytest.mark.obl("S1-047")
def test_negative_fixture_balance_rejected_and_state_kept(api):
    w1 = World(api, fixture())
    bad = fixture(users=[user("u_z", "zed", -1)], payments=[], requests=[],
                  settlement_operator_ids=[])
    r = api.call("POST", "/_test/reset", bad)
    assert_error(r, 422, "validation_failed")
    assert api.balance(w1.tok["ada"]) == 10000
    assert api.activity(w1.tok["ada"]).json["payments"][0]["payment_id"] == "p_1"


@pytest.mark.obl("S1-030", "S1-090")
@pytest.mark.parametrize("cur,mu", [("EUR", 2), ("JPY", 0), ("BHD", 3)])
def test_currency_declared_by_fixture(api, cur, mu):
    w1 = World(api, fixture(currency=cur, minor_units=mu))
    me = api.me(w1.tok["ada"])
    assert me == {"user_id": "u_ada", "display_name": "Ada", "handle": "ada",
                  "balance": 10000, "currency": cur, "minor_units": mu}
    r = api.pay(w1.tok["ada"], "bob", 1)
    assert r.status == 201 and r.json["currency"] == cur


@pytest.mark.obl("S1-044", "S1-046", "S1-045", "S1-199")
def test_seeded_records_visible(w):
    a = w.api.activity(w.tok["ada"]).json["payments"]
    assert len(a) == 1
    p = a[0]
    assert p["payment_id"] == "p_1" and p["from_user_id"] == "u_ada"
    assert p["to_user_id"] == "u_bob" and p["from_handle"] == "ada"
    assert p["to_handle"] == "bob" and p["amount"] == 500
    assert p["note"] == "coffee" and p["visibility"] == "public"
    assert p["request_id"] is None and p.get("settlement_id", "MISSING") is None
    rq = w.api.requests(w.tok["bob"]).json["requests"]
    assert [x["request_id"] for x in rq] == ["rq_1"]
    assert rq[0]["status"] == "pending" and rq[0]["amount"] == 1200
    assert w.bal("ada") == 10000 and w.bal("bob") == 2500


@pytest.mark.obl("S1-044", "S1-120", "S1-121")
def test_seeded_non_pending_requests_state_machine(api):
    fx = fixture(requests=[
        {"id": "rq_paid", "requester_id": "u_bob", "payer_id": "u_ada",
         "amount": 10, "note": "", "status": "paid"},
        {"id": "rq_dec", "requester_id": "u_bob", "payer_id": "u_ada",
         "amount": 10, "note": "", "status": "declined"},
        {"id": "rq_can", "requester_id": "u_bob", "payer_id": "u_ada",
         "amount": 10, "note": "", "status": "cancelled"},
    ])
    w = World(api, fx)
    a, b = w.tok["ada"], w.tok["bob"]
    assert_error(api.pay_request(a, "rq_paid"), 409, "request_not_pending")
    assert_error(api.call("POST", "/requests/rq_paid/decline", token=a), 409, "request_not_pending")
    assert_error(api.call("POST", "/requests/rq_paid/cancel", token=b), 409, "request_not_pending")
    r = api.call("POST", "/requests/rq_dec/decline", token=a)
    assert r.status == 200 and r.json["status"] == "declined", r
    assert_error(api.call("POST", "/requests/rq_dec/cancel", token=b), 409, "request_not_pending")
    assert_error(api.pay_request(a, "rq_dec"), 409, "request_not_pending")
    r = api.call("POST", "/requests/rq_can/cancel", token=b)
    assert r.status == 200 and r.json["status"] == "cancelled", r
    assert_error(api.call("POST", "/requests/rq_can/decline", token=a), 409, "request_not_pending")
    assert w.sum() == total(fx)


@pytest.mark.obl("S1-021")
def test_generated_ids_do_not_collide_with_seeded_ids(api):
    """R1-01: fixtures may use the same id shapes a generator would."""
    users = [user("u_ada", "ada", 10**7), user("u_bob", "bob", 0)]
    users += [user(f"u_{i}", f"n{i}", 0) for i in range(1, 6)]
    users += [user(str(i), f"m{i}", 0) for i in range(1, 4)]
    pays = [{"id": f"p_{i}", "from_user_id": "u_ada", "to_user_id": "u_bob",
             "amount": 1, "note": "", "visibility": "public"} for i in range(1, 21)]
    pays += [{"id": str(i), "from_user_id": "u_ada", "to_user_id": "u_bob",
              "amount": 1, "note": "", "visibility": "public"} for i in range(1, 6)]
    reqs = [{"id": f"rq_{i}", "requester_id": "u_bob", "payer_id": "u_ada",
             "amount": 1, "note": "", "status": "pending"} for i in range(1, 21)]
    reqs += [{"id": f"r_{i}", "requester_id": "u_bob", "payer_id": "u_ada",
              "amount": 1, "note": "", "status": "pending"} for i in range(1, 6)]
    fx = fixture(users=users, payments=pays, requests=reqs,
                 settlement_operator_ids=["u_ada"])
    w = World(api, fx)
    a, b = w.tok["ada"], w.tok["bob"]
    seeded_p = {p["id"] for p in pays}
    seeded_r = {r["id"] for r in reqs}
    seeded_u = {u["id"] for u in users}
    new_p, new_r = set(), set()
    for _ in range(25):
        r = api.pay(a, "bob", 1)
        assert r.status == 201, r
        new_p.add(r.json["payment_id"])
        r = api.request(b, "ada", 1)
        assert r.status == 201, r
        new_r.add(r.json["request_id"])
    r = api.pay_request(a, "rq_1")
    assert r.status == 201, r
    new_p.add(r.json["payment_id"])
    r = api.call("POST", "/splits", {"amount": 3, "participant_handles": ["ada", "bob"]},
                 token=a, key=new_key())
    assert r.status == 201, r
    new_r |= {x["request_id"] for x in r.json["requests"]}
    r = api.call("POST", "/settlements",
                 {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 1}] * 3},
                 token=a, key=new_key())
    assert r.status == 201, r
    new_p |= {x["payment_id"] for x in r.json["payments"]}
    new_u = set()
    for i in range(6):
        r = api.call("POST", "/auth/signup", {"email": f"sg{i}@example.com",
                                              "password": PASSWORD, "display_name": "S"})
        assert r.status == 201, r
        new_u.add(r.json["user_id"])
    assert len(new_p) == 25 + 1 + 3 and not (new_p & seeded_p), new_p & seeded_p
    assert len(new_r) == 26 and not (new_r & seeded_r), new_r & seeded_r
    assert len(new_u) == 6 and not (new_u & seeded_u), new_u & seeded_u
    ids = [p["payment_id"] for p in _all_activity(api, a)]
    assert len(ids) == len(set(ids)) == len(pays) + 29


def _all_activity(api, tok):
    out, off = [], 0
    while True:
        r = api.activity(tok, limit=200, offset=off)
        assert r.status == 200, r
        out += r.json["payments"]
        if not r.json["has_more"]:
            return out
        off += 200


@pytest.mark.obl("S1-050", "S1-019")
def test_error_envelope_unknown_route_and_method(w):
    r = w.api.call("GET", "/definitely-not-a-route", token=w.tok["ada"])
    assert 400 <= r.status < 500, r
    assert_error(r, r.status)
    r = w.api.call("DELETE", "/me", token=w.tok["ada"])
    assert 400 <= r.status < 500, r
    assert_error(r, r.status)


@pytest.mark.obl("S1-019")
def test_unknown_fields_and_query_params_ignored(w):
    r = w.api.pay(w.tok["ada"], "bob", 10, zzz={"a": 1}, amount_minor="x")
    assert r.status == 201, r
    r = w.api.activity(w.tok["ada"], foo="bar", limit=1)
    assert r.status == 200 and len(r.json["payments"]) == 1, r
    r = w.api.me(w.tok["ada"])


@pytest.mark.obl("S1-020", "S1-018")
def test_ids_and_timestamps(w):
    p = w.api.pay(w.tok["ada"], "bob", 10).json
    assert 1 <= len(p["payment_id"]) <= 64
    from advlib import assert_ts
    assert_ts(p["created_at"])
    rq = w.api.request(w.tok["bob"], "ada", 10).json
    assert 1 <= len(rq["request_id"]) <= 64
    assert_ts(rq["created_at"])


@pytest.mark.obl("S1-013")
def test_reset_within_10s(api):
    import time
    t0 = time.monotonic()
    api.reset(fixture())
    assert time.monotonic() - t0 < 10

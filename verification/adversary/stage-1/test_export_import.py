"""§10 export and import. Export bodies stay in memory and are never written out."""
import copy
import time

import pytest

from advlib import PASSWORD, World, assert_error, fixture, new_key, total, user


def populate(w):
    """Put state of every kind into w; return the receipts needed to check it later."""
    a, b = w.tok["ada"], w.tok["bob"]
    out = {}
    out["pay_key"] = new_key()
    out["pay"] = w.api.pay(a, "bob", 321, key=out["pay_key"], note="café \U0001F600",
                           visibility="private").json
    out["req_key"] = new_key()
    out["req"] = w.api.request(b, "cy", 77, key=out["req_key"]).json
    out["payreq_key"] = new_key()
    out["payreq"] = w.api.pay_request(a, "rq_1", {"visibility": "private"}, key=out["payreq_key"]).json
    out["split_key"] = new_key()
    out["split"] = w.api.call("POST", "/splits", {"amount": 10, "participant_handles": ["ada", "bob", "cy"]},
                              token=a, key=out["split_key"]).json
    out["set_key"] = new_key()
    out["set"] = w.api.call("POST", "/settlements",
                            {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 40}]},
                            token=w.tok["op"], key=out["set_key"]).json
    out["failed_key"] = new_key()
    assert w.api.pay(w.tok["cy"], "ada", 10**6, key=out["failed_key"]).status == 409
    sg = w.api.call("POST", "/auth/signup", {"email": "new.one@example.com", "password": "pw-new-user",
                                            "display_name": "Newbie"})
    assert sg.status == 201
    out["signup"] = sg.json
    w.api.call("POST", f"/requests/{out['req']['request_id']}/cancel", token=b)
    out["balances"] = w.balances()
    out["feed_ada"] = w.api.activity(a, limit=200).json
    out["feed_cy"] = w.api.activity(w.tok["cy"], limit=200).json
    out["reqs_bob"] = w.api.requests(b, limit=200).json
    return out


def verify_imported(api, w_tokens, out, fx):
    a, b = w_tokens["ada"], w_tokens["bob"]
    # old tokens work, balances and feeds identical
    for h, bal in out["balances"].items():
        assert api.balance(w_tokens[h]) == bal, h
    assert api.activity(a, limit=200).json == out["feed_ada"]
    assert api.activity(w_tokens["cy"], limit=200).json == out["feed_cy"]
    assert api.requests(b, limit=200).json == out["reqs_bob"]
    assert api.me(out["signup"]["token"])["display_name"] == "Newbie"
    # hashed-password login survives
    assert api.call("POST", "/auth/login", {"email": "new.one@example.com", "password": "pw-new-user"}).status == 200
    assert api.call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD}).status == 200
    # completed retries replay with the original bodies; conflicts still conflict
    r = api.pay(a, "bob", 321, key=out["pay_key"], note="café \U0001F600", visibility="private")
    assert r.status == 200 and r.json == out["pay"], r
    assert_error(api.pay(a, "bob", 322, key=out["pay_key"]), 409, "idempotency_key_reuse")
    r = api.request(b, "cy", 77, key=out["req_key"])
    assert r.status == 200 and r.json == out["req"], r
    r = api.pay_request(a, "rq_1", {"visibility": "private"}, key=out["payreq_key"])
    assert r.status == 200 and r.json == out["payreq"], r
    r = api.call("POST", "/splits", {"amount": 10, "participant_handles": ["ada", "bob", "cy"]},
                 token=a, key=out["split_key"])
    assert r.status == 200 and r.json == out["split"], r
    r = api.call("POST", "/settlements", {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 40}]},
                 token=w_tokens["op"], key=out["set_key"])
    assert r.status == 200 and r.json == out["set"], r
    # the operator permission survived; a failed key is still a first use
    r = api.call("POST", "/settlements", {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 1}]},
                 token=w_tokens["op"], key=new_key())
    assert r.status == 201, r
    r = api.pay(w_tokens["cy"], "ada", 1, key=out["failed_key"])
    assert r.status == 201, r
    # new ids don't collide with imported ones (S1-021)
    new = api.pay(a, "bob", 1).json["payment_id"]
    known = {p["payment_id"] for p in out["feed_ada"]["payments"]}
    assert new not in known
    newrq = api.request(b, "ada", 1).json["request_id"]
    assert newrq not in {x["request_id"] for x in out["reqs_bob"]["requests"]}
    sg = api.call("POST", "/auth/signup", {"email": "post.import@example.com", "password": PASSWORD,
                                          "display_name": "P"})
    assert sg.status == 201 and sg.json["user_id"] not in {u["id"] for u in fx["users"]} | {out["signup"]["user_id"]}
    total_now = sum(api.balance(t) for t in w_tokens.values()) + api.balance(out["signup"]["token"])
    assert total_now == total(fx)


@pytest.mark.obl("S1-170")
def test_export_shape(w):
    r = w.api.call("GET", "/_test/export")
    assert r.status == 200, r.status
    assert r.json["track"] == "pocketful" and r.json["format_version"] == 1
    assert isinstance(r.json["state"], dict)


@pytest.mark.obl("S1-171", "S1-173", "S1-176", "S1-177", "S1-021", "S1-180")
def test_import_same_container_round_trip(api):
    fx = fixture()
    w = World(api, fx)
    out = populate(w)
    t0 = time.monotonic()
    exp = api.call("GET", "/_test/export").json
    assert time.monotonic() - t0 < 10
    # mutate after export, then import twice: the export wins and nothing duplicates
    api.pay(w.tok["ada"], "dee", 5)
    for _ in range(2):
        t0 = time.monotonic()
        r = api.call("POST", "/_test/import", exp)
        assert r.status == 204, r
        assert time.monotonic() - t0 < 10
    verify_imported(api, w.tok, out, fx)


@pytest.mark.obl("S1-175")
def test_export_is_a_snapshot(w):
    e1 = w.api.call("GET", "/_test/export").json
    w.api.pay(w.tok["ada"], "bob", 1)
    # the earlier snapshot still restores the pre-payment state
    assert w.api.call("POST", "/_test/import", e1).status == 204
    assert w.bal("ada") == 10000 and w.bal("bob") == 2500
    assert len(w.api.activity(w.tok["ada"]).json["payments"]) == 1


@pytest.mark.obl("S1-174")
@pytest.mark.parametrize("mut", ["no_state", "no_track", "no_version", "track", "version2",
                                 "version_str", "state_str", "state_list"])
def test_invalid_import_rejected_and_state_kept(w, mut):
    exp = w.api.call("GET", "/_test/export").json
    bad = copy.deepcopy(exp)
    if mut == "no_state":
        del bad["state"]
    elif mut == "no_track":
        del bad["track"]
    elif mut == "no_version":
        del bad["format_version"]
    elif mut == "track":
        bad["track"] = "tablekeeper"
    elif mut == "version2":
        bad["format_version"] = 2
    elif mut == "version_str":
        bad["format_version"] = "1"
    elif mut == "state_str":
        bad["state"] = "x"
    elif mut == "state_list":
        bad["state"] = []
    w.api.pay(w.tok["ada"], "bob", 9)
    r = w.api.call("POST", "/_test/import", bad)
    assert_error(r, 422, "validation_failed")
    assert w.bal("ada") == 9991


@pytest.mark.obl("S1-174")
@pytest.mark.decision("D-23")
def test_empty_state_object_rejected(w):
    exp = w.api.call("GET", "/_test/export").json
    exp["state"] = {}
    assert_error(w.api.call("POST", "/_test/import", exp), 422, "validation_failed")
    assert w.bal("ada") == 10000


@pytest.mark.obl("S1-174")
def test_import_unparseable(w):
    assert_error(w.api.call("POST", "/_test/import", raw="{nope"), 400, "malformed_request")
    assert w.bal("ada") == 10000


@pytest.mark.obl("S1-179")
def test_reset_clears_imported_state(api):
    w = World(api, fixture())
    exp = api.call("GET", "/_test/export").json
    api.call("POST", "/_test/import", exp)
    fx2 = fixture(users=[user("u_q", "q", 1)], payments=[], requests=[], settlement_operator_ids=[])
    api.reset(fx2)
    assert_error(api.call("GET", "/me", token=w.tok["ada"]), 401, "unauthenticated")


@pytest.mark.xc
@pytest.mark.obl("S1-172", "S1-176", "S1-177", "S1-178", "S1-202", "S1-021")
def test_cross_container_import(api, api_b):
    fx = fixture()
    w = World(api, fx)
    out = populate(w)
    exp = api.call("GET", "/_test/export").json
    # B has its own unrelated state and credentials
    fxb = fixture(users=[user("u_ada", "ada", 1), user("u_zed", "zed", 5)], payments=[], requests=[],
                  settlement_operator_ids=["u_zed"])
    wb = World(api_b, fxb)
    r = api_b.call("POST", "/_test/import", exp)
    assert r.status == 204, r
    assert_error(api_b.call("GET", "/me", token=wb.tok["zed"]), 401, "unauthenticated")
    assert_error(api_b.call("GET", "/me", token=wb.tok["ada"]), 401, "unauthenticated")
    assert api_b.call("POST", "/auth/login", {"email": "zed@example.com", "password": PASSWORD}).status == 401
    # A keeps running independently and is unaffected by B's later writes
    verify_imported(api_b, w.tok, out, fx)
    assert api.balance(w.tok["ada"]) == out["balances"]["ada"]

"""Stage-2 API rows: /me, authorizations, captures, voids, expiry, holds, negotiation, reset."""
import time
from datetime import timedelta

import pytest

from adv2 import (W2, assert_error, assert_ts, auth_rec, fx2, hours, new_key, parse_ts, total, user)

AUTH_KEYS = {"authorization_id", "from_user_id", "from_handle", "to_user_id", "to_handle", "amount",
             "captured_amount", "currency", "note", "visibility", "status", "expires_at",
             "payment_id", "payment_ids", "remaining_amount", "created_at"}


# --- GET /me -----------------------------------------------------------------------------

@pytest.mark.obl("S2-052", "S1-090")
def test_me_fields_without_holds(w):
    me = w.me("ada")
    assert me["balance"] == me["total"] == me["available"] == 10000 and me["held"] == 0, me
    assert {"user_id", "display_name", "handle", "currency", "minor_units"} <= set(me)


@pytest.mark.obl("S2-052", "S2-050", "S1-001")
def test_hold_moves_no_money(w):
    r = w.authorize("ada", "bob", 2000, note="deposit", visibility="private")
    assert r.status == 201, r
    a, b = w.me("ada"), w.me("bob")
    assert (a["balance"], a["total"], a["available"], a["held"]) == (10000, 10000, 8000, 2000), a
    assert (b["total"], b["available"], b["held"]) == (2500, 2500, 0), b
    assert w.totals() == total(w.fx)


# --- POST /authorizations ----------------------------------------------------------------

@pytest.mark.obl("S2-058", "S2-055")
def test_authorization_shape_and_expiry_arithmetic(w):
    r = w.authorize("ada", "bob", 2000, note="deposit", visibility="private")
    a = r.json
    assert set(a) >= AUTH_KEYS, AUTH_KEYS - set(a)
    assert a["from_user_id"] == "u_ada" and a["from_handle"] == "ada"
    assert a["to_user_id"] == "u_bob" and a["to_handle"] == "bob"
    assert (a["amount"], a["captured_amount"], a["remaining_amount"]) == (2000, 0, 2000)
    assert a["status"] == "open" and a["payment_id"] is None and a["payment_ids"] == []
    assert a["currency"] == "EUR" and a["note"] == "deposit" and a["visibility"] == "private"
    assert_ts(a["created_at"]) and assert_ts(a["expires_at"])
    assert parse_ts(a["expires_at"]) - parse_ts(a["created_at"]) == timedelta(seconds=600)


@pytest.mark.obl("S2-058")
def test_authorization_defaults(w):
    a = w.authorize("ada", "bob", 1).json
    assert a["note"] == "" and a["visibility"] == "public"


@pytest.mark.obl("S2-059", "S1-002")
def test_authorization_errors(w):
    assert_error(w.authorize("ada", "bob", 10001), 409, "insufficient_funds")
    assert w.authorize("ada", "bob", 6000).status == 201
    assert_error(w.authorize("ada", "cy", 4001), 409, "insufficient_funds")  # held can't back it
    assert w.authorize("ada", "cy", 4000).status == 201                       # exactly available
    assert_error(w.authorize("bob", "bob", 1), 422, "self_payment")
    assert_error(w.authorize("bob", "ghost", 1), 404, "not_found")
    for bad in (0, -1, 1000000001, 1.5, "5", True, None):
        assert_error(w.authorize("bob", "ada", bad), 422, "validation_failed")
    assert_error(w.authorize("bob", "ada", 1, note="n" * 201), 422, "validation_failed")
    assert_error(w.authorize("bob", "ada", 1, visibility="friends"), 422, "validation_failed")
    assert_error(w.api.call("POST", "/authorizations", {"to_handle": "ada", "amount": 1}, token=w.tok["bob"]),
                 400, "missing_idempotency_key")
    assert w.avail("ada") == 0 and w.held("ada") == 10000


@pytest.mark.obl("S1-002", "S1-092", "S1-112", "S1-196")
def test_held_funds_fund_nothing_else(w):
    assert w.authorize("ada", "bob", 9500).status == 201   # available 500
    assert_error(w.api.pay(w.tok["ada"], "cy", 501), 409, "insufficient_funds")
    assert w.api.pay(w.tok["ada"], "cy", 500).status == 201  # available 0 now
    assert_error(w.api.pay_request(w.tok["ada"], "rq_1"), 409, "insufficient_funds")
    r = w.api.call("POST", "/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "cy", "amount": 1}]},
                   token=w.tok["op"], key=new_key())
    assert_error(r, 409, "insufficient_funds")
    # net within total but eating into held → 409, nothing committed
    r = w.api.call("POST", "/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "cy", "amount": 300},
                                                          {"from_handle": "dee", "to_handle": "ada", "amount": 200}]},
                   token=w.tok["op"], key=new_key())
    assert_error(r, 409, "insufficient_funds")
    assert w.me("ada")["total"] == 9500 and w.me("dee")["total"] == 5000
    # a credit makes it affordable again
    r = w.api.call("POST", "/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "cy", "amount": 300},
                                                          {"from_handle": "dee", "to_handle": "ada", "amount": 300}]},
                   token=w.tok["op"], key=new_key())
    assert r.status == 201, r
    assert w.totals() == total(w.fx)


@pytest.mark.obl("S2-060", "S2-069")
def test_authorizations_not_in_feed(w):
    before = w.api.activity(w.tok["ada"], limit=200).json["payments"]
    a1 = w.authorize("ada", "bob", 100).json["authorization_id"]
    a2 = w.authorize("ada", "bob", 100).json["authorization_id"]
    w.void("ada", a2)
    for h in ("ada", "bob", "cy"):
        ids = {p["payment_id"] for p in w.api.activity(w.tok[h], limit=200).json["payments"]}
        assert a1 not in ids and a2 not in ids
    assert w.api.activity(w.tok["ada"], limit=200).json["payments"] == before


# --- capture -----------------------------------------------------------------------------

@pytest.mark.obl("S2-061", "S2-062", "S2-063", "S1-091")
def test_default_final_capture_releases_rest(w):
    a = w.authorize("ada", "bob", 2000, note="deposit", visibility="private").json
    r = w.capture("bob", a["authorization_id"], {"amount": 1500})
    assert r.status == 201, r
    p = r.json
    assert p["authorization_id"] == a["authorization_id"] and p["request_id"] is None
    assert p["settlement_id"] is None and p["amount"] == 1500
    assert p["from_user_id"] == "u_ada" and p["to_user_id"] == "u_bob"
    assert p["note"] == "deposit" and p["visibility"] == "private"
    ada, bob = w.me("ada"), w.me("bob")
    assert (ada["total"], ada["held"], ada["available"]) == (8500, 0, 8500), ada
    assert bob["total"] == 4000
    got = [x for x in w.auths("ada").json["authorizations"] if x["authorization_id"] == a["authorization_id"]][0]
    assert got["status"] == "captured" and got["captured_amount"] == 1500
    assert got["payment_id"] == p["payment_id"] and got["payment_ids"] == [p["payment_id"]]
    assert got["remaining_amount"] == 0
    feed = {x["payment_id"]: x for x in w.api.activity(w.tok["bob"], limit=200).json["payments"]}
    assert feed[p["payment_id"]] == p
    assert p["payment_id"] not in {x["payment_id"] for x in w.api.activity(w.tok["cy"], limit=200).json["payments"]}
    assert_error(w.capture("bob", a["authorization_id"], {"amount": 1}), 409, "authorization_not_open")
    assert_error(w.void("ada", a["authorization_id"]), 409, "authorization_not_open")


@pytest.mark.obl("S2-061", "S2-064")
def test_capture_amount_defaults_to_remainder(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    p = w.capture("bob", a).json
    assert p["amount"] == 2000
    assert w.me("bob")["total"] == 4500 and w.held("ada") == 0


@pytest.mark.obl("S2-064", "S2-065")
def test_extended_capture_700_700_600(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    ids = []
    for amt, left, status in [(700, 1300, "open"), (700, 600, "open")]:
        r = w.capture("bob", a, {"amount": amt, "final": False})
        assert r.status == 201 and r.json["amount"] == amt, r
        ids.append(r.json["payment_id"])
        cur = [x for x in w.auths("bob").json["authorizations"] if x["authorization_id"] == a][0]
        assert cur["status"] == status and cur["remaining_amount"] == left
        assert cur["captured_amount"] == 2000 - left and cur["payment_ids"] == ids
        assert cur["payment_id"] == ids[-1]
        assert w.held("ada") == left
    assert_error(w.capture("bob", a, {"amount": 601, "final": False}), 422, "capture_exceeds_authorization")
    r = w.capture("bob", a, {"amount": 600, "final": False})  # whole remainder closes it
    assert r.status == 201, r
    ids.append(r.json["payment_id"])
    cur = [x for x in w.auths("bob").json["authorizations"] if x["authorization_id"] == a][0]
    assert cur["status"] == "captured" and cur["remaining_amount"] == 0 and cur["payment_ids"] == ids
    assert w.me("ada")["total"] == 8000 and w.held("ada") == 0 and w.me("bob")["total"] == 4500


@pytest.mark.obl("S2-064")
def test_final_after_partial_releases_rest(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    w.capture("bob", a, {"amount": 500, "final": False})
    r = w.capture("bob", a, {"amount": 100})
    assert r.status == 201
    cur = [x for x in w.auths("ada").json["authorizations"] if x["authorization_id"] == a][0]
    assert cur["status"] == "captured" and cur["captured_amount"] == 600 and cur["remaining_amount"] == 0
    assert w.me("ada")["available"] == 9400 and w.held("ada") == 0


@pytest.mark.obl("S2-065")
def test_void_after_partial_keeps_records(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    p = w.capture("bob", a, {"amount": 300, "final": False}).json
    r = w.void("ada", a)
    assert r.status == 200 and r.json["status"] == "voided", r
    assert r.json["captured_amount"] == 300 and r.json["payment_ids"] == [p["payment_id"]]
    assert r.json["payment_id"] == p["payment_id"] and r.json["remaining_amount"] == 0
    assert w.me("ada")["total"] == 9700 and w.held("ada") == 0
    assert p["payment_id"] in {x["payment_id"] for x in w.api.activity(w.tok["ada"], limit=200).json["payments"]}
    r2 = w.void("ada", a)
    assert r2.status == 200 and r2.json["status"] == "voided"


@pytest.mark.obl("S2-067")
def test_capture_errors(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    assert_error(w.capture("ada", a), 403, "forbidden")
    assert_error(w.capture("cy", a), 403, "forbidden")
    assert_error(w.capture("op", a), 403, "forbidden")
    assert_error(w.capture("bob", "a_nope"), 404, "not_found")
    assert_error(w.capture("bob", a, {"amount": 2001}), 422, "capture_exceeds_authorization")
    for bad in (0, -1, 1.5, "10", True):
        assert_error(w.capture("bob", a, {"amount": bad}), 422, "validation_failed")
    assert_error(w.api.call("POST", f"/authorizations/{a}/capture", {}, token=w.tok["bob"]), 400,
                 "missing_idempotency_key")
    assert w.held("ada") == 2000


@pytest.mark.obl("S2-067")
@pytest.mark.decision("D2-04")
def test_final_wrong_type(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    for bad in ("false", 0, None, [False]):
        assert_error(w.capture("bob", a, {"amount": 1, "final": bad}), 400, "malformed_request")


@pytest.mark.obl("S2-068")
def test_void_rules(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    assert_error(w.void("bob", a), 403, "forbidden")
    assert_error(w.void("cy", a), 403, "forbidden")
    assert_error(w.void("ada", "a_nope"), 404, "not_found")
    r = w.void("ada", a, headers={"Content-Type": "application/json"}, raw="{\"junk\":1}")
    assert r.status == 200 and r.json["status"] == "voided" and r.json["remaining_amount"] == 0, r
    assert w.held("ada") == 0 and w.avail("ada") == 10000
    assert_error(w.capture("bob", a), 409, "authorization_not_open")


@pytest.mark.obl("S2-072")
def test_capture_spends_own_reservation_at_zero_available(w):
    a = w.authorize("bob", "cy", 2500).json["authorization_id"]
    assert w.avail("bob") == 0
    r = w.capture("cy", a, {"amount": 1000})
    assert r.status == 201, r
    b = w.me("bob")
    assert (b["total"], b["held"], b["available"]) == (1500, 0, 1500), b
    a2 = w.authorize("bob", "cy", 1500).json["authorization_id"]
    assert w.capture("cy", a2).status == 201
    assert w.me("bob")["total"] == 0 and w.me("cy")["total"] == 2500


# --- idempotency on the new paths ---------------------------------------------------------

@pytest.mark.obl("S2-061", "S2-066", "S2-073")
@pytest.mark.decision("D2-03")
def test_capture_idempotency(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    k = new_key()
    first = w.capture("bob", a, {}, key=k)
    assert first.status == 201
    rep = w.capture("bob", a, {}, key=k)
    assert rep.status == 200 and rep.json == first.json, rep
    assert_error(w.capture("bob", a, {"amount": 2000}, key=k), 409, "idempotency_key_reuse")
    assert_error(w.capture("bob", a, {"final": True}, key=k), 409, "idempotency_key_reuse")
    assert_error(w.capture("bob", a, {"amount": 99999}, key=k), 409, "idempotency_key_reuse")
    assert w.me("bob")["total"] == 4500


@pytest.mark.obl("S2-073")
def test_replays_after_closure(w):
    ka, kc = new_key(), new_key()
    auth = w.authorize("ada", "bob", 2000, key=ka)
    aid = auth.json["authorization_id"]
    cap = w.capture("bob", aid, {"amount": 100, "final": False}, key=kc)
    assert w.void("ada", aid).status == 200
    r = w.authorize("ada", "bob", 2000, key=ka)
    assert r.status == 200 and r.json == auth.json and r.json["status"] == "open", r
    r = w.capture("bob", aid, {"amount": 100, "final": False}, key=kc)
    assert r.status == 200 and r.json == cap.json, r
    assert w.me("bob")["total"] == 2600


@pytest.mark.obl("S2-073")
def test_failed_capture_key_reusable(w):
    a = w.authorize("ada", "bob", 2000).json["authorization_id"]
    k = new_key()
    assert_error(w.capture("bob", a, {"amount": 5000}, key=k), 422, "capture_exceeds_authorization")
    assert w.capture("bob", a, {"amount": 50}, key=k).status == 201


# --- expiry ------------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.obl("S2-057", "S2-055", "S2-050")
@pytest.mark.decision("D2-02", "D2-08", "D2-09")
def test_expiry_without_a_request_at_the_deadline(api):
    w = W2(api, fx2(authorization_ttl_seconds=2))
    a = w.authorize("ada", "bob", 2000).json
    exp = parse_ts(a["expires_at"])
    assert exp - parse_ts(a["created_at"]) == timedelta(seconds=2)
    part = w.authorize("ada", "bob", 1000).json["authorization_id"]
    w.capture("bob", part, {"amount": 400, "final": False})
    from datetime import datetime, timezone
    while datetime.now(timezone.utc) < exp - timedelta(seconds=0.5):
        time.sleep(0.05)
    before = [x for x in w.auths("ada").json["authorizations"] if x["authorization_id"] == a["authorization_id"]][0]
    assert before["status"] == "open", before
    while datetime.now(timezone.utc) < exp + timedelta(seconds=1.2):
        time.sleep(0.05)
    lst = {x["authorization_id"]: x for x in w.auths("ada").json["authorizations"]}
    assert lst[a["authorization_id"]]["status"] == "expired"
    assert lst[part]["status"] == "expired" and lst[part]["captured_amount"] == 400
    assert lst[part]["remaining_amount"] == 0
    me = w.me("ada")
    assert me["held"] == 0 and me["available"] == me["total"] == 9600, me
    assert {x["authorization_id"] for x in w.auths("ada", status="expired").json["authorizations"]} == \
        {a["authorization_id"], part}
    assert w.auths("ada", status="open").json["authorizations"] == []
    assert_error(w.capture("bob", a["authorization_id"]), 409, "authorization_expired")
    assert_error(w.void("ada", a["authorization_id"]), 409, "authorization_not_open")
    assert w.me("bob")["total"] == 2900


@pytest.mark.obl("S2-054", "S2-056")
def test_seeded_authorizations(api):
    fx = fx2(authorizations=[
        auth_rec("a_open", "u_ada", "u_bob", 3000),
        auth_rec("a_past", "u_ada", "u_bob", 5000, expires_h=-2),     # open but already expired
        auth_rec("a_cap", "u_ada", "u_bob", 100, status="captured"),
        auth_rec("a_void", "u_ada", "u_bob", 100, status="voided"),
        auth_rec("a_exp", "u_ada", "u_bob", 100, status="expired", expires_h=-3),
    ])
    w = W2(api, fx)
    me = w.me("ada")
    assert (me["total"], me["held"], me["available"]) == (10000, 3000, 7000), me
    lst = {x["authorization_id"]: x for x in w.auths("bob").json["authorizations"]}
    assert lst["a_open"]["status"] == "open" and lst["a_past"]["status"] == "expired"
    assert lst["a_cap"]["status"] == "captured" and lst["a_void"]["status"] == "voided"
    assert lst["a_exp"]["status"] == "expired"
    assert_error(w.capture("bob", "a_past"), 409, "authorization_expired")
    assert_error(w.capture("bob", "a_exp"), 409, "authorization_expired")
    assert_error(w.capture("bob", "a_cap"), 409, "authorization_not_open")
    assert_error(w.capture("bob", "a_void"), 409, "authorization_not_open")
    assert w.capture("bob", "a_open", {"amount": 3000}).status == 201


@pytest.mark.obl("S2-056")
def test_seeded_holds_exceed_or_equal_balance(api):
    w = W2(api, fx2())
    bad = fx2(authorizations=[auth_rec("a1", "u_bob", "u_ada", 2000), auth_rec("a2", "u_bob", "u_ada", 501)])
    assert_error(api.call("POST", "/_test/reset", bad), 422, "validation_failed")
    assert w.me("bob")["held"] == 0 and w.me("bob")["total"] == 2500
    ok = fx2(authorizations=[auth_rec("a1", "u_bob", "u_ada", 2000), auth_rec("a2", "u_bob", "u_ada", 500),
                             auth_rec("a3", "u_bob", "u_ada", 9999, expires_h=-2),
                             auth_rec("a4", "u_bob", "u_ada", 9999, status="voided")])
    w2 = W2(api, ok)
    assert w2.avail("bob") == 0 and w2.held("bob") == 2500


@pytest.mark.obl("S2-055")
@pytest.mark.decision("D2-15")
@pytest.mark.parametrize("ttl", [0, -1, 1.5, "600", True, None])
def test_bad_ttl(api, ttl):
    w = W2(api, fx2())
    assert_error(api.call("POST", "/_test/reset", fx2(authorization_ttl_seconds=ttl)), 422, "validation_failed")
    assert w.me("ada")["total"] == 10000


@pytest.mark.obl("S2-055")
def test_ttl_default_600(api):
    fx = fx2()
    del fx["authorization_ttl_seconds"]
    del fx["authorizations"]
    w = W2(api, fx)
    a = w.authorize("ada", "bob", 1).json
    assert parse_ts(a["expires_at"]) - parse_ts(a["created_at"]) == timedelta(seconds=600)


@pytest.mark.obl("S2-054")
@pytest.mark.decision("D2-15")
@pytest.mark.parametrize("case", ["unknown_from", "self", "amount0", "amount_big", "amount_frac", "status",
                                  "no_expiry", "bad_expiry", "no_offset", "dup_id"])
def test_bad_seeded_authorization(api, case):
    w = W2(api, fx2())
    rec = auth_rec("a_x", "u_ada", "u_bob", 100)
    recs = [rec]
    if case == "unknown_from":
        rec["from_user_id"] = "u_ghost"
    elif case == "self":
        rec["to_user_id"] = "u_ada"
    elif case == "amount0":
        rec["amount"] = 0
    elif case == "amount_big":
        rec["amount"] = 1000000001
    elif case == "amount_frac":
        rec["amount"] = 1.5
    elif case == "status":
        rec["status"] = "pending"
    elif case == "no_expiry":
        del rec["expires_at"]
    elif case == "bad_expiry":
        rec["expires_at"] = "tomorrow"
    elif case == "no_offset":
        rec["expires_at"] = rec["expires_at"][:19]
    elif case == "dup_id":
        recs = [rec, dict(rec)]
    assert_error(api.call("POST", "/_test/reset", fx2(authorizations=recs)), 422, "validation_failed")
    assert w.me("ada")["total"] == 10000


# --- GET /authorizations -------------------------------------------------------------------

@pytest.mark.obl("S2-069")
def test_list_scope_filters_pagination(w):
    ids = []
    for i in range(7):
        ids.append(w.authorize("ada", "bob", 10 + i).json["authorization_id"])
    inc = w.authorize("bob", "ada", 5).json["authorization_id"]
    other = w.authorize("dee", "cy", 5).json["authorization_id"]
    w.void("ada", ids[0])
    r = w.auths("ada")
    assert r.status == 200 and set(r.json) >= {"authorizations", "has_more"}, r
    got = [x["authorization_id"] for x in r.json["authorizations"]]
    assert set(got) == set(ids) | {inc} and other not in got
    assert got[0] == inc  # newest first
    assert [x["authorization_id"] for x in w.auths("ada", direction="incoming").json["authorizations"]] == [inc]
    assert set(x["authorization_id"] for x in w.auths("ada", direction="outgoing").json["authorizations"]) == set(ids)
    assert [x["authorization_id"] for x in w.auths("ada", status="voided").json["authorizations"]] == [ids[0]]
    p = w.auths("ada", limit=3, offset=0).json
    assert len(p["authorizations"]) == 3 and p["has_more"] is True
    p = w.auths("ada", limit=3, offset=6).json
    assert len(p["authorizations"]) == 2 and p["has_more"] is False
    assert w.auths("op").json["authorizations"] == []
    for bad in ({"limit": "0"}, {"limit": "1e1"}, {"offset": "-1"}, {"direction": "both"}, {"status": "closed"}):
        assert_error(w.auths("ada", **bad), 422, "validation_failed")
    assert_error(w.api.call("GET", "/authorizations"), 401, "unauthenticated")


# --- payment representations and unchanged behaviour ---------------------------------------

@pytest.mark.obl("S1-091", "S1-199", "S2-053")
def test_every_payment_has_authorization_id(w):
    p = w.api.pay(w.tok["ada"], "bob", 5).json
    q = w.api.pay_request(w.tok["ada"], "rq_1").json
    s = w.api.call("POST", "/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "cy", "amount": 1}]},
                   token=w.tok["op"], key=new_key()).json
    for x in [p, q] + s["payments"] + w.api.activity(w.tok["ada"], limit=200).json["payments"]:
        assert "authorization_id" in x and x["authorization_id"] is None, x
    assert w.held("ada") == 0 and w.avail("ada") == w.me("ada")["total"]


@pytest.mark.obl("S2-053")
def test_split_unchanged_and_requests_can_exceed_available(w):
    w.authorize("ada", "bob", 10000)
    r = w.api.call("POST", "/splits", {"amount": 10, "participant_handles": ["bob", "ada", "cy"]},
                   token=w.tok["bob"], key=new_key())
    assert r.status == 201 and [s["amount"] for s in r.json["shares"]] == [4, 3, 3]
    assert w.api.request(w.tok["bob"], "ada", 999999).status == 201


# --- negotiation ------------------------------------------------------------------------------

@pytest.mark.obl("S2-011")
@pytest.mark.decision("D2-14")
@pytest.mark.parametrize("path", ["/requests", "/authorizations"])
def test_content_negotiation(w, path):
    t = w.tok["ada"]
    for acc in (None, "*/*", "application/json", "application/json, text/html;q=0.5"):
        h = {"Accept": acc} if acc else {}
        r = w.api.call("GET", path, token=t, headers=h)
        assert r.status == 200 and r.headers["content-type"].startswith("application/json"), (acc, r.status)
    for acc in ("text/html", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"):
        r = w.api.call("GET", path, headers={"Accept": acc})
        assert r.status == 200 and r.headers["content-type"].startswith("text/html"), (acc, r.status)
    if path == "/requests":
        r = w.api.call("POST", "/requests", {"payer_handle": "bob", "amount": 1}, token=t, key=new_key(),
                       headers={"Accept": "text/html"})
        assert r.status == 201 and r.headers["content-type"].startswith("application/json")


@pytest.mark.obl("S2-010", "S2-011")
@pytest.mark.parametrize("path", ["/", "/split", "/signup", "/login"])
def test_ui_routes_serve_html(w, path):
    r = w.api.call("GET", path, headers={"Accept": "text/html"})
    assert r.status == 200 and r.headers["content-type"].startswith("text/html"), r.status


# --- export/import with holds ---------------------------------------------------------------

@pytest.mark.obl("S1-176", "S2-040")
def test_export_import_keeps_holds_and_retries(w):
    ka = new_key()
    auth = w.authorize("ada", "bob", 2000, key=ka)
    aid = auth.json["authorization_id"]
    kc = new_key()
    cap = w.capture("bob", aid, {"amount": 500, "final": False}, key=kc)
    exp = w.api.call("GET", "/_test/export").json
    assert exp["track"] == "pocketful" and exp["format_version"] == 1
    w.api.reset(fx2())
    assert w.api.call("POST", "/_test/import", exp).status == 204
    me = w.api.me(w.tok["ada"])
    assert me["held"] == 1500 and me["total"] == 9500
    assert w.capture("bob", aid, {"amount": 500, "final": False}, key=kc).json == cap.json
    assert w.authorize("ada", "bob", 2000, key=ka).json == auth.json
    r = w.capture("bob", aid)
    assert r.status == 201 and r.json["amount"] == 1500


@pytest.mark.xc
@pytest.mark.slow
@pytest.mark.obl("S2-074", "S2-057")
def test_hold_exported_before_expiry_imported_after(api, api_b):
    w = W2(api, fx2(authorization_ttl_seconds=2))
    aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
    exp = api.call("GET", "/_test/export")
    assert exp.status == 200
    time.sleep(3.2)
    assert api_b.call("POST", "/_test/import", raw=exp.raw).status == 204
    me = api_b.me(w.tok["ada"])
    assert me["held"] == 0 and me["available"] == 10000, me
    got = [x for x in api_b.call("GET", "/authorizations", token=w.tok["ada"]).json["authorizations"]
           if x["authorization_id"] == aid][0]
    assert got["status"] == "expired"

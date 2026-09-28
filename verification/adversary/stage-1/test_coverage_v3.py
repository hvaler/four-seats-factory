"""v3 additions routed by the analyst (msg 4837ffaf) on candidate 1.

Export states are opaque (§10): tampering is generic (per top-level key of `state`) and no
state content is ever printed; failure messages carry key names and counts only (S1-181).
"""
import copy
import hashlib
import json
import threading
import time

import pytest

from advlib import (NO_BODY, PASSWORD, Api, World, assert_error, fixture, new_key,
                    total, user)


def _snapshot(api, tok):
    return api.me(tok), api.activity(tok, limit=200).json


def _wrong_type(v):
    if isinstance(v, list):
        return "x"
    if isinstance(v, dict):
        return 7
    if isinstance(v, str):
        return []
    if isinstance(v, bool):
        return "x"
    if isinstance(v, (int, float)):
        return "x"
    return 7  # null -> number


def _state_keys(api):
    exp = api.call("GET", "/_test/export").json
    assert isinstance(exp.get("state"), dict) and exp["state"], "export state is empty or not an object"
    return exp, sorted(exp["state"])


# --- S1-174: tampered / invalid state ----------------------------------------------

@pytest.mark.obl("S1-174")
@pytest.mark.decision("D-23")
def test_import_state_with_wrong_typed_inner_field(w):
    exp, keys = _state_keys(w.api)
    w.api.pay(w.tok["ada"], "bob", 9)
    before = _snapshot(w.api, w.tok["ada"])
    accepted = []
    for k in keys:
        bad = copy.deepcopy(exp)
        bad["state"][k] = _wrong_type(bad["state"][k])
        r = w.api.call("POST", "/_test/import", bad)
        if r.status != 422 or r.code != "validation_failed":
            accepted.append(f"{k}->{r.status}")
        assert _snapshot(w.api, w.tok["ada"]) == before, f"destination changed after bad import of key {k}"
    assert accepted == [], f"wrong-typed state keys not rejected with 422: {accepted}"


@pytest.mark.obl("S1-174")
@pytest.mark.decision("D-23")
def test_import_state_with_missing_inner_field(w):
    w.api.pay(w.tok["ada"], "bob", 9)
    exp, keys = _state_keys(w.api)
    before = _snapshot(w.api, w.tok["ada"])
    outcomes = {}
    for k in keys:
        bad = copy.deepcopy(exp)
        del bad["state"][k]
        r = w.api.call("POST", "/_test/import", bad)
        outcomes[k] = r.status
        if r.status == 204:
            # accepted as valid: restore the exact reference state for the next key
            assert w.api.call("POST", "/_test/import", exp).status == 204
        else:
            assert r.status == 422 and r.code == "validation_failed", f"{k}->{r.status}"
            assert _snapshot(w.api, w.tok["ada"]) == before, f"destination changed after bad import of key {k}"
    rejected = [k for k, s in outcomes.items() if s == 422]
    assert rejected, f"no state key was required by import: {outcomes}"


@pytest.mark.obl("S1-174")
@pytest.mark.parametrize("state", ["x", 1, True, None, []])
def test_import_state_not_an_object(w, state):
    exp = w.api.call("GET", "/_test/export").json
    exp["state"] = state
    before = _snapshot(w.api, w.tok["ada"])
    assert_error(w.api.call("POST", "/_test/import", exp), 422, "validation_failed")
    assert _snapshot(w.api, w.tok["ada"]) == before


@pytest.mark.obl("S1-174")
def test_import_from_other_fixture_does_not_leak_into_failed_attempt(api):
    """A valid export of state X, tampered, must not partially apply X."""
    w = World(api, fixture())
    exp_other = api.call("GET", "/_test/export").json
    api.reset(fixture(users=[user("u_q", "q", 5), user("u_r", "r", 0)], payments=[], requests=[],
                      settlement_operator_ids=[]))
    tq = api.login("q@example.com")
    keys = sorted(exp_other["state"])
    for k in keys:
        bad = copy.deepcopy(exp_other)
        bad["state"][k] = _wrong_type(bad["state"][k])
        api.call("POST", "/_test/import", bad)
        assert api.balance(tq) == 5, f"state changed after tampered import of key {k}"
    assert api.call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD}).status == 401


# --- S1-175: export during concurrent writes ------------------------------------------

@pytest.mark.xc
@pytest.mark.obl("S1-175", "S1-172", "S1-001")
def test_export_under_concurrent_writes_is_consistent(api, api_b):
    users = [user(f"u_{h}", h, 10000) for h in ("a", "b", "c", "d", "e")]
    seed = [{"id": "p_seed", "from_user_id": "u_a", "to_user_id": "u_b", "amount": 1,
             "note": "", "visibility": "private"}]
    fx = fixture(users=users, payments=seed, requests=[], settlement_operator_ids=["u_e"])
    w = World(api, fx)
    hs = ["a", "b", "c", "d"]
    stop = threading.Event()
    errors = []

    def writer(i):
        a = Api()
        n = 0
        while not stop.is_set():
            f, t = hs[(i + n) % 4], hs[(i + n + 1 + n % 3) % 4]
            if f == t:
                t = hs[(hs.index(f) + 1) % 4]
            vis = "private" if n % 2 else "public"
            if n % 7 == 0:
                r = a.call("POST", "/settlements",
                           {"transfers": [{"from_handle": f, "to_handle": t, "amount": 3},
                                          {"from_handle": t, "to_handle": f, "amount": 2, "visibility": vis}]},
                           token=w.tok["e"], key=new_key())
            else:
                r = a.pay(w.tok[f], t, 1 + n % 5, visibility=vis)
            if r.status >= 500:
                errors.append(r.status)
            n += 1
        a.close()

    th = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for x in th:
        x.start()
    time.sleep(0.3)
    exports = []
    for _ in range(5):
        r = api.call("GET", "/_test/export")
        assert r.status == 200
        exports.append(r.raw)
        time.sleep(0.05)
    stop.set()
    for x in th:
        x.join()
    assert not errors, errors
    seeded_bal = {u["handle"]: u["balance"] for u in users}
    for raw in exports:
        r = api_b.call("POST", "/_test/import", raw=raw)
        assert r.status == 204, r.status
        tot = 0
        for h in ("a", "b", "c", "d", "e"):
            bal = api_b.balance(w.tok[h])
            assert bal >= 0
            tot += bal
            items, off = [], 0
            while True:
                pg = api_b.activity(w.tok[h], limit=200, offset=off).json
                items += pg["payments"]
                if not pg["has_more"]:
                    break
                off += 200
            ids = [p["payment_id"] for p in items]
            assert len(ids) == len(set(ids)), f"{h}: duplicate items while paging a static imported feed"
            delta = 0
            for p in items:
                if p["payment_id"] == "p_seed":
                    continue
                if p["to_handle"] == h:
                    delta += p["amount"]
                if p["from_handle"] == h:
                    delta -= p["amount"]
            assert bal == seeded_bal[h] + delta, f"{h}: balance does not match its own feed in a mid-write export"
        assert tot == total(fx), "mid-write export does not conserve the seeded total"


@pytest.mark.obl("S1-175")
def test_saved_export_copy_unchanged_by_later_write(w):
    r1 = w.api.call("GET", "/_test/export")
    saved = bytes(r1.raw)
    h1 = hashlib.sha256(saved).hexdigest()
    assert w.api.pay(w.tok["ada"], "bob", 1).status == 201
    r2 = w.api.call("GET", "/_test/export")
    assert hashlib.sha256(saved).hexdigest() == h1
    assert hashlib.sha256(r2.raw).hexdigest() != h1, "a later write is not reflected in a new export"
    assert w.api.call("POST", "/_test/import", raw=saved).status == 204
    assert w.bal("ada") == 10000 and w.bal("bob") == 2500


# --- S1-047 / D-24: reset content errors ---------------------------------------------

def _bad_fixtures():
    out = {}
    f = fixture()
    f["users"].append(user("u_dup", "ada", 0, email="other@example.com"))
    out["duplicate_handle"] = f
    f = fixture()
    f["users"].append(user("u_dup", "zed", 0, email="ada@example.com"))
    out["duplicate_email"] = f
    f = fixture()
    f["users"].append(user("u_ada", "zed", 0))
    out["duplicate_user_id"] = f
    f = fixture()
    f["payments"][0]["to_user_id"] = "u_ghost"
    out["dangling_payment_user"] = f
    f = fixture()
    f["requests"][0]["payer_id"] = "u_ghost"
    out["dangling_request_user"] = f
    out["minor_units_1"] = fixture(minor_units=1)
    f = fixture()
    f["users"][0]["handle"] = "Bad-Handle"
    out["regex_invalid_handle"] = f
    f = fixture()
    f["requests"][0]["status"] = "open"
    out["bad_request_status"] = f
    f = fixture()
    del f["users"][0]["email"]
    out["missing_user_email"] = f
    return out


BAD = _bad_fixtures()


@pytest.mark.obl("S1-047")
@pytest.mark.decision("D-24")
@pytest.mark.parametrize("case", sorted(BAD))
def test_reset_content_error_is_422_and_changes_nothing(api, case):
    good = fixture(users=[user("u_k", "keep", 77), user("u_l", "left", 3)], payments=[], requests=[],
                   settlement_operator_ids=[])
    w = World(api, good)
    r = api.call("POST", "/_test/reset", BAD[case])
    assert_error(r, 422, "validation_failed")
    assert api.balance(w.tok["keep"]) == 77
    assert api.call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD}).status == 401


@pytest.mark.obl("S1-047")
def test_reset_negative_balance_among_valid_users(api):
    w = World(api, fixture())
    bad = fixture()
    bad["users"][3]["balance"] = -5
    assert_error(api.call("POST", "/_test/reset", bad), 422, "validation_failed")
    assert api.balance(w.tok["ada"]) == 10000


# --- S1-017 / S1-019 on every endpoint ------------------------------------------------

def _ct_ok(r):
    ct = r.headers.get("content-type", "").replace(" ", "").lower()
    return ct.startswith("application/json") and "charset=utf-8" in ct


@pytest.mark.obl("S1-017")
def test_content_type_every_endpoint(api):
    w = World(api, fixture())
    a, op = w.tok["ada"], w.tok["op"]
    rid = api.request(w.tok["bob"], "ada", 5).json["request_id"]
    rid2 = api.request(w.tok["bob"], "ada", 5).json["request_id"]
    rid3 = api.request(w.tok["bob"], "ada", 5).json["request_id"]
    exp = api.call("GET", "/_test/export")
    calls = {
        "health": api.call("GET", "/health"),
        "export": exp,
        "signup": api.call("POST", "/auth/signup", {"email": "ct@example.com", "password": PASSWORD, "display_name": "C"}),
        "signup_err": api.call("POST", "/auth/signup", {"email": "x"}),
        "login": api.call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD}),
        "login_err": api.call("POST", "/auth/login", {"email": "ada@example.com", "password": "wrongwrong"}),
        "me": api.call("GET", "/me", token=a),
        "payments": api.pay(a, "bob", 1),
        "payments_err": api.pay(a, "ada", 1),
        "requests_post": api.request(a, "bob", 1),
        "requests_get": api.requests(a),
        "requests_get_err": api.requests(a, limit="0"),
        "pay": api.pay_request(a, rid),
        "pay_err": api.pay_request(a, "nope"),
        "decline": api.call("POST", f"/requests/{rid2}/decline", token=a),
        "cancel": api.call("POST", f"/requests/{rid3}/cancel", token=w.tok["bob"]),
        "cancel_err": api.call("POST", f"/requests/{rid3}/cancel", token=a),
        "splits": api.call("POST", "/splits", {"amount": 3, "participant_handles": ["ada", "bob"]}, token=a, key=new_key()),
        "activity": api.activity(a),
        "settlements": api.call("POST", "/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 1}]},
                                token=op, key=new_key()),
        "settlements_err": api.call("POST", "/settlements", {"transfers": []}, token=a, key=new_key()),
        "reset_err": api.call("POST", "/_test/reset", raw="{bad"),
        "import_err": api.call("POST", "/_test/import", {"track": "x"}),
        "unknown_route": api.call("GET", "/nope"),
        "missing_key": api.call("POST", "/payments", {"to_handle": "bob", "amount": 1}, token=a),
        "unauth": api.call("GET", "/me"),
    }
    bad = [k for k, r in calls.items() if not _ct_ok(r)]
    assert bad == [], f"missing application/json; charset=utf-8 on: {bad}"
    statuses = {k: r.status for k, r in calls.items()}
    assert all(s != 204 for s in statuses.values())
    assert statuses["signup"] == 201 and statuses["pay"] == 201 and statuses["settlements"] == 201, statuses


@pytest.mark.obl("S1-019")
def test_unknown_fields_ignored_every_body(api):
    fx = fixture()
    fx["unknown_top"] = {"x": 1}
    fx["users"][0]["favourite_colour"] = "teal"
    fx["payments"][0]["extra"] = [1, 2]
    fx["requests"][0]["extra"] = None
    assert api.call("POST", "/_test/reset", fx).status == 204
    X = {"zz_unknown": {"nested": [1, "a", None]}, "amountt": 5}
    r = api.call("POST", "/auth/signup", {"email": "uf@example.com", "password": PASSWORD, "display_name": "U", "handle": "hacker", **X})
    assert r.status == 201, r
    assert api.me(r.json["token"])["handle"] == "uf"  # a supplied handle is an unknown field
    r = api.call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD, **X})
    assert r.status == 200, r
    a = r.json["token"]
    b = api.login("bob@example.com")
    op = api.login("op@example.com")
    r = api.call("POST", "/requests", {"payer_handle": "bob", "amount": 4, **X}, token=a, key=new_key())
    assert r.status == 201 and r.json["amount"] == 4, r
    r = api.call("POST", "/splits", {"amount": 4, "participant_handles": ["ada", "bob"], **X}, token=a, key=new_key())
    assert r.status == 201, r
    rid = api.request(b, "ada", 1).json["request_id"]
    r = api.call("POST", f"/requests/{rid}/decline", {"status": "paid", **X}, token=a)
    assert r.status == 200 and r.json["status"] == "declined", r
    rid = api.request(b, "ada", 1).json["request_id"]
    r = api.call("POST", f"/requests/{rid}/cancel", {"status": "paid", **X}, token=b)
    assert r.status == 200 and r.json["status"] == "cancelled", r
    rid = api.request(b, "ada", 1).json["request_id"]
    r = api.call("POST", f"/requests/{rid}/pay", {"amount": 999, **X}, token=a, key=new_key())
    assert r.status == 201 and r.json["amount"] == 1, r
    r = api.call("POST", "/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 1}], **X},
                 token=op, key=new_key())
    assert r.status == 201, r
    r = api.call("POST", "/payments", {"to_handle": "bob", "amount": 1, "from_handle": "bob", **X}, token=a, key=new_key())
    assert r.status == 201 and r.json["from_handle"] == "ada", r
    for path, params in [("/requests", {"sort": "asc", "page": "2"}), ("/activity", {"sort": "asc", "cursor": "x"}),
                         ("/me", {"verbose": "1"})]:
        assert api.call("GET", path, token=a, params=params).status == 200, path
    exp = api.call("GET", "/_test/export").json
    exp["unknown_top"] = 1
    assert api.call("POST", "/_test/import", exp).status == 204


# --- S1-060 / D-09 --------------------------------------------------------------------

@pytest.mark.obl("S1-060")
@pytest.mark.decision("D-09")
def test_empty_display_name(w):
    r = w.api.call("POST", "/auth/signup", {"email": "e@example.com", "password": PASSWORD, "display_name": ""})
    assert_error(r, 422, "validation_failed")
    r = w.api.call("POST", "/auth/signup", {"email": "e@example.com", "password": PASSWORD, "display_name": 5})
    assert_error(r, 400, "malformed_request")
    r = w.api.call("POST", "/auth/login", {"email": "e@example.com", "password": PASSWORD})
    assert_error(r, 401, "unauthenticated")


# --- S1-057: non-ASCII key (risk probe; observation only) -------------------------------

@pytest.mark.risk
@pytest.mark.obl("S1-057")
def test_non_ascii_idempotency_key_observation(w, record_property):
    key = "clé-ü-€".encode("utf-8")
    first = w.api.call("POST", "/payments", {"to_handle": "bob", "amount": 3}, token=w.tok["ada"],
                       headers={"Idempotency-Key": key})
    rep = w.api.call("POST", "/payments", {"to_handle": "bob", "amount": 3}, token=w.tok["ada"],
                     headers={"Idempotency-Key": key})
    record_property("observation", f"non-ascii key: first={first.status} replay={rep.status}")
    assert first.status < 500 and rep.status < 500
    if first.status == 201:
        assert rep.status == 200 and rep.json == first.json
        assert w.bal("bob") == 2503

#!/usr/bin/env python3
"""Auditor-owned supplemental probes for fskit-001 stage 1, closing spec rows routed by analyst (msg 4837ffaf):
S1-017 (content type on every endpoint), S1-019 (unknown body fields / query params on every endpoint),
S1-047 + D-24 (reset content errors change nothing), S1-174 (tampered import state), S1-175 (export during
concurrent writes is an internally consistent snapshot), S1-060/D-09 (empty display_name).
Stdlib only; synthetic data; export bodies are held in memory only and never written.

usage: audit_probe2.py --base URL_A --base-b URL_B --out results.json
"""
import argparse, json, sys, time, threading, uuid
from concurrent.futures import ThreadPoolExecutor
import audit_probe as ap
from audit_probe import call, code, record, fixture, reset, login, bal, k


def ct_ok(ct):
    return (ct or "").replace(" ", "").lower() == "application/json;charset=utf-8"


def p_content_type_all_endpoints():
    """S1-017: every non-204 response, success and error, on every route."""
    reset(fixture([("op", 0), ("aa", 1000), ("bb", 1000)], operators=["op"]))
    ta, tb, to = login("aa"), login("bb"), login("op")
    s, rq, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 1}, token=ta, key=k())
    s, rq2, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 1}, token=ta, key=k())
    s, rq3, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 1}, token=ta, key=k())
    cases = [
        ("GET", "/health", None, None, None), ("GET", "/_test/export", None, None, None),
        ("POST", "/auth/signup", {"email": "ct1@audit.invalid", "password": "longenough1", "display_name": "C"}, None, None),
        ("POST", "/auth/login", {"email": "aa@audit.invalid", "password": "pw-aa-12345"}, None, None),
        ("GET", "/me", None, ta, None),
        ("POST", "/payments", {"to_handle": "bb", "amount": 1}, ta, k()),
        ("POST", "/requests", {"payer_handle": "bb", "amount": 1}, ta, k()),
        ("GET", "/requests", None, ta, None),
        ("POST", "/requests/%s/pay" % rq["request_id"], {}, tb, k()),
        ("POST", "/requests/%s/decline" % rq2["request_id"], None, tb, None),
        ("POST", "/requests/%s/cancel" % rq3["request_id"], None, ta, None),
        ("POST", "/splits", {"amount": 3, "participant_handles": ["aa", "bb"]}, ta, k()),
        ("GET", "/activity", None, ta, None),
        ("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 1}]}, to, k()),
    ]
    errs = [
        ("GET", "/me", None, None, None), ("POST", "/payments", {"to_handle": "bb"}, ta, k()),
        ("POST", "/payments", None, ta, None), ("POST", "/auth/login", {"email": "x@y", "password": "nopenope"}, None, None),
        ("POST", "/auth/signup", {"email": "bad", "password": "longenough1", "display_name": "C"}, None, None),
        ("POST", "/requests/nope/pay", {}, tb, k()), ("POST", "/settlements", {"transfers": []}, ta, k()),
        ("GET", "/requests?limit=0", None, ta, None), ("POST", "/_test/import", {"track": "x"}, None, None),
        ("POST", "/_test/reset", {"currency": "EUR"}, None, None), ("GET", "/no/such/route", None, ta, None),
        ("DELETE", "/me", None, ta, None),
    ]
    bad = {}
    n = 0
    for m, p, b, t, key in cases + errs:
        s, j, ct = call(m, p, b, token=t, key=key)
        n += 1
        if s == 204:
            continue
        if not ct_ok(ct) or (s >= 400 and not (isinstance(j, dict) and "error" in j and "code" in j["error"] and "message" in j["error"])):
            bad[m + " " + p] = (s, ct)
    record("S1-017/S1-050", "content type + error envelope on every route (%d calls)" % n, not bad, {"bad": bad})


def p_unknown_fields_everywhere():
    """S1-019: unknown body fields and unknown query params ignored on every endpoint."""
    X = {"zz_unknown": {"nested": [1, 2]}, "another": None}
    fx = fixture([("op", 0), ("aa", 1000), ("bb", 1000)], operators=["op"])
    fx["zz_unknown_fixture_field"] = True
    fx["users"][1]["zz_extra"] = "x"
    s, j, _ = call("POST", "/_test/reset", fx)
    out = {"reset": s}
    ta, tb, to = login("aa"), login("bb"), login("op")
    out["signup"] = call("POST", "/auth/signup", dict({"email": "uf1@audit.invalid", "password": "longenough1", "display_name": "U"}, **X))[0]
    out["login"] = call("POST", "/auth/login", dict({"email": "aa@audit.invalid", "password": "pw-aa-12345"}, **X))[0]
    out["payments"] = call("POST", "/payments", dict({"to_handle": "bb", "amount": 1}, **X), token=ta, key=k())[0]
    s, rq, _ = call("POST", "/requests", dict({"payer_handle": "bb", "amount": 1}, **X), token=ta, key=k())
    out["requests"] = s
    out["pay"] = call("POST", "/requests/%s/pay" % rq["request_id"], dict({"visibility": "private"}, **X), token=tb, key=k())[0]
    s, rq2, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 1}, token=ta, key=k())
    out["decline"] = call("POST", "/requests/%s/decline" % rq2["request_id"], X, token=tb)[0]
    s, rq3, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 1}, token=ta, key=k())
    out["cancel"] = call("POST", "/requests/%s/cancel" % rq3["request_id"], X, token=ta)[0]
    out["splits"] = call("POST", "/splits", dict({"amount": 3, "participant_handles": ["aa", "bb"]}, **X), token=ta, key=k())[0]
    out["settlements"] = call("POST", "/settlements", dict({"transfers": [dict({"from_handle": "aa", "to_handle": "bb", "amount": 1}, **X)]}, **X), token=to, key=k())[0]
    out["GET /me?x"] = call("GET", "/me?foo=bar&limit=abc", token=ta)[0]
    out["GET /requests?x"] = call("GET", "/requests?foo=bar&sort=weird", token=ta)[0]
    out["GET /activity?x"] = call("GET", "/activity?foo=bar&cursor=zz", token=ta)[0]
    out["GET /health?x"] = call("GET", "/health?foo=1")[0]
    s, ex, _ = call("GET", "/_test/export?foo=1")
    out["export?x"] = s
    ex2 = dict(ex, zz_unknown=1)
    out["import+unknown"] = call("POST", "/_test/import", ex2)[0]
    exp = {"reset": 204, "signup": 201, "login": 200, "payments": 201, "requests": 201, "pay": 201, "decline": 200,
           "cancel": 200, "splits": 201, "settlements": 201, "GET /me?x": 200, "GET /requests?x": 200,
           "GET /activity?x": 200, "GET /health?x": 200, "export?x": 200, "import+unknown": 204}
    record("S1-019", "unknown fields/params ignored on every endpoint", out == exp, {"got": out})


def p_reset_content_errors():
    """S1-047 (spec: negative balance) and D-24 (other content errors): 422 and nothing changes."""
    base_fx = fixture([("aa", 500), ("bb", 0)])
    reset(base_fx)
    ta = login("aa")
    call("POST", "/payments", {"to_handle": "bb", "amount": 7}, token=ta, key=k())

    def mk(mut):
        fx = json.loads(json.dumps(fixture([("cc", 10), ("dd", 20)])))
        mut(fx)
        return fx
    cases = {
        "S1-047 negative balance": lambda f: f["users"][0].__setitem__("balance", -1),
        "D-24 duplicate handle": lambda f: f["users"][1].__setitem__("handle", "cc"),
        "D-24 duplicate email": lambda f: f["users"][1].__setitem__("email", "cc@audit.invalid"),
        "D-24 duplicate user id": lambda f: f["users"][1].__setitem__("id", "u_cc"),
        "D-24 regex-invalid handle": lambda f: f["users"][0].__setitem__("handle", "Bad-Handle"),
        "D-24 minor_units 1": lambda f: f.__setitem__("minor_units", 1),
        "D-24 dangling payment ref": lambda f: f["payments"].append({"id": "p_x", "from_user_id": "u_cc", "to_user_id": "u_ghost", "amount": 1, "note": "", "visibility": "public"}),
        "D-24 dangling request ref": lambda f: f["requests"].append({"id": "rq_x", "requester_id": "u_ghost", "payer_id": "u_cc", "amount": 1, "note": "", "status": "pending"}),
        "D-24 bad request status": lambda f: f["requests"].append({"id": "rq_y", "requester_id": "u_dd", "payer_id": "u_cc", "amount": 1, "note": "", "status": "open"}),
        "D-24 missing users": lambda f: f.pop("users"),
        "D-24 operator unknown id": lambda f: f.__setitem__("settlement_operator_ids", ["u_ghost"]),
    }
    res = {}
    for name, mut in cases.items():
        s, j, _ = call("POST", "/_test/reset", mk(mut))
        me = call("GET", "/me", token=ta)
        res[name] = (s, code(j), me[0], (me[1] or {}).get("balance"))
    s1, j1, _ = call("POST", "/_test/reset", raw=b"{not json")
    s2, j2, _ = call("POST", "/_test/reset", raw=b"[1,2]")
    me = call("GET", "/me", token=ta)
    spec_ok = res["S1-047 negative balance"] == (422, "validation_failed", 200, 493)
    record("S1-047", "negative fixture balance -> 422, previous state intact", spec_ok, {"got": res["S1-047 negative balance"]})
    d24 = {n: v for n, v in res.items() if n.startswith("D-24") and n != "D-24 operator unknown id"}
    record("D-24", "reset content errors -> 422, previous state intact",
           all(v == (422, "validation_failed", 200, 493) for v in d24.values()) and (s1, s2) == (400, 400) and me[0] == 200,
           {"got": d24, "unparseable": s1, "non_object": s2})
    record("OBS", "operator id not a user (not asserted)", True, {"got": res["D-24 operator unknown id"]})


def p_import_tampered(base_b):
    """S1-174: import with missing/non-object/structurally broken state -> 422, destination unchanged."""
    reset(fixture([("aa", 1000), ("bb", 0)]))
    ta = login("aa")
    call("POST", "/payments", {"to_handle": "bb", "amount": 3}, token=ta, key=k())
    s, ex, _ = call("GET", "/_test/export")
    st = ex["state"]
    reset(fixture([("zz", 77), ("yy", 0)]), base=base_b)
    tz = login("zz", base=base_b)
    call("POST", "/payments", {"to_handle": "yy", "amount": 2}, token=tz, key=k(), base=base_b)

    def dest_view():
        me = call("GET", "/me", token=tz, base=base_b)
        feed = call("GET", "/activity", token=tz, base=base_b)[1]
        return (me[0], me[1].get("balance"), json.dumps(feed, sort_keys=True))
    before = dest_view()

    def broken_variants(state):
        out = {"state missing": None, "state string": "x", "state array": [], "state empty object": {}}
        # structural mutations of the opaque inner state, applied generically to its top-level members
        for key, val in state.items():
            if isinstance(val, list) and val:
                out["inner %s: first element -> string" % key] = dict(state, **{key: ["garbage"] + val[1:]})
                out["inner %s: -> number" % key] = dict(state, **{key: 42})
            elif isinstance(val, dict) and val:
                out["inner %s: -> string" % key] = dict(state, **{key: "garbage"})
                fk = next(iter(val))
                out["inner %s.%s -> null" % (key, fk)] = dict(state, **{key: dict(val, **{fk: None})})
            else:
                out["inner %s: -> [[]]" % key] = dict(state, **{key: [[]]})
        return out
    res = {}
    for name, bst in broken_variants(st).items():
        body = {"track": "pocketful", "format_version": 1}
        if bst is not None:
            body["state"] = bst
        s, j, _ = call("POST", "/_test/import", body, base=base_b)
        res[name] = (s, code(j), dest_view() == before)
    fivexx = {n: v for n, v in res.items() if v[0] >= 500}
    top = {n: v for n, v in res.items() if n.startswith("state ")}
    inner_changed = {n: v for n, v in res.items() if not n.startswith("state ") and v[0] == 204}
    inner_bad = {n: v for n, v in res.items() if not n.startswith("state ") and v[0] != 204 and v[:2] != (422, "validation_failed")}
    record("S1-174", "missing / non-object state -> 422, destination unchanged",
           all(v == (422, "validation_failed", True) for v in top.values()), {"got": top})
    record("S1-174", "structurally broken inner state -> 422 (or accepted as valid), destination unchanged on reject, no 5xx",
           not fivexx and not inner_bad and all(v[2] for n, v in res.items() if v[0] != 204),
           {"variants": len(res), "accepted_204": sorted(inner_changed), "non422_rejects": inner_bad, "5xx": fivexx})
    # restore B to known fixture for later probes
    reset(fixture([("zz", 1)]), base=base_b)


def p_export_during_writes(base_b):
    """S1-175: exports taken while payments are in flight are internally consistent snapshots."""
    users = [("u%d" % i, 1000) for i in range(8)]
    reset(fixture(users))
    toks = {h: login(h) for h, _ in users}
    total = 8000
    stop = threading.Event()
    exports = []

    def writer(i):
        n = 0
        h = "u%d" % (i % 8)
        while not stop.is_set() and n < 60:
            call("POST", "/payments", {"to_handle": "u%d" % ((i + 1 + n) % 8) if (i + 1 + n) % 8 != i % 8 else "u%d" % ((i + 2) % 8),
                                       "amount": 1 + (n % 5)}, token=toks[h], key=k())
            n += 1

    def exporter():
        for _ in range(6):
            s, ex, _ = call("GET", "/_test/export")
            if s == 200:
                exports.append(ex)
            time.sleep(0.05)
    with ThreadPoolExecutor(20) as pool:
        fs = [pool.submit(writer, i) for i in range(16)]
        e = pool.submit(exporter)
        e.result()
        stop.set()
        [f.result() for f in fs]
    ok_all = True
    detail = []
    for idx, ex in enumerate(exports):
        s, _, _ = call("POST", "/_test/import", ex, base=base_b)
        bals = {}
        net = {h: 0 for h, _ in users}
        for h, _ in users:
            bals[h] = bal(toks[h], base=base_b)
        # every payment is public, so any one user's feed lists all of them
        seen, off = {}, 0
        while True:
            pg = call("GET", "/activity?limit=200&offset=%d" % off, token=toks["u0"], base=base_b)[1]
            for p in pg["payments"]:
                seen[p["payment_id"]] = p
            if not pg["has_more"]:
                break
            off += 200
        for p in seen.values():
            net[p["from_handle"]] -= p["amount"]
            net[p["to_handle"]] += p["amount"]
        cons = sum(bals.values()) == total
        match = all(bals[h] == 1000 + net[h] for h, _ in users)
        ok_all &= (s == 204 and cons and match)
        detail.append({"import": s, "payments": len(seen), "sum_ok": cons, "balances_match_feed": match})
    # a later write does not change a snapshot already taken: re-importing an earlier export restores exactly it
    if exports:
        first = exports[0]
        call("POST", "/_test/import", first, base=base_b)
        v1 = call("GET", "/_test/export", base=base_b)[1]
        record("S1-175", "re-importing an earlier export reproduces it exactly (export of B == saved copy)",
               json.dumps(v1, sort_keys=True) == json.dumps(first, sort_keys=True), {})
    distinct = len({json.dumps(e, sort_keys=True) for e in exports})
    record("S1-175", "exports during 16 concurrent writers are consistent snapshots", ok_all and len(exports) >= 3 and distinct >= 2,
           {"exports": len(exports), "distinct": distinct, "detail": detail})
    reset(fixture([("zz", 1)]), base=base_b)


def p_signup_display_name():
    """S1-060 / D-09: empty display_name -> 422; missing -> 422; non-string -> 400."""
    reset(fixture([("aa", 0)]))
    a = call("POST", "/auth/signup", {"email": "dn1@audit.invalid", "password": "longenough1", "display_name": ""})
    b = call("POST", "/auth/signup", {"email": "dn2@audit.invalid", "password": "longenough1"})
    c = call("POST", "/auth/signup", {"email": "dn3@audit.invalid", "password": "longenough1", "display_name": 5})
    record("D-09", "display_name empty/missing 422, non-string 400",
           (a[0], code(a[1]), b[0], code(b[1]), c[0], code(c[1])) == (422, "validation_failed", 422, "validation_failed", 400, "malformed_request"),
           {"got": [a[0], b[0], c[0]]})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--base-b", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    ap.BASE = a.base
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for f in [p_content_type_all_endpoints, p_unknown_fields_everywhere, p_reset_content_errors, p_signup_display_name]:
        try:
            f()
        except Exception as e:
            record("ERROR", f.__name__, False, {"exception": repr(e)[:300]})
    for f in [p_import_tampered, p_export_during_writes]:
        try:
            f(a.base_b)
        except Exception as e:
            record("ERROR", f.__name__, False, {"exception": repr(e)[:300]})
    R = ap.RESULTS
    summ = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(r["pass"] for r in R), "failed": sum(not r["pass"] for r in R), "total": len(R), "results": R}
    json.dump(summ, open(a.out, "w"), indent=1, ensure_ascii=False)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

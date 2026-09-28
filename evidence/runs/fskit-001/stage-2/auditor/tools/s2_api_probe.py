#!/usr/bin/env python3
"""Auditor-owned stage-2 API probes (fskit-001). Stdlib only, synthetic data, no secrets written.
Keys: S2-011, S2-050..S2-071, superseded S1-001/002/070/090/091/092/196, D2-02/D2-03/D2-04.

usage: s2_api_probe.py --base URL --out results.json
"""
import argparse, json, sys, time, os
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, record, k


def fx(users, auths=(), ttl=None, operators=(), extra=None):
    f = ap.fixture(users, operators=operators)
    f["authorizations"] = list(auths)
    if ttl is not None:
        f["authorization_ttl_seconds"] = ttl
    if extra:
        f.update(extra)
    return f


def iso(offset_s):
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + offset_s))


def me(t):
    return call("GET", "/me", token=t)[1]


def auth(tok, to, amt, **kw):
    body = dict({"to_handle": to, "amount": amt}, **kw)
    return call("POST", "/authorizations", body, token=tok, key=k())


def cap(tok, aid, body=None, key=None):
    return call("POST", "/authorizations/%s/capture" % aid, {} if body is None else body, token=tok, key=key or k())


def p_me_and_hold():
    ap.reset(fx([("aa", 10000), ("bb", 0), ("cc", 0)]))
    ta, tb = ap.login("aa"), ap.login("bb")
    m0 = me(ta)
    record("S2-052", "GET /me fields with no holds", {"balance", "total", "available", "held"} <= set(m0) and
           m0["balance"] == m0["total"] == m0["available"] == 10000 and m0["held"] == 0, {"me": {x: m0.get(x) for x in ("balance", "total", "available", "held")}})
    s, a, _ = auth(ta, "bb", 2000, note="dep", visibility="private")
    m1 = me(ta)
    ok = (s == 201 and a["status"] == "open" and a["captured_amount"] == 0 and a["remaining_amount"] == 2000 and a["payment_id"] is None
          and a.get("payment_ids") == [] and a["currency"] == "EUR" and a["visibility"] == "private" and a["from_handle"] == "aa"
          and m1["total"] == m1["balance"] == 10000 and m1["held"] == 2000 and m1["available"] == 8000)
    record("S2-050/S2-058", "authorize creates hold, moves no money", ok, {"s": s, "me": {x: m1.get(x) for x in ("total", "available", "held")}})
    feed = [p["payment_id"] for p in call("GET", "/activity", token=ta)[1]["payments"]]
    record("S2-060", "open authorization not a feed item", feed == [], {"feed": feed})
    s2, j2, _ = auth(ta, "bb", 8001)
    s3, j3, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 8001}, token=ta, key=k())
    record("S2-059/S1-092", "held funds cannot back payment or authorization",
           (s2, code(j2), s3, code(j3)) == (409, "insufficient_funds", 409, "insufficient_funds"), {"s": [s2, s3]})
    s4, _, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 8000}, token=ta, key=k())
    m2 = me(ta)
    record("S1-002/S2-052", "spend exactly available -> available 0, hold intact", s4 == 201 and m2["available"] == 0 and m2["held"] == 2000 and m2["total"] == 2000,
           {"me": {x: m2.get(x) for x in ("total", "available", "held")}})
    # capture spends its own reservation although available is 0
    s5, p5, _ = cap(tb, a["authorization_id"], {"amount": 1500})
    m3, mb = me(ta), me(tb)
    ok = (s5 == 201 and p5.get("authorization_id") == a["authorization_id"] and p5.get("request_id") is None and p5["amount"] == 1500
          and p5["note"] == "dep" and p5["visibility"] == "private" and p5["from_handle"] == "aa" and p5["to_handle"] == "bb"
          and "settlement_id" in p5 and m3["total"] == 500 and m3["held"] == 0 and m3["available"] == 500 and mb["total"] == 1500)
    record("S2-062/S2-063", "final partial capture spends reservation, releases rest", ok,
           {"s": s5, "payer": {x: m3.get(x) for x in ("total", "available", "held")}, "recv": mb.get("total")})
    s6, j6, _ = cap(tb, a["authorization_id"], {"amount": 1})
    record("S2-063", "second capture after final -> 409 authorization_not_open", (s6, code(j6)) == (409, "authorization_not_open"), {"s": s6, "c": code(j6)})
    lst = call("GET", "/authorizations", token=ta)[1]
    it = [x for x in lst.get("authorizations", []) if x["authorization_id"] == a["authorization_id"]]
    record("S2-069/S2-064", "GET /authorizations shape and captured state", "has_more" in lst and it and it[0]["status"] == "captured"
           and it[0]["captured_amount"] == 1500 and it[0]["remaining_amount"] == 0 and it[0]["payment_id"] == p5["payment_id"],
           {"keys": sorted(lst), "item": {x: it[0].get(x) for x in ("status", "captured_amount", "remaining_amount")} if it else None})
    pf = [p for p in call("GET", "/payments-nonexistent", token=ta)[1] or []] if False else None
    feed_b = call("GET", "/activity", token=tb)[1]["payments"]
    record("S2-062/S1-199", "capture payment in feed with authorization_id; others null", any(p["payment_id"] == p5["payment_id"] and p["authorization_id"] == a["authorization_id"] for p in feed_b)
           and all("authorization_id" in p for p in feed_b), {})


def p_extended_capture():
    ap.reset(fx([("aa", 5000), ("bb", 0)]))
    ta, tb = ap.login("aa"), ap.login("bb")
    s, a, _ = auth(ta, "bb", 2000)
    aid = a["authorization_id"]
    r1 = cap(tb, aid, {"amount": 700, "final": False})
    r2 = cap(tb, aid, {"amount": 700, "final": False})
    st = call("GET", "/authorizations?status=open", token=ta)[1]["authorizations"]
    mid = [x for x in st if x["authorization_id"] == aid]
    r3x = cap(tb, aid, {"amount": 601, "final": False})
    r3 = cap(tb, aid, {"amount": 600, "final": False})
    fin = [x for x in call("GET", "/authorizations", token=ta)[1]["authorizations"] if x["authorization_id"] == aid][0]
    m = me(ta)
    ok = (r1[0] == 201 and r2[0] == 201 and mid and mid[0]["remaining_amount"] == 600 and mid[0]["captured_amount"] == 1400
          and (r3x[0], code(r3x[1])) == (422, "capture_exceeds_authorization") and r3[0] == 201 and fin["status"] == "captured"
          and fin["captured_amount"] == 2000 and fin["remaining_amount"] == 0 and fin["payment_ids"] == [r1[1]["payment_id"], r2[1]["payment_id"], r3[1]["payment_id"]]
          and fin["payment_id"] == r3[1]["payment_id"] and m["total"] == 3000 and m["held"] == 0)
    record("S2-064", "700/700/600 non-final captures; exceeds compares remainder; full remainder closes", ok,
           {"s": [r1[0], r2[0], r3x[0], r3[0]], "fin": {x: fin.get(x) for x in ("status", "captured_amount", "remaining_amount")}})
    # partial then void keeps capture records, releases only remainder
    s, b, _ = auth(ta, "bb", 1000)
    cap(tb, b["authorization_id"], {"amount": 300, "final": False})
    v = call("POST", "/authorizations/%s/void" % b["authorization_id"], None, token=ta)
    v2 = call("POST", "/authorizations/%s/void" % b["authorization_id"], None, token=ta)
    m = me(ta)
    record("S2-065/S2-068", "void after partial capture keeps records, releases rest; void twice 200",
           v[0] == 200 and v[1]["status"] == "voided" and v[1]["captured_amount"] == 300 and len(v[1]["payment_ids"]) == 1
           and v[1]["remaining_amount"] == 0 and v2[0] == 200 and m["held"] == 0 and m["total"] == 2700,
           {"v": v[0], "v2": v2[0], "me": {x: m.get(x) for x in ("total", "held")}})
    # omitted amount = remainder; {} vs {"amount":N} idempotency; final type
    s, c, _ = auth(ta, "bb", 400)
    key = k()
    e1 = cap(tb, c["authorization_id"], {}, key=key)
    e2 = cap(tb, c["authorization_id"], {}, key=key)
    e3 = cap(tb, c["authorization_id"], {"amount": 400}, key=key)
    e4 = cap(tb, c["authorization_id"], {"final": True}, key=key)
    record("S2-061/S2-066/D2-03", "omitted amount = remainder; replay 200; {} vs {amount} vs {final:true} -> 409",
           e1[0] == 201 and e1[1]["amount"] == 400 and e2[0] == 200 and e2[1] == e1[1] and (e3[0], code(e3[1])) == (409, "idempotency_key_reuse")
           and (e4[0], code(e4[1])) == (409, "idempotency_key_reuse"), {"s": [e1[0], e2[0], e3[0], e4[0]]})
    s, d, _ = auth(ta, "bb", 100)
    f1 = cap(tb, d["authorization_id"], {"final": "no"})
    f2 = cap(tb, d["authorization_id"], {"amount": 0})
    f3 = cap(tb, d["authorization_id"], {"amount": 1.5})
    f4 = cap(ta, d["authorization_id"], {})
    s5, cc, _ = call("POST", "/auth/signup", {"email": "third@audit.invalid", "password": "longenough1", "display_name": "T"})
    f5 = cap(cc["token"], d["authorization_id"], {})
    f6 = cap(tb, "a_does_not_exist", {})
    f7 = call("POST", "/authorizations/%s/void" % d["authorization_id"], None, token=tb)
    f8 = call("POST", "/authorizations/%s/void" % d["authorization_id"], None, token=cc["token"])
    got = [(x[0], code(x[1])) for x in (f1, f2, f3, f4, f5, f6, f7, f8)]
    exp = [(400, "malformed_request"), (422, "validation_failed"), (422, "validation_failed"), (403, "forbidden"), (403, "forbidden"),
           (404, "not_found"), (403, "forbidden"), (403, "forbidden")]
    record("S2-067/S2-068/D2-04", "capture/void error codes", got == exp, {"got": got})
    n1 = call("POST", "/authorizations/%s/capture" % d["authorization_id"], {}, token=tb)
    record("S1-070", "capture needs Idempotency-Key", (n1[0], code(n1[1])) == (400, "missing_idempotency_key"), {"s": n1[0]})
    n2 = call("POST", "/authorizations", {"to_handle": "bb", "amount": 1}, token=ta)
    record("S1-070", "authorize needs Idempotency-Key", (n2[0], code(n2[1])) == (400, "missing_idempotency_key"), {"s": n2[0]})


def p_expiry():
    ap.reset(fx([("aa", 5000), ("bb", 0)], ttl=2, auths=[
        {"id": "a_past", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 9999999, "note": "", "visibility": "public",
         "status": "open", "expires_at": iso(-7200)},
        {"id": "a_fut", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 1000, "note": "", "visibility": "public",
         "status": "open", "expires_at": iso(7200)}]))
    ta, tb = ap.login("aa"), ap.login("bb")
    m0 = me(ta)
    lst = {x["authorization_id"]: x for x in call("GET", "/authorizations", token=ta)[1]["authorizations"]}
    record("S2-054/S2-056/S2-028", "seeded past open = expired, holds nothing; seeded future holds", m0["held"] == 1000 and m0["available"] == 4000
           and lst["a_past"]["status"] == "expired" and lst["a_fut"]["status"] == "open", {"me": {x: m0.get(x) for x in ("available", "held")}})
    s, a, _ = auth(ta, "bb", 700)
    ca = time.mktime(time.strptime(a["created_at"][:19], "%Y-%m-%dT%H:%M:%S"))
    ea = time.mktime(time.strptime(a["expires_at"][:19], "%Y-%m-%dT%H:%M:%S"))
    record("S2-055", "expires_at = created_at + ttl(2)", s == 201 and ea - ca == 2, {"created": a.get("created_at"), "expires": a.get("expires_at")})
    s, b, _ = auth(ta, "bb", 300)
    cap(tb, b["authorization_id"], {"amount": 100, "final": False})
    time.sleep(3.2)
    m1 = me(ta)
    ex = [x["authorization_id"] for x in call("GET", "/authorizations?status=expired", token=ta)[1]["authorizations"]]
    op = [x["authorization_id"] for x in call("GET", "/authorizations?status=open", token=ta)[1]["authorizations"]]
    c = cap(tb, a["authorization_id"], {})
    v = call("POST", "/authorizations/%s/void" % a["authorization_id"], None, token=ta)
    bb_ = [x for x in call("GET", "/authorizations", token=ta)[1]["authorizations"] if x["authorization_id"] == b["authorization_id"]][0]
    ok = (m1["held"] == 1000 and m1["available"] == 5000 - 100 - 1000 and a["authorization_id"] in ex and b["authorization_id"] in ex
          and a["authorization_id"] not in op and (c[0], code(c[1])) == (409, "authorization_expired") and (v[0], code(v[1])) == (409, "authorization_not_open")
          and bb_["captured_amount"] == 100 and bb_["remaining_amount"] == 0)
    record("S2-057/S2-065/D2-08", "clock expiry with no request at deadline; capture 409 expired; void 409 not_open",
           ok, {"me": {x: m1.get(x) for x in ("available", "held")}, "cap": (c[0], code(c[1])), "void": (v[0], code(v[1]))})
    bad = {}
    for ttl in [0, -1, 1.5, "600", True]:
        s, j, _ = call("POST", "/_test/reset", fx([("aa", 1)], ttl=ttl))
        bad[str(ttl)] = (s, code(j))
    record("S2-055", "bad ttl -> reset 422", all(v == (422, "validation_failed") for v in bad.values()), bad)
    s, j, _ = call("POST", "/_test/reset", fx([("aa", 100), ("bb", 0)], auths=[
        {"id": "a1", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 101, "note": "", "visibility": "public", "status": "open", "expires_at": iso(7200)}]))
    s2, j2, _ = call("POST", "/_test/reset", fx([("aa", 100), ("bb", 0)], auths=[
        {"id": "a1", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 101, "note": "", "visibility": "public", "status": "open", "expires_at": iso(-7200)},
        {"id": "a2", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 500, "note": "", "visibility": "public", "status": "voided", "expires_at": iso(7200)}]))
    record("S2-056", "seeded unexpired open holds > balance -> 422; expired/closed don't count", (s, code(j), s2) == (422, "validation_failed", 204), {"s": [s, s2]})


def p_settlement_vs_holds():
    ap.reset(fx([("op", 0), ("aa", 1000), ("bb", 0)], operators=["op"]))
    to, ta = ap.login("op"), ap.login("aa")
    auth(ta, "bb", 600)
    s, j, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 401}]}, token=to, key=k())
    s2, _, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 400}]}, token=to, key=k())
    m = me(ta)
    record("S1-196(sup)/S1-002", "settlement net debit cannot eat held funds", (s, code(j), s2) == (409, "insufficient_funds", 201) and m["available"] == 0 and m["held"] == 600,
           {"s": [s, s2], "me": {x: m.get(x) for x in ("total", "available", "held")}})


def p_accept_header():
    ap.reset(fx([("aa", 1)]))
    ta = ap.login("aa")
    import urllib.request
    out = {}
    for path in ("/requests", "/authorizations"):
        for acc in (None, "text/html", "application/json"):
            req = urllib.request.Request(ap.BASE + path)
            req.add_header("Authorization", "Bearer " + ta)
            if acc:
                req.add_header("Accept", acc)
            with urllib.request.urlopen(req, timeout=10) as r:
                out["%s %s" % (path, acc)] = (r.status, (r.headers.get("Content-Type") or "").split(";")[0])
    ok = all(v == (200, "application/json") for kk, v in out.items() if "text/html" not in kk) and all(
        v[1] == "text/html" for kk, v in out.items() if "text/html" in kk)
    record("S2-011", "Accept text/html -> UI, else JSON", ok, out)


def p_concurrency():
    ap.reset(fx([("op", 0), ("aa", 3000), ("bb", 3000), ("cc", 0)], operators=["op"]))
    to, ta, tb, tc = ap.login("op"), ap.login("aa"), ap.login("bb"), ap.login("cc")
    s, a, _ = auth(ta, "cc", 1500)
    aid = a["authorization_id"]
    jobs = [lambda: cap(tc, aid, {"amount": 100, "final": False}) for _ in range(20)]
    jobs += [lambda: call("POST", "/authorizations/%s/void" % aid, None, token=ta)]
    jobs += [lambda: call("POST", "/payments", {"to_handle": "cc", "amount": 90}, token=ta, key=k()) for _ in range(20)]
    jobs += [lambda: auth(tb, "cc", 150) for _ in range(20)]
    jobs += [lambda: call("POST", "/settlements", {"transfers": [{"from_handle": "bb", "to_handle": "aa", "amount": 50}]}, token=to, key=k()) for _ in range(10)]
    reads = []

    def reader():
        for _ in range(30):
            for t in (ta, tb):
                m = me(t)
                reads.append((m["total"], m["available"], m["held"]))
    with ThreadPoolExecutor(50) as ex:
        fr = ex.submit(reader)
        rs = list(ex.map(lambda f: f(), jobs))
        fr.result()
    ms = [me(t) for t in (to, ta, tb, tc)]
    tot = sum(m["total"] for m in ms)
    au = [x for x in call("GET", "/authorizations?limit=200", token=ta)[1]["authorizations"] if x["authorization_id"] == aid][0]
    caps = sum(1 for r in rs[:20] if r[0] == 201)
    ok = (tot == 6000 and all(m["available"] >= 0 and m["available"] == m["total"] - m["held"] for m in ms)
          and all(av >= 0 and av == t - h for t, av, h in reads) and not any(r[0] >= 500 for r in rs)
          and au["captured_amount"] == 100 * caps and au["captured_amount"] <= 1500)
    record("S2-051/S2-070/S2-071", "mixed concurrent captures/void/payments/authorizations/settlements", ok,
           {"total": tot, "caps201": caps, "auth": {x: au.get(x) for x in ("status", "captured_amount", "remaining_amount")},
            "reads": len(reads), "outcomes": sorted(set(str((r[0], code(r[1]))) for r in rs))})
    # same-key concurrent capture and authorize
    s, b, _ = auth(tb, "cc", 50)
    key = k()
    with ThreadPoolExecutor(15) as ex:
        rs = list(ex.map(lambda _: cap(tc, b["authorization_id"], {"amount": 50}, key=key), range(15)))
    key2 = k()
    with ThreadPoolExecutor(15) as ex:
        rs2 = list(ex.map(lambda _: call("POST", "/authorizations", {"to_handle": "cc", "amount": 5}, token=tb, key=key2), range(15)))
    record("S1-078(sup)", "15x concurrent same key on capture and authorize",
           [r[0] for r in rs].count(201) == 1 and [r[0] for r in rs].count(200) == 14 and len({json.dumps(r[1], sort_keys=True) for r in rs}) == 1
           and [r[0] for r in rs2].count(201) == 1 and [r[0] for r in rs2].count(200) == 14, {})


def p_r2_rows():
    """S2-072, S2-073, S2-056 boundary, D2-15, S1-112(sup), S2-060/069 operator + voided not in feed."""
    ap.reset(fx([("op", 0), ("aa", 1000), ("bb", 0)], operators=["op"]))
    to, ta, tb = ap.login("op"), ap.login("aa"), ap.login("bb")
    ak = k()
    s, a, _ = call("POST", "/authorizations", {"to_handle": "bb", "amount": 1000}, token=ta, key=ak)
    m0 = me(ta)
    s_rq, rq, _ = call("POST", "/requests", {"payer_handle": "aa", "amount": 1}, token=tb, key=k())
    pr = call("POST", "/requests/%s/pay" % rq["request_id"], {}, token=ta, key=k())
    ck = k()
    c1 = cap(tb, a["authorization_id"], {"amount": 400}, key=ck)
    m1 = me(ta)
    record("S2-072/S1-112(sup)", "available 0: pay request with held money 409; capture still spends reservation; final partial releases rest",
           m0["available"] == 0 and (pr[0], code(pr[1])) == (409, "insufficient_funds") and c1[0] == 201 and m1["total"] == 600 and m1["held"] == 0 and m1["available"] == 600,
           {"pay": pr[0], "cap": c1[0], "me": {x: m1.get(x) for x in ("total", "available", "held")}})
    r1 = call("POST", "/authorizations", {"to_handle": "bb", "amount": 1000}, token=ta, key=ak)
    r2 = cap(tb, a["authorization_id"], {"amount": 400}, key=ck)
    r3 = cap(tb, a["authorization_id"], {"amount": 99999}, key=ck)
    record("S2-073", "replay authorize after capture -> 200 original (open); replay capture -> 200; claimed key + invalid body -> 409",
           r1[0] == 200 and r1[1] == a and r1[1]["status"] == "open" and r2[0] == 200 and r2[1] == c1[1] and (r3[0], code(r3[1])) == (409, "idempotency_key_reuse"),
           {"s": [r1[0], r2[0], r3[0]]})
    s, b, _ = auth(ta, "bb", 100)
    fk = k()
    f1 = cap(tb, b["authorization_id"], {"amount": 101}, key=fk)
    f2 = cap(tb, b["authorization_id"], {"amount": 50}, key=fk)
    v = call("POST", "/authorizations/%s/void" % b["authorization_id"], None, token=ta)
    f3 = cap(tb, b["authorization_id"], {"amount": 50}, key=fk)
    record("S2-073", "failed capture key reusable; replay after void -> 200 original payment",
           (f1[0], code(f1[1])) == (422, "capture_exceeds_authorization") and f2[0] == 201 and v[0] == 200 and f3[0] == 200 and f3[1] == f2[1],
           {"s": [f1[0], f2[0], v[0], f3[0]]})
    feed = [p["payment_id"] for p in call("GET", "/activity?limit=200", token=ta)[1]["payments"]]
    opl = call("GET", "/authorizations", token=to)[1]["authorizations"]
    record("S2-060/S2-069", "only capture payments in feed; operator sees no others' authorizations",
           set(feed) == {c1[1]["payment_id"], f2[1]["payment_id"]} and opl == [], {"feed": len(feed), "operator_list": len(opl)})
    s, j, _ = call("POST", "/_test/reset", fx([("aa", 100), ("bb", 0)], auths=[
        {"id": "a1", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 100, "note": "", "visibility": "public", "status": "open", "expires_at": iso(7200)}]))
    tae = ap.login("aa")
    m = me(tae)
    record("S2-056", "seeded open holds == balance -> 204, available 0", s == 204 and m["available"] == 0 and m["held"] == 100, {"s": s})
    base_ok = fx([("aa", 100), ("bb", 0)])
    ap.reset(base_ok)
    tok = ap.login("aa")
    good = {"id": "a1", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 10, "note": "", "visibility": "public", "status": "open", "expires_at": iso(7200)}
    muts = {"unknown user": dict(good, to_user_id="u_ghost"), "from=to": dict(good, to_user_id="u_aa"), "amount 0": dict(good, amount=0),
            "amount 1.5": dict(good, amount=1.5), "status bad": dict(good, status="pending"), "expires missing": {x: v for x, v in good.items() if x != "expires_at"},
            "expires no offset": dict(good, expires_at="2030-01-01T00:00:00"), "expires garbage": dict(good, expires_at="soon")}
    res = {}
    for n, a_ in muts.items():
        s, j, _ = call("POST", "/_test/reset", fx([("aa", 100), ("bb", 0)], auths=[a_]))
        res[n] = (s, code(j), call("GET", "/me", token=tok)[0])
    s, j, _ = call("POST", "/_test/reset", fx([("aa", 100), ("bb", 0)], auths=[good, dict(good)]))
    res["duplicate id"] = (s, code(j), call("GET", "/me", token=tok)[0])
    record("D2-15", "authorization fixture errors -> 422, previous state intact", all(v == (422, "validation_failed", 200) for v in res.values()), res)


def p_export_expiry(base_b):
    """S2-074: hold exported before expires_at, imported after it -> expired, holds nothing (two containers)."""
    ap.reset(fx([("aa", 1000), ("bb", 0)], ttl=2))
    ta = ap.login("aa")
    s, a, _ = auth(ta, "bb", 300)
    s, ex, _ = call("GET", "/_test/export")
    time.sleep(3.2)
    s2, _, _ = call("POST", "/_test/import", ex, base=base_b)
    m = call("GET", "/me", token=ta, base=base_b)[1]
    st = [x for x in call("GET", "/authorizations", token=ta, base=base_b)[1]["authorizations"] if x["authorization_id"] == a["authorization_id"]]
    record("S2-074", "exported open hold imported after expiry reads expired", s2 == 204 and m["held"] == 0 and m["available"] == 1000 and st and st[0]["status"] == "expired",
           {"import": s2, "me": {x: m.get(x) for x in ("available", "held")}, "status": st[0]["status"] if st else None})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--base-b", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    ap.BASE = a.base
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for f in (p_me_and_hold, p_extended_capture, p_expiry, p_settlement_vs_holds, p_accept_header, p_concurrency, p_r2_rows):
        try:
            f()
        except Exception as e:
            record("ERROR", f.__name__, False, {"exception": repr(e)[:400]})
    try:
        p_export_expiry(a.base_b)
    except Exception as e:
        record("ERROR", "p_export_expiry", False, {"exception": repr(e)[:400]})
    R = ap.RESULTS
    summ = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(r["pass"] for r in R), "failed": sum(not r["pass"] for r in R), "total": len(R), "results": R}
    json.dump(summ, open(a.out, "w"), indent=1, ensure_ascii=False)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

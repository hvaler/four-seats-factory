#!/usr/bin/env python3
"""Auditor-owned independent probes for fskit-001 stage 1 (Pocketful).

Stdlib only. Black-box HTTP against a running candidate container.
Each probe is keyed by obligation ID and cites the spec clause it checks.
Synthetic fixture only; no tokens or export contents are written to disk.

usage: audit_probe.py --base http://127.0.0.1:PORT [--base-b http://127.0.0.1:PORT2] --out results.json
"""
import argparse, json, threading, time, urllib.request, urllib.error, uuid, re, sys
from concurrent.futures import ThreadPoolExecutor

BASE = None
RESULTS = []


def call(method, path, body=None, token=None, key=None, raw=None, base=None, timeout=15):
    url = (base or BASE) + path
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if key is not None:
        req.add_header("Idempotency-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else None), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            j = json.loads(txt) if txt else None
        except ValueError:
            j = {"_raw": txt}
        return e.code, j, e.headers.get("Content-Type")


def code(j):
    return (j or {}).get("error", {}).get("code") if isinstance(j, dict) else None


def record(ob, name, ok, detail):
    RESULTS.append({"obligation": ob, "probe": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + ob + " " + name + " :: " + json.dumps(detail)[:300], flush=True)


def fixture(users, operators=(), payments=(), requests=(), cur="EUR", mu=2):
    return {"currency": cur, "minor_units": mu,
            "users": [{"id": "u_" + h, "email": h + "@audit.invalid", "password": "pw-" + h + "-12345",
                       "display_name": h.upper(), "handle": h, "balance": b} for h, b in users],
            "payments": list(payments), "requests": list(requests),
            "settlement_operator_ids": ["u_" + h for h in operators]}


def reset(fx, base=None):
    s, j, _ = call("POST", "/_test/reset", fx, base=base)
    assert s == 204, ("reset", s, j)


def login(h, base=None):
    s, j, _ = call("POST", "/auth/login", {"email": h + "@audit.invalid", "password": "pw-" + h + "-12345"}, base=base)
    assert s == 200, ("login", h, s, j)
    return j["token"]


def bal(tok, base=None):
    return call("GET", "/me", token=tok, base=base)[1]["balance"]


def k():
    return "aud-" + uuid.uuid4().hex


# ---------------------------------------------------------------- probes

def p_conservation_concurrent():
    """S1-001, S1-002, S1-058: 50 concurrent debits from one wallet exceeding its balance."""
    users = [("src", 1000)] + [("d%d" % i, 0) for i in range(5)]
    reset(fixture(users))
    t = login("src")
    toks = {h: login(h) for h, _ in users}

    def pay(i):
        return call("POST", "/payments", {"to_handle": "d%d" % (i % 5), "amount": 50}, token=t, key=k())
    with ThreadPoolExecutor(50) as ex:
        rs = list(ex.map(pay, range(50)))
    st = [r[0] for r in rs]
    ok201 = st.count(201)
    other = [(s, code(j)) for s, j, _ in rs if s != 201]
    final = {h: bal(toks[h]) for h, _ in users}
    total = sum(final.values())
    record("S1-001/S1-002", "50 concurrent debits of 50 from 1000",
           ok201 == 20 and final["src"] == 0 and total == 1000 and all(o == (409, "insufficient_funds") for o in other)
           and not any(s >= 500 for s in st),
           {"201": ok201, "others": sorted(set(map(str, other))), "final": final, "total": total})


def p_pay_at_most_once():
    """S1-003: concurrent pay (distinct keys) + decline + cancel race on one request."""
    reset(fixture([("req", 0), ("pyr", 5000)]))
    tr, tp = login("req"), login("pyr")
    s, rq, _ = call("POST", "/requests", {"payer_handle": "pyr", "amount": 700}, token=tr, key=k())
    rid = rq["request_id"]
    jobs = [lambda: call("POST", "/requests/%s/pay" % rid, {}, token=tp, key=k()) for _ in range(20)]
    jobs += [lambda: call("POST", "/requests/%s/decline" % rid, token=tp),
             lambda: call("POST", "/requests/%s/cancel" % rid, token=tr)]
    with ThreadPoolExecutor(22) as ex:
        rs = list(ex.map(lambda f: f(), jobs))
    pays = rs[:20]
    n201 = sum(1 for s, _, _ in pays if s == 201)
    b_req, b_pyr = bal(tr), bal(tp)
    moved = 5000 - b_pyr
    record("S1-003", "20 pays + decline + cancel racing",
           n201 <= 1 and moved in (0, 700) and (moved == 700) == (n201 == 1) and b_req + b_pyr == 5000
           and not any(s >= 500 for s, _, _ in rs),
           {"pay201": n201, "moved": moved, "statuses": sorted(set(s for s, _, _ in rs))})


def p_idem_concurrent_all_paths():
    """S1-078: concurrent identical requests with an unused key, on all five paths."""
    reset(fixture([("aa", 100000), ("bb", 100000), ("op", 0)], operators=["op"]))
    ta, tb, to = login("aa"), login("bb"), login("op")
    s, rq, _ = call("POST", "/requests", {"payer_handle": "aa", "amount": 10}, token=tb, key=k())
    cases = {
        "payments": ("/payments", {"to_handle": "bb", "amount": 7}, ta),
        "requests": ("/requests", {"payer_handle": "bb", "amount": 7}, ta),
        "pay": ("/requests/%s/pay" % rq["request_id"], {"visibility": "private"}, ta),
        "splits": ("/splits", {"amount": 9, "participant_handles": ["aa", "bb"]}, ta),
        "settlements": ("/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 3}]}, to),
    }
    for name, (path, body, tok) in cases.items():
        key = k()
        before = (bal(ta), bal(tb))
        with ThreadPoolExecutor(15) as ex:
            rs = list(ex.map(lambda _: call("POST", path, body, token=tok, key=key), range(15)))
        st = [s for s, _, _ in rs]
        bodies = [json.dumps(j, sort_keys=True) for _, j, _ in rs]
        after = (bal(ta), bal(tb))
        delta = before[0] - after[0]
        exp = {"payments": 7, "requests": 0, "pay": 10, "splits": 0, "settlements": 3}[name]
        record("S1-078", "15x concurrent same key " + name,
               st.count(201) == 1 and st.count(200) == 14 and len(set(bodies)) == 1 and delta == exp,
               {"statuses": {x: st.count(x) for x in set(st)}, "distinct_bodies": len(set(bodies)), "debit": delta})


def p_idem_semantics():
    """S1-071..S1-077, S1-080, S1-111, S1-113."""
    reset(fixture([("aa", 10000), ("bb", 0), ("cc", 0)]))
    ta, tb = login("aa"), login("bb")
    key = k()
    s1, j1, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 100, "note": "x"}, token=ta, key=key)
    s2, j2, _ = call("POST", "/payments", raw=b'{ "note":"x",  "amount":1e2, "to_handle":"bb"}', token=ta, key=key)
    record("S1-074/S1-077", "replay reordered + 1e2 form", s1 == 201 and s2 == 200 and j1 == j2, {"s": [s1, s2]})
    s3, j3, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 101, "note": "x"}, token=ta, key=key)
    record("S1-075", "same key different body", s3 == 409 and code(j3) == "idempotency_key_reuse", {"s": s3, "c": code(j3)})
    s4, j4, _ = call("POST", "/payments", {"to_handle": "bb", "amount": "bad"}, token=ta, key=key)
    record("S1-080", "claimed key + invalid body -> 409", s4 == 409 and code(j4) == "idempotency_key_reuse", {"s": s4, "c": code(j4)})
    s5, j5, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 100, "note": "x"}, token=ta, key=key)
    record("S1-072", "same key other path -> 201", s5 == 201, {"s": s5, "c": code(j5)})
    s6, _, _ = call("POST", "/payments", {"to_handle": "aa", "amount": 100, "note": "x"}, token=tb, key=key)
    # bb holds exactly 100 (received above); aa's key must not affect bb -> bb's own first use -> 201
    record("S1-071", "other user same key -> own first use", s6 == 201, {"s": s6})
    fk = k()
    sf, jf, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 999999}, token=ta, key=fk)
    sg, _, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 5}, token=ta, key=fk)
    record("S1-076", "failed-4xx key reusable with different body", sf == 409 and sg == 201, {"s": [sf, sg]})
    s, rq, _ = call("POST", "/requests", {"payer_handle": "aa", "amount": 50}, token=tb, key=k())
    pk = k()
    p1, pj1, _ = call("POST", "/requests/%s/pay" % rq["request_id"], {}, token=ta, key=pk)
    p2, pj2, _ = call("POST", "/requests/%s/pay" % rq["request_id"], {}, token=ta, key=pk)
    p3, pj3, _ = call("POST", "/requests/%s/pay" % rq["request_id"], {"visibility": "public"}, token=ta, key=pk)
    record("S1-113/S1-111", "pay replay 200 after paid; {} vs public -> 409",
           p1 == 201 and p2 == 200 and pj1 == pj2 and p3 == 409 and code(pj3) == "idempotency_key_reuse",
           {"s": [p1, p2, p3], "c3": code(pj3)})
    s, _, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1}, token=ta, key="")
    s7, j7, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1}, token=ta)
    s8, j8, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1}, token=ta, key="x" * 256)
    s9, _, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1}, token=ta, key="y" * 255)
    record("S1-052/S1-057", "key empty/absent 400, 256 -> 422, 255 ok",
           s == 400 and s7 == 400 and code(j7) == "missing_idempotency_key" and s8 == 422 and s9 == 201,
           {"s": [s, s7, s8, s9]})


def p_amount_forms():
    """S1-031, S1-055, S1-093."""
    reset(fixture([("aa", 10 ** 10), ("bb", 0)]))
    ta = login("aa")
    ok = {}
    for raw in ["1000", "1000.0", "1e3", "1E3", "1000000000"]:
        s, j, _ = call("POST", "/payments", raw=('{"to_handle":"bb","amount":%s}' % raw).encode(), token=ta, key=k())
        ok[raw] = (s, (j or {}).get("amount"))
    bad = {}
    for raw in ['"1000"', "true", "false", "1000.5", "0", "-1", "1000000001", "1e10"]:
        s, j, _ = call("POST", "/payments", raw=('{"to_handle":"bb","amount":%s}' % raw).encode(), token=ta, key=k())
        bad[raw] = (s, code(j))
    obs = {}
    for raw in ["null", "[1]", "{}"]:  # spec-ambiguous (400 vs 422): observed only, not asserted
        s, j, _ = call("POST", "/payments", raw=('{"to_handle":"bb","amount":%s}' % raw).encode(), token=ta, key=k())
        obs[raw] = (s, code(j))
    record("OBS", "amount null/array/object (not asserted)", all(v[0] in (400, 422) for v in obs.values()), obs)
    record("S1-031", "integral numeric forms accepted",
           all(v[0] == 201 for v in ok.values()) and ok["1e3"][1] == 1000 and isinstance(ok["1e3"][1], int), ok)
    record("S1-055/S1-093", "invalid amounts -> 422 validation_failed",
           all(v == (422, "validation_failed") for v in bad.values()), bad)
    notes = {}
    for raw in ["null", "5", "true"]:
        s, j, _ = call("POST", "/payments", raw=('{"to_handle":"bb","amount":1,"note":%s}' % raw).encode(), token=ta, key=k())
        notes[raw] = (s, code(j))
    for raw in ['"PUBLIC"', "null", "1"]:
        s, j, _ = call("POST", "/payments", raw=('{"to_handle":"bb","amount":1,"visibility":%s}' % raw).encode(), token=ta, key=k())
        notes["vis " + raw] = (s, code(j))
    record("S1-055", "note/visibility wrong -> 422", all(v == (422, "validation_failed") for v in notes.values()), notes)
    s, j, _ = call("POST", "/payments", raw=b'{"to_handle":1,"amount":1}', token=ta, key=k())
    s2, j2, _ = call("POST", "/payments", raw=b'{"to_handle":', token=ta, key=k())
    s3, j3, _ = call("POST", "/payments", raw=b'[1]', token=ta, key=k())
    record("S1-051", "wrong-type handle / unparseable / non-object -> 400",
           (s, code(j), s2, code(j2), s3, code(j3)) == (400, "malformed_request", 400, "malformed_request", 400, "malformed_request"),
           {"s": [s, s2, s3]})
    emo = "  héllo 👋🏽 <b>&amp; é é  "
    s, j, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1, "note": emo}, token=ta, key=k())
    record("S1-098", "note verbatim unicode round-trip", s == 201 and j["note"] == emo, {"s": s})
    n200 = "é" * 200
    s, _, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1, "note": n200}, token=ta, key=k())
    s2, j2, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1, "note": n200 + "é"}, token=ta, key=k())
    record("S1-095", "note 200 ok / 201 -> 422", s == 201 and s2 == 422, {"s": [s, s2]})


def p_splits():
    """S1-140..S1-143, S1-160, S1-161."""
    reset(fixture([("aa", 0), ("bb", 0), ("cc", 0), ("dd", 0), ("ee", 0)]))
    ta = login("aa")
    table = [(1000, ["aa", "bb", "cc"], [334, 333, 333]), (1, ["aa", "bb", "cc"], [1, 0, 0]),
             (10, ["aa", "bb", "cc"], [4, 3, 3]), (999, ["aa", "bb", "cc"], [333, 333, 333]),
             (5, ["aa", "bb", "cc", "dd", "ee"], [1] * 5), (1000, ["cc", "aa", "bb"], [334, 333, 333]),
             (1000000000, ["bb", "cc", "dd", "ee", "aa"], [200000000] * 5), (7, ["bb", "cc"], [4, 3])]
    for amt, hs, exp in table:
        s, j, _ = call("POST", "/splits", {"amount": amt, "participant_handles": hs, "note": "s"}, token=ta, key=k())
        shares = [x["amount"] for x in j.get("shares", [])] if s == 201 else None
        rq = [(r["payer_handle"], r["amount"], r["requester_handle"], r["status"]) for r in j.get("requests", [])] if s == 201 else None
        exp_rq = [(h, a, "aa", "pending") for h, a in zip(hs, exp) if h != "aa"]
        record("S1-160/S1-140", "split %d over %s" % (amt, hs),
               s == 201 and shares == exp and [x["handle"] for x in j["shares"]] == hs and rq == exp_rq,
               {"s": s, "shares": shares})
    s, j, _ = call("POST", "/splits", {"amount": 5, "participant_handles": ["aa"]}, token=ta, key=k())
    record("S1-142", "self-only split", s == 201 and j["requests"] == [] and len(j["shares"]) == 1, {"s": s})
    for body, exp in [({"amount": 5, "participant_handles": []}, (422, "validation_failed")),
                      ({"amount": 5, "participant_handles": ["bb", "bb"]}, (422, "validation_failed")),
                      ({"amount": 5, "participant_handles": ["bb", "zz"]}, (404, "not_found"))]:
        s, j, _ = call("POST", "/splits", body, token=ta, key=k())
        record("S1-141", "split invalid " + json.dumps(body), (s, code(j)) == exp, {"s": s, "c": code(j)})


def p_settlements():
    """S1-192..S1-201."""
    fx = fixture([("op", 0), ("aa", 100), ("bb", 0), ("cc", 0)], operators=["op"])
    reset(fx)
    to, ta, tb, tc = login("op"), login("aa"), login("bb"), login("cc")
    s, j, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 1}]}, token=ta, key=k())
    s0, j0, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 1}]}, key=k())
    record("S1-192", "non-operator 403, no token 401", (s, code(j), s0) == (403, "forbidden", 401), {"s": [s, s0]})
    # netting: bb has 0 and pays 150 to cc before receiving 150 from aa? aa only has 100.
    # chain: aa->bb 100, bb->cc 100 (bb short sequentially only if order reversed)
    body = {"transfers": [{"from_handle": "bb", "to_handle": "cc", "amount": 100},
                          {"from_handle": "aa", "to_handle": "bb", "amount": 100, "visibility": "private", "note": "n"}]}
    key = k()
    s, j, _ = call("POST", "/settlements", body, token=to, key=key)
    ok = s == 201 and [p["amount"] for p in j["payments"]] == [100, 100] and all(
        p["settlement_id"] == j["settlement_id"] and p["request_id"] is None and p["created_at"] == j["committed_at"] for p in j["payments"])
    record("S1-196/S1-198", "net-affordable reversed chain commits; member shape", ok,
           {"s": s, "bal": [bal(ta), bal(tb), bal(tc)]})
    s2, j2, _ = call("POST", "/settlements", body, token=to, key=key)
    record("S1-201", "settlement replay 200 identical", s2 == 200 and j2 == j, {"s": s2})
    # visibility: private member hidden from operator and cc (third parties)
    feed_op = [p["payment_id"] for p in call("GET", "/activity?limit=200", token=to)[1]["payments"]]
    feed_cc = [p["payment_id"] for p in call("GET", "/activity?limit=200", token=tc)[1]["payments"]]
    priv = j["payments"][1]["payment_id"]
    record("S1-200/S1-191", "private member hidden from operator & third party", priv not in feed_op and priv not in feed_cc,
           {"in_op": priv in feed_op, "in_cc": priv in feed_cc})
    # insufficient by 1 -> 409, nothing moves, key reusable
    before = [bal(ta), bal(tb), bal(tc)]
    key2 = k()
    s, j, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "cc", "to_handle": "aa", "amount": 50},
                                                          {"from_handle": "cc", "to_handle": "bb", "amount": 51}]}, token=to, key=key2)
    after = [bal(ta), bal(tb), bal(tc)]
    s3, _, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "cc", "to_handle": "aa", "amount": 50}]}, token=to, key=key2)
    record("S1-196/S1-197", "net short by 1 -> 409 atomic, key reusable", (s, code(j)) == (409, "insufficient_funds") and before == after and s3 == 201,
           {"s": [s, s3], "before": before, "after": after})
    # precedence in input order
    s, j, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "zz", "to_handle": "aa", "amount": 1},
                                                          {"from_handle": "aa", "to_handle": "aa", "amount": 1}]}, token=to, key=k())
    s2, j2, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "aa", "amount": 1},
                                                            {"from_handle": "zz", "to_handle": "aa", "amount": 1}]}, token=to, key=k())
    s3, j3, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "cc", "to_handle": "aa", "amount": 10 ** 9},
                                                            {"from_handle": "zz", "to_handle": "aa", "amount": 1}]}, token=to, key=k())
    record("S1-195", "entry errors in input order, before funds",
           (s, code(j), s2, code(j2), s3, code(j3)) == (404, "not_found", 422, "self_payment", 404, "not_found"),
           {"got": [s, code(j), s2, code(j2), s3, code(j3)]})
    for n, exp in [(0, 422), (33, 422), (32, 201)]:
        tr = [{"from_handle": "aa", "to_handle": "bb", "amount": 1}] * n
        s, j, _ = call("POST", "/settlements", {"transfers": tr}, token=to, key=k())
        record("S1-193", "transfers count %d" % n, s == exp, {"s": s, "c": code(j)})
    reset(fx)
    t_all = [login(h) for h in ("op", "aa", "bb", "cc")]
    record("S1-001", "sum after settlements (post-reset baseline)", sum(bal(t) for t in t_all) == 100, {})


def p_settlement_concurrency():
    """S1-203: concurrent settlements + payments from the same wallets."""
    reset(fixture([("op", 0), ("aa", 1000), ("bb", 1000), ("cc", 0)], operators=["op"]))
    to, ta, tb, tc = login("op"), login("aa"), login("bb"), login("cc")
    jobs = []
    for i in range(20):
        jobs.append(lambda: call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "cc", "amount": 90},
                                                                        {"from_handle": "bb", "to_handle": "aa", "amount": 40}]}, token=to, key=k()))
        jobs.append(lambda: call("POST", "/payments", {"to_handle": "cc", "amount": 60}, token=ta, key=k()))
        jobs.append(lambda: call("POST", "/payments", {"to_handle": "cc", "amount": 60}, token=tb, key=k()))
    with ThreadPoolExecutor(50) as ex:
        rs = list(ex.map(lambda f: f(), jobs))
    b = [bal(t) for t in (to, ta, tb, tc)]
    st = sorted(set((s, code(j)) for s, j, _ in rs), key=str)
    record("S1-203", "concurrent settlements+payments", sum(b) == 2000 and min(b) >= 0 and not any(s >= 500 for s, _, _ in rs),
           {"bal": b, "outcomes": [str(x) for x in st]})


def p_visibility_auth():
    """S1-039, S1-040, S1-053, S1-120, S1-121, S1-190."""
    reset(fixture([("aa", 1000), ("bb", 1000), ("cc", 1000)]))
    ta, tb, tc = login("aa"), login("bb"), login("cc")
    s, pv, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1, "visibility": "private"}, token=ta, key=k())
    s, pu, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 1}, token=ta, key=k())
    f = {h: [p["payment_id"] for p in call("GET", "/activity", token=t)[1]["payments"]] for h, t in (("aa", ta), ("bb", tb), ("cc", tc))}
    record("S1-039", "feed iff public or party", pv["payment_id"] in f["aa"] and pv["payment_id"] in f["bb"] and pv["payment_id"] not in f["cc"]
           and pu["payment_id"] in f["cc"], {})
    s, rq, _ = call("POST", "/requests", {"payer_handle": "bb", "amount": 5}, token=ta, key=k())
    rc = [r["request_id"] for r in call("GET", "/requests", token=tc)[1]["requests"]]
    record("S1-040", "third party cannot list request", rq["request_id"] not in rc, {})
    outs = {}
    for hdr in [None, "Bearer", "Bearer nope", "Basic abc"]:
        req = urllib.request.Request(BASE + "/me")
        if hdr:
            req.add_header("Authorization", hdr)
        try:
            urllib.request.urlopen(req, timeout=10); outs[str(hdr)] = 200
        except urllib.error.HTTPError as e:
            outs[str(hdr)] = (e.code, code(json.loads(e.read().decode() or "null")))
    record("S1-053", "unauthenticated variants", all(v == (401, "unauthenticated") for v in outs.values()), outs)
    rid = rq["request_id"]
    r1 = call("POST", "/requests/%s/decline" % rid, token=tc)
    r2 = call("POST", "/requests/%s/cancel" % rid, token=tb)
    r3 = call("POST", "/requests/%s/decline" % rid, token=tb)
    r4 = call("POST", "/requests/%s/decline" % rid, token=tb)
    r5 = call("POST", "/requests/%s/cancel" % rid, token=ta)
    r6 = call("POST", "/requests/%s/pay" % rid, {}, token=tb, key=k())
    record("S1-120/S1-121/S1-112", "decline/cancel lifecycle",
           (r1[0], r2[0], r3[0], r3[1]["status"], r4[0], r5[0], code(r5[1]), r6[0], code(r6[1])) ==
           (403, 403, 200, "declined", 200, 409, "request_not_pending", 409, "request_not_pending"),
           {"got": [r1[0], r2[0], r3[0], r4[0], r5[0], r6[0]]})
    q = {}
    for qs in ["limit=0", "limit=201", "limit=1e2", "limit=4.0", "limit=%2B4", "offset=-1", "direction=up", "status=open", "status="]:
        s, j, _ = call("GET", "/requests?" + qs, token=ta)
        q[qs] = (s, code(j))
    record("S1-056/S1-057/S1-131", "query validation -> 422", all(v == (422, "validation_failed") for v in q.values()), q)
    s, j, ct = call("GET", "/nope-route", token=ta)
    record("S1-050/S1-017", "unknown route error envelope + json ct", s == 404 and code(j) is not None and "application/json" in (ct or ""), {"s": s, "ct": ct})


def p_id_collision_and_zero_share():
    """R1-01 (proposed S1-021): new ids never collide with seeded ids. R1-02 (proposed S1-145): zero share payable."""
    fx = fixture([("aa", 1000), ("bb", 1000), ("cc", 0)])
    fx["users"][0]["id"], fx["users"][1]["id"], fx["users"][2]["id"] = "u_1", "u_2", "u_3"
    fx["payments"] = [{"id": "p_%d" % i, "from_user_id": "u_1", "to_user_id": "u_2", "amount": 1, "note": "",
                       "visibility": "public"} for i in range(1, 21)]
    fx["requests"] = [{"id": "rq_%d" % i, "requester_id": "u_2", "payer_id": "u_1", "amount": 1, "note": "",
                       "status": "pending"} for i in range(1, 21)]
    reset(fx)
    ta, tb = login("aa"), login("bb")
    new_p = [call("POST", "/payments", {"to_handle": "bb", "amount": 1}, token=ta, key=k())[1]["payment_id"] for _ in range(25)]
    new_r = [call("POST", "/requests", {"payer_handle": "bb", "amount": 1}, token=ta, key=k())[1]["request_id"] for _ in range(25)]
    s, su, _ = call("POST", "/auth/signup", {"email": "newbie@audit.invalid", "password": "longenough1", "display_name": "N"})
    seeded = {"p_%d" % i for i in range(1, 21)} | {"rq_%d" % i for i in range(1, 21)} | {"u_1", "u_2", "u_3"}
    clash = (set(new_p) | set(new_r) | {su.get("user_id")}) & seeded
    feed = call("GET", "/activity?limit=200", token=ta)[1]["payments"]
    record("R1-01/S1-020", "generated ids never collide with seeded ids", not clash and len(set(new_p)) == 25 and len(feed) == 45
           and all(len(x) <= 64 for x in new_p + new_r), {"clash": sorted(clash), "feed": len(feed)})
    s, sp, _ = call("POST", "/splits", {"amount": 1, "participant_handles": ["aa", "bb", "cc"]}, token=ta, key=k())
    zero = [r for r in sp["requests"] if r["payer_handle"] == "cc"][0]
    tc = login("cc")
    s, pj, _ = call("POST", "/requests/%s/pay" % zero["request_id"], {}, token=tc, key=k())
    record("R1-02/S1-143", "zero-share request payable -> payment amount 0", s == 201 and pj.get("amount") == 0 and bal(tc) == 0,
           {"s": s, "c": code(pj)})


def p_export_import(base_b):
    """S1-170..S1-178, S1-202 across two independent containers."""
    fx = fixture([("op", 0), ("aa", 1000), ("bb", 0)], operators=["op"])
    reset(fx)
    ta, to = login("aa"), login("op")
    key = k()
    s, p1, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 10}, token=ta, key=key)
    fk = k()
    call("POST", "/payments", {"to_handle": "bb", "amount": 10 ** 6}, token=ta, key=fk)
    sk = k()
    s, st1, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 5}]}, token=to, key=sk)
    s, ex, _ = call("GET", "/_test/export")
    shape = s == 200 and ex.get("track") == "pocketful" and ex.get("format_version") == 1 and isinstance(ex.get("state"), dict)
    blob = json.dumps(ex)
    record("S1-170/S1-069", "export shape; no plaintext password", shape and "pw-aa-12345" not in blob, {"s": s})
    call("POST", "/payments", {"to_handle": "bb", "amount": 1}, token=ta, key=k())
    s2, ex2, _ = call("GET", "/_test/export")
    record("S1-175", "export snapshot unaffected by later writes", blob != json.dumps(ex2) and json.loads(blob) == ex, {})
    # destination B
    reset(fixture([("zz", 7)]), base=base_b)
    tz = login("zz", base=base_b)
    for bad, exp in [({"track": "x", "format_version": 1, "state": ex["state"]}, 422),
                     ({"track": "pocketful", "format_version": 2, "state": ex["state"]}, 422),
                     ({"track": "pocketful", "format_version": 1}, 422)]:
        s, j, _ = call("POST", "/_test/import", bad, base=base_b)
        still = call("GET", "/me", token=tz, base=base_b)[0]
        record("S1-174", "invalid import rejected, dest unchanged", s == exp and still == 200, {"s": s, "me": still})
    s, j, _ = call("POST", "/_test/import", raw=b"{nope", base=base_b)
    record("S1-174", "invalid JSON import -> 400", s == 400, {"s": s})
    for i in range(2):
        s, _, _ = call("POST", "/_test/import", ex, base=base_b)
    ok = s == 204
    r_old = call("GET", "/me", token=ta, base=base_b)
    r_z = call("GET", "/me", token=tz, base=base_b)
    rp = call("POST", "/payments", {"to_handle": "bb", "amount": 10}, token=ta, key=key, base=base_b)
    rd = call("POST", "/payments", {"to_handle": "bb", "amount": 11}, token=ta, key=key, base=base_b)
    rf = call("POST", "/payments", {"to_handle": "bb", "amount": 3}, token=ta, key=fk, base=base_b)
    rs = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 5}]}, token=to, key=sk, base=base_b)
    lg = call("POST", "/auth/login", {"email": "aa@audit.invalid", "password": "pw-aa-12345"}, base=base_b)
    feed = call("GET", "/activity?limit=200", token=ta, base=base_b)[1]["payments"]
    record("S1-172/S1-176/S1-177/S1-178/S1-202", "A->B import continuity",
           ok and r_old[0] == 200 and r_old[1]["balance"] == 1000 - 15 and r_z[0] == 401 and rp[0] == 200 and rp[1] == p1
           and rd[0] == 409 and rf[0] == 201 and rs[0] == 200 and rs[1] == st1 and lg[0] == 200 and len(feed) == 2,
           {"import": s, "old_tok": r_old[0], "dest_tok": r_z[0], "replay": rp[0], "diff": rd[0], "failed_key": rf[0],
            "settle_replay": rs[0], "login": lg[0], "feed_len": len(feed)})
    reset(fixture([("aa", 1)]), base=base_b)
    record("S1-179", "reset clears imported state", call("GET", "/me", token=ta, base=base_b)[0] == 401, {})


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--base-b")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    BASE = a.base
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    probes = [p_conservation_concurrent, p_pay_at_most_once, p_idem_concurrent_all_paths, p_idem_semantics,
              p_amount_forms, p_splits, p_settlements, p_settlement_concurrency, p_visibility_auth, p_id_collision_and_zero_share]
    for p in probes:
        try:
            p()
        except Exception as e:  # a crashed probe is a failure, never a pass
            record("ERROR", p.__name__, False, {"exception": repr(e)[:300]})
    if a.base_b:
        try:
            p_export_import(a.base_b)
        except Exception as e:
            record("ERROR", "p_export_import", False, {"exception": repr(e)[:300]})
    else:
        record("S1-172", "XC export/import", False, {"reason": "NOT_RUN: no --base-b"})
    fin = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summ = {"started_utc": started, "finished_utc": fin, "passed": sum(r["pass"] for r in RESULTS),
            "failed": sum(not r["pass"] for r in RESULTS), "total": len(RESULTS), "results": RESULTS}
    json.dump(summ, open(a.out, "w"), indent=1, ensure_ascii=False)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Auditor-owned stage-4 probe (fskit-001): refunds and batch corrections, hand-computed expectations.
Keys: S4-010..S4-047, D4-01..D4-11. Stdlib only; synthetic data; no secrets written.
usage: s4_probe.py --base URL --out results.json"""
import argparse, json, os, sys, time, datetime as dt, urllib.parse
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, record, k

T1, T2 = "2026-09-01T10:00:00+00:00", "2026-09-02T10:00:00+00:00"


def fx():
    f = ap.fixture([("op", 0), ("aa", 10000), ("bb", 5000), ("cc", 3000), ("dd", 0)], operators=["op"])
    f["payments"] = [{"id": "p1", "from_user_id": "u_aa", "to_user_id": "u_bb", "amount": 1000, "note": "n1", "visibility": "private", "created_at": T1}]
    f["requests"] = []
    return f


def me(t):
    return call("GET", "/me", token=t)[1]


def refund(t, pid, amt, key=None):
    return call("POST", "/payments/%s/refunds" % pid, {"amount": amt}, token=t, key=key or k())


def batch(t, items, key=None):
    return call("POST", "/correction-batches", {"corrections": items}, token=t, key=key or k())


def item(pid, rev, amt, eff=T2, reason="batch"):
    return {"payment_id": pid, "expected_revision": rev, "amount": amt, "effective_at": eff, "reason": reason}


def total(tk):
    return sum(me(t)["total"] for t in tk.values())


def refunds_probe():
    ap.reset(fx())
    tk = {h: ap.login(h) for h in ("op", "aa", "bb", "cc", "dd")}
    ta, tb, tc = tk["aa"], tk["bb"], tk["cc"]
    TOT = total(tk)
    acc = [refund(ta, "p1", 10)[0], refund(tc, "p1", 10)[0], refund(tk["op"], "p1", 10)[0], refund(tb, "p_none", 10)[0],
           call("POST", "/payments/p1/refunds", {"amount": 10}, key=k())[0], call("POST", "/payments/p1/refunds", {"amount": 10}, token=tb)[0]]
    record("S4-010/S4-011", "sender/third/operator 403, unknown 404, no token 401, no key 400", acc == [403, 403, 403, 404, 401, 400], {"got": acc})
    bad = {r: refund(tb, "p1", json.loads(r))[0] for r in ("0", "-1", "1000000001", "1.5", '"10"', "true")}
    record("S4-013", "invalid refund amounts 422", all(v == 422 for v in bad.values()), bad)
    rk = k()
    s, r1, _ = refund(tb, "p1", 300, key=rk)
    s2, r1b, _ = refund(tb, "p1", 300, key=rk)
    s3, r1c, _ = refund(tb, "p1", 301, key=rk)
    ok = (s == 201 and r1["from_handle"] == "bb" and r1["to_handle"] == "aa" and r1["amount"] == 300 and r1["refund_of"] == "p1" and r1["request_id"] is None
          and r1["authorization_id"] is None and r1.get("settlement_id") is None and r1["note"] == "n1" and r1["visibility"] == "private"
          and s2 == 200 and r1b == r1 and (s3, code(r1c)) == (409, "idempotency_key_reuse"))
    record("S4-015/D4-02/D4-11", "refund shape (reverse direction, refund_of, links null, note/visibility copied); replay 200; key reuse 409", ok,
           {"s": [s, s2, s3], "refund": {x: r1.get(x) for x in ("from_handle", "to_handle", "refund_of", "visibility")}})
    feed_a = {p["payment_id"]: p for p in call("GET", "/activity?limit=200", token=ta)[1]["payments"]}
    feed_c = [p["payment_id"] for p in call("GET", "/activity?limit=200", token=tc)[1]["payments"]]
    record("S4-018/S4-019", "refund in feed by visibility (private: parties only); others refund_of null", r1["payment_id"] in feed_a and r1["payment_id"] not in feed_c
           and feed_a["p1"]["refund_of"] is None, {})
    ex = refund(tb, "p1", 701)
    ok700 = refund(tb, "p1", 700)
    over = refund(tb, "p1", 1)
    record("S4-014", "cumulative refunds limit = current amount (300+700 ok, +1 -> 422)", (ex[0], code(ex[1])) == (422, "refund_exceeds_payment") and ok700[0] == 201
           and (over[0], code(over[1])) == (422, "refund_exceeds_payment"), {"s": [ex[0], ok700[0], over[0]]})
    rr = refund(ta, r1["payment_id"], 1)
    record("S4-012", "refund of a refund -> 422 invalid_refund_target", (rr[0], code(rr[1])) == (422, "invalid_refund_target"), {"s": rr[0], "c": code(rr[1])})
    c_ref = call("POST", "/payments/%s/corrections" % r1["payment_id"], {"expected_revision": 1, "amount": 1, "effective_at": T2, "reason": "x"}, token=tb, key=k())
    revs = call("GET", "/payments/%s/revisions" % r1["payment_id"], token=tb)[1]["revisions"]
    record("S4-020/E3", "refund payment not correctable (422 linked_payment_immutable); revisions has rev 1 only",
           (c_ref[0], code(c_ref[1])) == (422, "linked_payment_immutable") and len(revs) == 1 and revs[0].get("correction_batch_id", "MISSING") is None, {"s": c_ref[0]})
    # correction floor at refunded amount: new payment aa->cc 500, cc refunds 200, aa corrects 500 -> 199 (422), 200 ok
    s, p2, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 500}, token=ta, key=k())
    refund(tc, p2["payment_id"], 200)
    c1 = call("POST", "/payments/%s/corrections" % p2["payment_id"], {"expected_revision": 1, "amount": 199, "effective_at": p2["created_at"], "reason": "x"}, token=ta, key=k())
    c2 = call("POST", "/payments/%s/corrections" % p2["payment_id"], {"expected_revision": 1, "amount": 200, "effective_at": p2["created_at"], "reason": "x"}, token=ta, key=k())
    record("S4-021", "correction below refunded total -> 422 refund_exceeds_payment; exactly equal OK", (c1[0], code(c1[1])) == (422, "refund_exceeds_payment") and c2[0] == 201,
           {"s": [c1[0], c2[0]]})
    r_after = refund(tc, p2["payment_id"], 1)
    record("S4-014/D4-03", "refund limit follows current corrected amount (200 refunded of 200 -> +1 422)", (r_after[0], code(r_after[1])) == (422, "refund_exceeds_payment"), {"s": r_after[0]})
    # available funds: dd gets 400, authorizes 300 (available 100), refund of 200 -> 409
    s, p3, _ = call("POST", "/payments", {"to_handle": "dd", "amount": 400}, token=ta, key=k())
    s, h, _ = call("POST", "/authorizations", {"to_handle": "aa", "amount": 300}, token=tk["dd"], key=k())
    rf = refund(tk["dd"], p3["payment_id"], 200)
    rf_ok = refund(tk["dd"], p3["payment_id"], 100)
    record("S4-016", "refund checks available (held funds can't pay) -> 409; within available 201", (rf[0], code(rf[1])) == (409, "insufficient_funds") and rf_ok[0] == 201,
           {"s": [rf[0], rf_ok[0]], "dd": me(tk["dd"])})
    # capture refund does not reopen hold; request payment refund does not reopen request
    s, cp, _ = call("POST", "/authorizations/%s/capture" % h["authorization_id"], {"amount": 50}, token=ta, key=k())
    rcap = refund(ta, cp["payment_id"], 50)
    au = [x for x in call("GET", "/authorizations", token=ta)[1]["authorizations"] if x["authorization_id"] == h["authorization_id"]][0]
    s, rq, _ = call("POST", "/requests", {"payer_handle": "aa", "amount": 40}, token=tc, key=k())
    s, pay, _ = call("POST", "/requests/%s/pay" % rq["request_id"], {}, token=ta, key=k())
    rreq = refund(tc, pay["payment_id"], 40)
    rq_now = [r for r in call("GET", "/requests?limit=200", token=tc)[1]["requests"] if r["request_id"] == rq["request_id"]][0]
    record("S4-012/S4-017/D4-09", "refund of capture and of request payment: 201; hold stays closed, request stays paid", rcap[0] == 201 and au["status"] == "captured"
           and au["captured_amount"] == 50 and au["remaining_amount"] == 0 and rreq[0] == 201 and rq_now["status"] == "paid", {"s": [rcap[0], rreq[0]], "auth": au["status"]})
    # concurrent refunds of one payment
    s, p4, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 1000}, token=ta, key=k())
    with ThreadPoolExecutor(20) as ex:
        rs = list(ex.map(lambda i: refund(tc, p4["payment_id"], 150), range(20)))
    n = [r[0] for r in rs].count(201)
    s, p5, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 500}, token=ta, key=k())
    key = k()
    with ThreadPoolExecutor(15) as ex:
        rs2 = list(ex.map(lambda i: refund(tc, p5["payment_id"], 10, key=key), range(15)))
    st2 = [r[0] for r in rs2]
    same = len({json.dumps(r[1], sort_keys=True) for r in rs2}) == 1
    refunded = sum(1 for p in call("GET", "/activity?limit=200", token=tc)[1]["payments"] if p.get("refund_of") == p5["payment_id"])
    record("S4-023/S4-024", "20 concurrent refunds of 150 on 1000 -> exactly 6; same-key x15 -> one 201 + 14x200 identical, effect once",
           n == 6 and all(r[0] in (201, 422) for r in rs) and st2.count(201) == 1 and st2.count(200) == 14 and same and refunded == 1 and total(tk) == TOT,
           {"ok": n, "same_key": {x: st2.count(x) for x in set(st2)}, "identical": same, "refunds_made": refunded})
    # history: refund counts at its own created_at
    hist = call("GET", "/me?as_of=%s" % urllib.parse.quote(r1["created_at"], safe=""), token=tb)[1]["balance"]
    before = call("GET", "/me?as_of=%s" % urllib.parse.quote((dt.datetime.fromisoformat(r1["created_at"]) - dt.timedelta(milliseconds=1)).isoformat(timespec="milliseconds"), safe=""),
                  token=tb)[1]["balance"]
    record("S4-019/E2", "refund applies in history at its created_at", before - hist == 300, {"before": before, "at": hist})


def batch_probe():
    ap.reset(fx())
    tk = {h: ap.login(h) for h in ("op", "aa", "bb", "cc", "dd")}
    to, ta, tb, tc = tk["op"], tk["aa"], tk["bb"], tk["cc"]
    TOT = total(tk)
    s, st1, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 100},
                                                           {"from_handle": "bb", "to_handle": "cc", "amount": 50}]}, token=to, key=(sk := k()))
    st1_raw = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 100},
                                                         {"from_handle": "bb", "to_handle": "cc", "amount": 50}]}, token=to, key=sk)[1]
    m1, m2 = st1["payments"][0]["payment_id"], st1["payments"][1]["payment_id"]
    s, st2, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "cc", "to_handle": "aa", "amount": 30}]}, token=to, key=k())
    m3 = st2["payments"][0]["payment_id"]
    s, pd, _ = call("POST", "/payments", {"to_handle": "cc", "amount": 70}, token=ta, key=k())
    eff = st1["committed_at"]
    acc = [batch(ta, [item(pd["payment_id"], 1, 60, pd["created_at"])])[0], call("POST", "/correction-batches", {"corrections": [item("p1", 1, 900, T1)]}, key=k())[0],
           call("POST", "/correction-batches", {"corrections": [item("p1", 1, 900, T1)]}, token=to)[0]]
    record("S4-030", "non-operator 403, no token 401, no key 400", acc == [403, 401, 400], {"got": acc})
    shape = [batch(to, [])[0], batch(to, [item("p1", 1, 900, T1)] * 2)[0], batch(to, [item("p%d" % i, 1, 1, T1) for i in range(33)])[0],
             call("POST", "/correction-batches", {"corrections": "x"}, token=to, key=k())[0], batch(to, [dict(item("p1", 1, 900, T1), amount=-1)])[0],
             batch(to, [item("p1", 1, 900, "2099-01-01T00:00:00+00:00")])[0]]
    record("S4-031/S4-041", "0 items / duplicate / 33 / not array / bad field / future effective -> 422", shape == [422] * 6, {"got": shape})
    inc = batch(to, [item(m1, 1, 0, eff)])
    record("S4-034", "partial settlement -> 422 incomplete_settlement", (inc[0], code(inc[1])) == (422, "incomplete_settlement"), {"s": inc[0], "c": code(inc[1])})
    shifted = (dt.datetime.fromisoformat(eff) + dt.timedelta(hours=2)).isoformat(timespec="milliseconds").replace("+00:00", "+02:00") \
        if False else (dt.datetime.fromisoformat(eff).astimezone(dt.timezone(dt.timedelta(hours=2)))).isoformat(timespec="milliseconds")
    diff = batch(to, [item(m1, 1, 0, eff), item(m2, 1, 0, T1)])
    record("S4-035", "members with different effective instants -> 422", (diff[0], code(diff[1])) == (422, "validation_failed"), {"s": diff[0]})
    prec1 = batch(to, [item("p1", 9, 900, T1), item("p_unknown", 1, 1, T1)])
    prec2 = batch(to, [item("p_unknown", 1, 1, T1), item("p1", 9, 900, T1)])
    record("S4-037/D4-06", "item errors in input order (stale then unknown -> 409; reverse -> 404)", (prec1[0], code(prec1[1]), prec2[0]) == (409, "stale_revision", 404),
           {"got": [prec1[0], code(prec1[1]), prec2[0]]})
    before = {h: me(t)["total"] for h, t in tk.items()}
    rev_before = call("GET", "/payments/p1/revisions", token=ta)[1]
    bk = k()
    over = batch(to, [item("p1", 1, 50000, T1)], key=bk)
    after = {h: me(t)["total"] for h, t in tk.items()}
    record("S4-037/S4-039", "unaffordable batch -> 409 insufficient_funds; nothing changes; key unclaimed", (over[0], code(over[1])) == (409, "insufficient_funds")
           and before == after and call("GET", "/payments/p1/revisions", token=ta)[1] == rev_before, {"s": over[0], "c": code(over[1])})
    # combined affordability: cc has 3000+50-30+70 = 3090; reverse m2 (bb->cc 50 -> 0 debits cc 50) and increase pd (aa->cc 70 -> 3160 credits cc)
    # simpler: dd has 0; pay dd 500 (aa->dd); batch: correct that to 0 (debit dd 500) and correct p_x (dd receives) ... use two payments to dd
    s, q1, _ = call("POST", "/payments", {"to_handle": "dd", "amount": 500}, token=ta, key=k())
    s, q2, _ = call("POST", "/payments", {"to_handle": "dd", "amount": 100}, token=tb, key=k())
    call("POST", "/payments", {"to_handle": "cc", "amount": 600}, token=tk["dd"], key=k())      # dd spends all 600 -> 0
    alone = call("POST", "/payments/%s/corrections" % q1["payment_id"], {"expected_revision": 1, "amount": 400, "effective_at": q1["created_at"], "reason": "x"},
                 token=ta, key=k())
    comb = batch(to, [item(q1["payment_id"], 1, 400, q1["created_at"]), item(q2["payment_id"], 1, 200, q2["created_at"])], key=bk)
    record("S4-038", "one correction alone unaffordable (409), combined batch affordable (201, reuses unclaimed key)", (alone[0], code(alone[1])) == (409, "insufficient_funds")
           and comb[0] == 201, {"alone": alone[0], "batch": comb[0], "c": code(comb[1])})
    # complete settlement batch reversal + response shape + receipts unchanged + snapshot frozen
    s, snap0, _ = call("GET", "/statement?limit=200", token=tb)
    ck = k()
    body = [item(m1, 1, 0, eff, "reversal"), item(m2, 1, 0, eff.replace("+00:00", "+00:00"), "reversal"), item(pd["payment_id"], 1, 60, pd["created_at"])]
    s, br, _ = batch(to, body, key=ck)
    revs = br.get("revisions", []) if isinstance(br, dict) else []
    prev_rec = max(st1["committed_at"], pd["created_at"])
    ok = (s == 201 and br.get("correction_batch_id") and [r["payment_id"] for r in revs] == [m1, m2, pd["payment_id"]] and len({r["recorded_at"] for r in revs}) == 1
          and revs[0]["recorded_at"] == br["recorded_at"] and br["recorded_at"] > prev_rec and all(r.get("correction_batch_id") == br["correction_batch_id"] for r in revs))
    record("S4-040/S4-033/D4-10", "complete settlement + non-member batch: 201 shape, input order, one shared recorded_at, correction_batch_id", ok,
           {"s": s, "batch": {x: br.get(x) for x in ("correction_batch_id", "recorded_at")} if isinstance(br, dict) else br})
    rp = call("POST", "/correction-batches", {"corrections": body}, token=to, key=ck)
    rd = call("POST", "/correction-batches", {"corrections": body[:2]}, token=to, key=ck)
    st_rep = call("POST", "/settlements", {"transfers": [{"from_handle": "aa", "to_handle": "bb", "amount": 100},
                                                        {"from_handle": "bb", "to_handle": "cc", "amount": 50}]}, token=to, key=sk)[1]
    record("S4-044/S4-042", "batch replay 200 identical; different body 409; settlement receipt retry unchanged", rp[0] == 200 and rp[1] == br and (rd[0], code(rd[1])) == (409, "idempotency_key_reuse")
           and st_rep == st1_raw, {"s": [rp[0], rd[0]]})
    rv = call("GET", "/payments/%s/revisions" % m1, token=ta)[1]["revisions"]
    record("S4-040/D4-05", "revisions show batch revision with correction_batch_id; rev1 null", rv[0].get("correction_batch_id", "MISSING") is None
           and rv[-1].get("correction_batch_id") == br.get("correction_batch_id") and rv[-1]["amount"] == 0, {"revs": len(rv)})
    s, snap1, _ = call("GET", "/statement?snapshot=%s&limit=200" % snap0["snapshot"], token=tb)
    s2, new, _ = call("GET", "/statement?limit=200", token=tb)
    ent = [e for e in new["entries"] if e["payment"]["payment_id"] == m1]
    record("S4-043", "old snapshot frozen; new statement shows batch revision (amount 0)", snap1["entries"] == snap0["entries"] and ent and ent[0]["payment"]["amount"] == 0
           and ent[0]["delta"] == 0, {})
    single = call("POST", "/payments/%s/corrections" % m3, {"expected_revision": 1, "amount": 1, "effective_at": st2["committed_at"], "reason": "x"}, token=tk["cc"], key=k())
    record("S4-036", "single correction of settlement member still 422 linked_payment_immutable", (single[0], code(single[1])) == (422, "linked_payment_immutable"), {"s": single[0]})
    mref = refund(tb, m1 if False else st2["payments"][0]["payment_id"], 10) if False else refund(tk["aa"], m3, 10)
    m3v = [p for p in call("GET", "/activity?limit=200", token=tk["aa"])[1]["payments"] if p["payment_id"] == m3][0]
    record("S4-045", "settlement member refundable; refund has settlement_id null; member keeps settlement_id", mref[0] == 201 and mref[1].get("settlement_id") is None
           and m3v["settlement_id"] == st2["settlement_id"], {"s": mref[0]})
    # concurrency: batch vs single sharing a revision
    s, z, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 10}, token=ta, key=k())
    jobs = [lambda: batch(to, [item(z["payment_id"], 1, 9, z["created_at"])]) for _ in range(6)]
    jobs += [lambda: call("POST", "/payments/%s/corrections" % z["payment_id"], {"expected_revision": 1, "amount": 8, "effective_at": z["created_at"], "reason": "s"},
                          token=ta, key=k()) for _ in range(6)]
    with ThreadPoolExecutor(12) as ex:
        rs = list(ex.map(lambda f: f(), jobs))
    ok_n = [r[0] for r in rs].count(201)
    record("S4-046", "12 concurrent batch/single corrections on one revision -> exactly one 201, rest 409 stale", ok_n == 1 and all(r[0] in (201, 409) for r in rs),
           {"outcomes": sorted(set(str((r[0], code(r[1]))) for r in rs))})
    # S4-024: 15 concurrent same-key batches
    s, y, _ = call("POST", "/payments", {"to_handle": "bb", "amount": 20}, token=ta, key=k())
    bk2 = k()
    with ThreadPoolExecutor(15) as ex:
        rsb = list(ex.map(lambda i: batch(to, [item(y["payment_id"], 1, 15, y["created_at"])], key=bk2), range(15)))
    stb = [r[0] for r in rsb]
    nrev = len(call("GET", "/payments/%s/revisions" % y["payment_id"], token=ta)[1]["revisions"])
    record("S4-024", "15 concurrent same-key batches -> one 201 + 14x200 identical; one revision appended",
           stb.count(201) == 1 and stb.count(200) == 14 and len({json.dumps(r[1], sort_keys=True) for r in rsb}) == 1 and nrev == 2, {"st": {x: stb.count(x) for x in set(stb)}, "revs": nrev})
    grid = [total_view for total_view in [sum(call("GET", "/me?as_of=%s" % urllib.parse.quote(a, safe=""), token=t)[1]["total"] for t in tk.values())
                                          for a in (T1, T2, eff, "2099-01-01T00:00:00+00:00")]]
    record("S4-047", "conservation in historical views after batches", all(g == TOT for g in grid) and total(tk) == TOT, {"grid": grid, "TOT": TOT})


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--base", required=True)
    a.add_argument("--out", required=True)
    x = a.parse_args()
    ap.BASE = x.base
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for f in (refunds_probe, batch_probe):
        try:
            f()
        except Exception as e:
            import traceback
            record("ERROR", f.__name__, False, {"exception": repr(e)[:300], "at": traceback.format_exc().splitlines()[-3][:200]})
    R = ap.RESULTS
    summ = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(r["pass"] for r in R), "failed": sum(not r["pass"] for r in R), "total": len(R), "results": R}
    json.dump(summ, open(x.out, "w"), indent=1, ensure_ascii=False)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

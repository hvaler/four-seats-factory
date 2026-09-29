#!/usr/bin/env python3
"""Auditor-owned stage-3 probe (fskit-001) with HAND-COMPUTED expected values.
Keys: S3-010..S3-085, D3-01..D3-16. Stdlib only; synthetic data; no secrets written.

Seeded history (fixture balances are AFTER these payments):
  T1 p1 aa->bb 1000 public     T2 p2 bb->aa 300 public     T2 p4 aa->dd 700 public
  T3 p3 cc->aa 500 private     T3 p5 dd->cc 600 public
  final: aa 10000, bb 5000, cc 2000, dd 100, ee 0, ff 5000, op 0      total 22100
  opening = final - net(seeded):
    aa 10000 - (-1000 +300 +500 -700) = 10900     bb 5000 - (1000 -300) = 4300
    cc 2000 - (-500 +600) = 1900                  dd 100 - (700 -600) = 0     ee 0, ff 5000, op 0
usage: s3_probe.py --base URL --out results.json
"""
import argparse, json, sys, os, time, datetime as dt, urllib.parse
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, record, k

T1, T2, T3 = "2026-09-01T10:00:00+00:00", "2026-09-02T10:00:00+00:00", "2026-09-03T10:00:00+00:00"
TOTAL = 22100


def q(v):
    return urllib.parse.quote(v, safe="")


def iso_shift(s, ms):
    d = dt.datetime.fromisoformat(s.replace("Z", "+00:00")) + dt.timedelta(milliseconds=ms)
    return d.isoformat(timespec="milliseconds")


def fixture():
    f = ap.fixture([("aa", 10000), ("bb", 5000), ("cc", 2000), ("dd", 100), ("ee", 0), ("ff", 5000), ("op", 0)], operators=["op"])
    P = lambda i, a, b, amt, t, vis="public": {"id": i, "from_user_id": "u_" + a, "to_user_id": "u_" + b, "amount": amt, "note": i,
                                              "visibility": vis, "created_at": t}
    f["payments"] = [P("p1", "aa", "bb", 1000, T1), P("p2", "bb", "aa", 300, T2), P("p4", "aa", "dd", 700, T2),
                     P("p3", "cc", "aa", 500, T3, "private"), P("p5", "dd", "cc", 600, T3)]
    f["requests"] = []
    return f


def me(t, **qs):
    s = "&".join("%s=%s" % (a, q(b)) for a, b in qs.items())
    return call("GET", "/me" + ("?" + s if s else ""), token=t)


def stmt(t, **qs):
    s = "&".join("%s=%s" % (a, q(str(b))) for a, b in qs.items())
    return call("GET", "/statement" + ("?" + s if s else ""), token=t)


def correct(t, pid, rev, amount, eff, reason="fix", key=None):
    return call("POST", "/payments/%s/corrections" % pid, {"expected_revision": rev, "amount": amount, "effective_at": eff, "reason": reason},
                token=t, key=key or k())


def total_view(toks, **qs):
    return sum(me(t, **qs)[1]["balance"] for t in toks.values())


def main_probe():
    ap.reset(fixture())
    tk = {h: ap.login(h) for h in ("aa", "bb", "cc", "dd", "ee", "ff", "op")}
    ta, tb, tc, td = tk["aa"], tk["bb"], tk["cc"], tk["dd"]
    # ---- timestamps + as_of
    feed = {p["payment_id"]: p for p in call("GET", "/activity?limit=200", token=ta)[1]["payments"]}
    record("S3-010/S3-011/S3-012", "seeded created_at verbatim, fixture balance unchanged",
           feed["p1"]["created_at"] == T1 and feed["p3"]["created_at"] == T3 and me(ta)[1]["balance"] == 10000, {"p1": feed["p1"]["created_at"]})
    cases = {"before T1": (iso_shift(T1, -1), 10900), "at T1 (inclusive)": (T1, 9900), "T1 as +02:00": ("2026-09-01T12:00:00+02:00", 9900),
             "at T2": (T2, 9500), "at T3": (T3, 10000), "far future": ("2030-01-01T00:00:00+00:00", 10000)}
    got = {}
    for n, (a, exp) in cases.items():
        s, j, _ = me(ta, as_of=a)
        got[n] = (s, j.get("balance"), j.get("as_of") == a, exp)
    record("S3-021/S3-022", "as_of inclusive, opening before earliest, echo exact", all(v[0] == 200 and v[1] == v[3] and v[2] for v in got.values()), got)
    bad = {v: me(ta, as_of=v)[0] for v in ("2026-09-01T10:00:00", "2026-09-01", "", "yesterday")}
    record("S3-020", "invalid as_of -> 422", all(v == 422 for v in bad.values()), bad)
    # ---- statements
    s, st, _ = stmt(ta, **{"from": T1, "to": T3})
    ids = [(e["payment"]["payment_id"], e["delta"], e["balance_after"]) for e in st.get("entries", [])]
    exp_ids = [("p1", -1000, 9900), ("p2", 300, 10200), ("p4", -700, 9500)]
    record("S3-031/S3-032/S3-033/S3-034", "window [T1,T3): opening, entries (time then id), closing; T3 excluded",
           s == 200 and st["opening_balance"] == 10900 and ids == exp_ids and st["closing_balance"] == 9500 and st.get("snapshot"),
           {"s": s, "opening": st.get("opening_balance"), "entries": ids, "closing": st.get("closing_balance")})
    s, pg, _ = stmt(ta, **{"from": T1, "to": T3, "limit": 1, "offset": 1})
    s2, pg2, _ = stmt(ta, **{"from": T1, "to": T3, "limit": 2, "offset": 2})
    record("S3-035/S3-064", "pagination invariant; has_more", [(e["payment"]["payment_id"], e["balance_after"]) for e in pg["entries"]] == [("p2", 10200)]
           and pg["opening_balance"] == 10900 and pg["closing_balance"] == 9500 and pg["has_more"] is True
           and [e["payment"]["payment_id"] for e in pg2["entries"]] == ["p4"] and pg2["has_more"] is False, {})
    s, stb, _ = stmt(tb)
    sb = [e["payment"]["payment_id"] for e in stb["entries"]]
    s, stc, _ = stmt(tc)
    sc = [e["payment"]["payment_id"] for e in stc["entries"]]
    record("S3-036", "statement only own payments (private included, others' public excluded)", sb == ["p1", "p2"] and sc == ["p3", "p5"], {"bb": sb, "cc": sc})
    bad = {v: stmt(ta, **{"from": v})[0] for v in ("2026-09-01", "")}
    bad["to naive"] = stmt(ta, **{"to": "2026-09-01T10:00:00"})[0]
    bad["from>to"] = stmt(ta, **{"from": T3, "to": T1})[0]
    bad["limit 0"] = stmt(ta, limit=0)[0]
    record("S3-030/D3-08/C2", "statement invalid instants / from>to / limit -> 422", all(v == 422 for v in bad.values()), bad)
    # ---- revisions
    s, rv, _ = call("GET", "/payments/p1/revisions", token=ta)
    r1 = (rv or {}).get("revisions", [{}])[0]
    s2, _, _ = call("GET", "/payments/p1/revisions", token=tc)
    s3, _, _ = call("GET", "/payments/p1/revisions")
    record("S3-040/S3-052", "revision 1 shape; third party 404; no token 401", s == 200 and r1.get("revision") == 1 and r1.get("amount") == 1000
           and r1.get("effective_at") == T1 and r1.get("recorded_at") == T1 and r1.get("reason") == "" and (s2, s3) == (404, 401), {"r1": r1, "s": [s, s2, s3]})
    # ---- corrections
    before_corr = call("GET", "/me", token=ta)[1]
    kb = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 2))
    ck = k()
    s, c1, _ = correct(ta, "p1", 1, 800, T1, key=ck)
    m_aa, m_bb = me(ta)[1]["balance"], me(tb)[1]["balance"]
    record("S3-044/S3-048", "decrease 1000->800 moves 200 back from receiver; 201 shape", s == 201 and c1.get("revision") == 2 and c1.get("amount") == 800
           and c1.get("effective_at") == T1 and c1.get("reason") == "fix" and c1.get("recorded_at") and c1.get("payment_id") == "p1" and (m_aa, m_bb) == (10200, 4800),
           {"s": s, "body": c1, "aa": m_aa, "bb": m_bb})
    hist = me(ta, as_of=T1)[1]["balance"]
    hist_k = me(ta, as_of=T1, known_at=kb)[1]
    record("S3-053/D3-07", "as_of T1 after correction 10100; with known_at before correction 9900 (echoed)", hist == 10100 and hist_k["balance"] == 9900 and hist_k.get("known_at") == kb,
           {"now_view": hist, "known_view": hist_k.get("balance")})
    s, st, _ = stmt(ta)
    e1 = [e for e in st["entries"] if e["payment"]["payment_id"] == "p1"][0]
    s, stk, _ = stmt(ta, known_at=kb)
    e1k = [e for e in stk["entries"] if e["payment"]["payment_id"] == "p1"][0]
    record("S3-054/D3-12", "statement uses selected revision; known_at selects older", e1["revision"] == 2 and e1["payment"]["amount"] == 800 and e1["delta"] == -800
           and e1["effective_at"] == T1 and st["closing_balance"] == 10200 and e1k["revision"] == 1 and e1k["delta"] == -1000 and stk["closing_balance"] == 10000,
           {"now": [e1["revision"], e1["delta"]], "known": [e1k["revision"], e1k["delta"]]})
    act = [p for p in call("GET", "/activity?limit=200", token=ta)[1]["payments"] if p["payment_id"] == "p1"][0]
    nfeed = len(call("GET", "/activity?limit=200", token=ta)[1]["payments"])
    record("S3-051/D3-06", "activity shows original amount; no new feed items", act["amount"] == 1000 and nfeed == 5, {"amount": act["amount"], "feed": nfeed})
    views = {}
    for a in (iso_shift(T1, -1), T1, T2, T3, "2030-01-01T00:00:00+00:00"):
        views[a] = (total_view(tk, as_of=a), total_view(tk, as_of=a, known_at=kb))
    record("S3-050/D3-14", "conservation in every historical view", all(v == (TOTAL, TOTAL) for v in views.values()), views)
    r_st = correct(ta, "p1", 1, 700, T1)
    r_rp = correct(ta, "p1", 1, 800, T1, key=ck)
    r_df = correct(ta, "p1", 1, 801, T1, key=ck)
    record("S3-046/S3-047", "stale 409; replay 200 original; different body 409", (r_st[0], code(r_st[1])) == (409, "stale_revision") and r_rp[0] == 200 and r_rp[1] == c1
           and (r_df[0], code(r_df[1])) == (409, "idempotency_key_reuse"), {"s": [r_st[0], r_rp[0], r_df[0]]})
    auth = [correct(tb, "p1", 2, 1, T1)[0], correct(tc, "p1", 2, 1, T1)[0], correct(ta, "p_none", 1, 1, T1)[0],
            call("POST", "/payments/p1/corrections", {"expected_revision": 2, "amount": 1, "effective_at": T1, "reason": "x"}, key=k())[0],
            call("POST", "/payments/p1/corrections", {"expected_revision": 2, "amount": 1, "effective_at": T1, "reason": "x"}, token=ta)[0]]
    record("S3-042", "receiver 403, third 403, unknown 404, no token 401, no key 400", auth == [403, 403, 404, 401, 400], {"got": auth})
    inval = {}
    for n, body in {"amount -1": {"amount": -1}, "amount 1e9+1": {"amount": 1000000001}, "reason empty": {"reason": ""}, "reason 201": {"reason": "r" * 201},
                    "future eff": {"effective_at": "2030-01-01T00:00:00+00:00"}, "no offset": {"effective_at": "2026-09-01T10:00:00"},
                    "rev 0": {"expected_revision": 0}, "rev string": {"expected_revision": "2"}, "reason number": {"reason": 5}}.items():
        b = dict({"expected_revision": 2, "amount": 800, "effective_at": T1, "reason": "x"}, **body)
        s, j, _ = call("POST", "/payments/p1/corrections", b, token=ta, key=k())
        inval[n] = (s, code(j))
    for fld in ("expected_revision", "amount", "effective_at", "reason"):
        b = {"expected_revision": 2, "amount": 800, "effective_at": T1, "reason": "x"}
        b.pop(fld)
        s, j, _ = call("POST", "/payments/p1/corrections", b, token=ta, key=k())
        inval["missing " + fld] = (s, code(j))
    record("S3-043/D3-02", "invalid correction fields -> 422", all(v == (422, "validation_failed") for v in inval.values()), inval)
    s, j, _ = correct(tb, "p2", 1, 300 + 4801, T2)
    record("S3-049", "currently unaffordable increase -> 409 insufficient_funds", (s, code(j)) == (409, "insufficient_funds"), {"s": s, "c": code(j)})
    # historical overdraft: dd opened at 0, got 700 at T2, paid 600 at T3. Fund dd now so a decrease is affordable today.
    call("POST", "/payments", {"to_handle": "dd", "amount": 1000}, token=tk["ff"], key=k())
    revs_before = call("GET", "/payments/p4/revisions", token=ta)[1]
    hk = k()
    s, j, _ = correct(ta, "p4", 1, 550, T2, key=hk)
    revs_after = call("GET", "/payments/p4/revisions", token=ta)[1]
    dd_after_reject = me(td)[1]["balance"]          # read BEFORE the successful retry (which legitimately moves 50)
    s2, j2, _ = correct(ta, "p4", 1, 650, T2, key=hk)
    record("S3-049/D3-11", "backdated decrease making dd negative at T3 -> 409 historical_overdraft; nothing changes; key reusable",
           (s, code(j)) == (409, "historical_overdraft") and revs_before == revs_after and dd_after_reject == 1100 and s2 == 201,
           {"s": s, "c": code(j), "revs_unchanged": revs_before == revs_after, "dd_after_reject": dd_after_reject, "retry_ok": s2})
    s, j, _ = correct(ta, "p4", 2, 650, T2)
    record("D3-03", "same-amount correction appends revision (201)", s == 201 and j.get("revision") == 3, {"s": s})
    s, z, _ = correct(tk["ff"], [p for p in call("GET", "/activity?limit=200", token=tk["ff"])[1]["payments"] if p["to_handle"] == "dd"][0]["payment_id"], 1, 0,
                      iso_shift(time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), -500))
    record("S3-043/S3-054", "zero-amount reversal allowed when affordable", s in (201, 409), {"s": s, "c": code(z), "note": "201 expected unless dd's later history makes it an overdraft"})
    # ---- linked immutable
    s, stl, _ = call("POST", "/settlements", {"transfers": [{"from_handle": "ff", "to_handle": "ee", "amount": 10}]}, token=tk["op"], key=k())
    mid = stl["payments"][0]["payment_id"]
    s1_, j1_, _ = correct(tk["ff"], mid, 1, 5, T1)
    s, a, _ = call("POST", "/authorizations", {"to_handle": "ee", "amount": 20}, token=tk["ff"], key=k())
    s, cp, _ = call("POST", "/authorizations/%s/capture" % a["authorization_id"], {}, token=tk["ee"], key=k())
    s2_, j2_, _ = correct(tk["ff"], cp["payment_id"], 1, 5, T1)
    s, rs, _ = call("GET", "/payments/%s/revisions" % mid, token=tk["ff"])
    record("S3-070/S3-071/D3-05", "settlement member and capture -> 422 linked_payment_immutable; member rev1 at committed_at",
           (s1_, code(j1_), s2_, code(j2_)) == (422, "linked_payment_immutable", 422, "linked_payment_immutable")
           and rs["revisions"][0]["effective_at"] == stl["committed_at"] == rs["revisions"][0]["recorded_at"], {"got": [s1_, code(j1_), s2_, code(j2_)]})
    s, ste, _ = stmt(tk["ee"])
    capent = [e for e in ste["entries"] if e["payment"]["payment_id"] == cp["payment_id"]]
    record("S3-084/C6", "capture appears exactly once in statement with authorization link; no authorization entries",
           len(capent) == 1 and capent[0]["payment"].get("authorization_id") == a["authorization_id"] and len(ste["entries"]) == 2, {"entries": len(ste["entries"])})
    # ---- snapshots
    s, s0, _ = stmt(ta, limit=2)
    tok = s0["snapshot"]
    call("POST", "/payments", {"to_handle": "bb", "amount": 5}, token=ta, key=k())
    correct(ta, "p1", 2, 900, T1)
    s, sp, _ = stmt(ta, snapshot=tok, limit=2, offset=0)
    s_, sp2, _ = stmt(ta, snapshot=tok, limit=2, offset=2)
    s_all, full, _ = stmt(ta, snapshot=tok, limit=200)
    ok = (sp["entries"] == s0["entries"] and sp["opening_balance"] == s0["opening_balance"] and sp["closing_balance"] == s0["closing_balance"]
          and sp["has_more"] == s0["has_more"] and len(full["entries"]) == 4 and full["closing_balance"] == s0["closing_balance"])  # aa: p1 p2 p4 p3
    record("S3-060/S3-061/S3-064", "snapshot frozen across payment + correction", ok, {"first_page_same": sp["entries"] == s0["entries"], "full": len(full["entries"])})
    e422 = [stmt(ta, snapshot=tok, **{"from": T1})[0], stmt(ta, snapshot=tok, to=T3)[0], stmt(ta, snapshot=tok, known_at=T3)[0]]
    e404 = [stmt(tb, snapshot=tok)[0], stmt(ta, snapshot="nope-token")[0]]
    ign = stmt(ta, snapshot=tok, foo="bar")[0]
    record("S3-062/S3-063/D3-09", "snapshot + from/to/known_at 422; other user / unknown 404; unknown param ignored", e422 == [422] * 3 and e404 == [404] * 2 and ign == 200,
           {"422": e422, "404": e404, "ignored": ign})
    # ---- concurrent same-revision corrections
    revn = call("GET", "/payments/p2/revisions", token=tb)[1]["revisions"][-1]["revision"]
    with ThreadPoolExecutor(12) as ex:
        rs = list(ex.map(lambda i: correct(tb, "p2", revn, 250 + i, T2), range(12)))
    st_ = sorted(str((r[0], code(r[1]))) for r in rs)
    revs = call("GET", "/payments/p2/revisions", token=tb)[1]["revisions"]
    rec_times = [r["recorded_at"] for r in revs]
    record("S3-065/S3-045", "12 concurrent same-revision corrections: exactly one 201, rest stale; recorded_at strictly increasing",
           [r[0] for r in rs].count(201) == 1 and all(r[0] in (201, 409) for r in rs) and rec_times == sorted(set(rec_times)) and total_view(tk) == TOTAL,
           {"outcomes": sorted(set(st_)), "revisions": len(revs)})
    ap.reset(fixture())
    record("S3-063", "snapshot from before reset -> 404", stmt(ap.login("aa"), snapshot=tok)[0] == 404, {})


def holds_probe():
    f = ap.fixture([("aa", 5000), ("bb", 0)])
    f["authorization_ttl_seconds"] = 2
    ap.reset(f)
    ta, tb = ap.login("aa"), ap.login("bb")
    s, a, _ = call("POST", "/authorizations", {"to_handle": "bb", "amount": 1000}, token=ta, key=k())
    c0 = a["created_at"]
    s, cp, _ = call("POST", "/authorizations/%s/capture" % a["authorization_id"], {"amount": 300, "final": False}, token=tb, key=k())
    ct = cp["created_at"]
    time.sleep(2.6)
    lst = {x["authorization_id"]: x for x in call("GET", "/authorizations", token=ta)[1]["authorizations"]}
    ex = lst[a["authorization_id"]]
    v = lambda at, **kw: me(ta, as_of=at, **kw)[1]
    pts = {"before create": v(iso_shift(c0, -1)), "at create": v(c0), "at capture": v(ct), "at expiry": v(ex["expires_at"]), "now": me(ta)[1]}
    exp = {"before create": (5000, 5000, 0), "at create": (5000, 4000, 1000), "at capture": (4700, 4000, 700), "at expiry": (4700, 4700, 0), "now": (4700, 4700, 0)}
    got = {n: (m["total"], m["available"], m["held"]) for n, m in pts.items()}
    ok4 = all(m["balance"] == m["total"] for m in pts.values())
    record("S3-080/S3-082/S3-023", "historical holds: create, non-final capture, expiry at expires_at; closed_at = expires_at; four fields one view",
           got == exp and ok4 and ex["status"] == "expired" and ex["closed_at"] == ex["expires_at"], {"got": got, "closed_at": ex.get("closed_at"), "expires": ex.get("expires_at")})
    f = ap.fixture([("aa", 5000), ("bb", 0)])      # fresh state, default TTL 600 so the hold stays open
    ap.reset(f)
    ta, tb = ap.login("aa"), ap.login("bb")
    s, b, _ = call("POST", "/authorizations", {"to_handle": "bb", "amount": 400}, token=ta, key=k())
    kn = iso_shift(b["created_at"], -1)
    fut = me(ta, as_of=iso_shift(b["expires_at"], 1000))[1]
    known_before = me(ta, as_of=b["created_at"], known_at=kn)[1]
    record("S3-081", "future as_of beyond deadline -> expired (held 0); known_at before creation -> hold unknown", fut["held"] == 0 and known_before["held"] == 0
           and me(ta)[1]["held"] == 400, {"future_held": fut["held"], "known_before_held": known_before["held"]})
    vo = call("POST", "/authorizations/%s/void" % b["authorization_id"], None, token=ta)
    record("S3-082", "void sets closed_at to the void time", vo[0] == 200 and vo[1].get("closed_at") and vo[1]["closed_at"] >= b["created_at"]
           and me(ta, as_of=vo[1]["closed_at"])[1]["held"] == 0 and me(ta, as_of=iso_shift(vo[1]["closed_at"], -1))[1]["held"] == 400, {"closed_at": vo[1].get("closed_at")})
    # historical_overdraft on AVAILABLE: ee receives 1000 now, authorizes 1000 (available 0), voids; then a backdated decrease of the receipt
    f = ap.fixture([("ff", 5000), ("ee", 0)])
    ap.reset(f)
    tf, te = ap.login("ff"), ap.login("ee")
    s, p, _ = call("POST", "/payments", {"to_handle": "ee", "amount": 1000}, token=tf, key=k())
    time.sleep(0.05)
    s, h, _ = call("POST", "/authorizations", {"to_handle": "ff", "amount": 1000}, token=te, key=k())
    time.sleep(0.05)
    call("POST", "/authorizations/%s/void" % h["authorization_id"], None, token=te)
    s, j, _ = correct(tf, p["payment_id"], 1, 900, p["created_at"])
    record("S3-083", "correction making historical AVAILABLE negative (total fine) -> 409 historical_overdraft", (s, code(j)) == (409, "historical_overdraft"),
           {"s": s, "c": code(j), "ee_now": me(te)[1]})


def time_move_probe():
    """R3-01/R3-02/R3-04: same-amount correction moving effective_at; exact-instant boundaries with server strings."""
    ap.reset(fixture())
    tk = {h: ap.login(h) for h in ("aa", "bb", "cc", "dd")}
    ta = tk["aa"]
    # move p3 (cc->aa 500 at T3) to effective T2 with the same amount
    s, c, _ = correct(tk["cc"], "p3", 1, 500, T2, reason="moved")
    cur = me(ta)[1]["balance"]
    mid = me(ta, as_of=iso_shift(T2, 1000))[1]["balance"]         # between new (T2) and old (T3)
    s2, st, _ = stmt(ta, **{"from": T1, "to": T3})
    ids = [e["payment"]["payment_id"] for e in st["entries"]]
    record("S3-055/R3-01", "same-amount time move: current unchanged, history shifted, entry enters window", s == 201 and cur == 10000 and mid == 10000
           and ids == ["p1", "p2", "p3", "p4"] and st["closing_balance"] == 10000, {"s": s, "cur": cur, "mid": mid, "ids": ids})
    rec_at = c["recorded_at"]
    kn_eq = me(ta, as_of=iso_shift(T2, 1000), known_at=rec_at)[1]["balance"]
    kn_before = me(ta, as_of=iso_shift(T2, 1000), known_at=iso_shift(rec_at, -1))[1]["balance"]
    at_eq = me(ta, as_of=T2)[1]["balance"]
    s3, st2, _ = stmt(ta, **{"from": T1, "to": T2})
    ids2 = [e["payment"]["payment_id"] for e in st2["entries"]]
    record("S3-053/S3-021/S3-031/R3-04", "known_at == recorded_at selects it; as_of == effective_at counts; to == effective_at excludes",
           kn_eq == 10000 and kn_before == 9500 and at_eq == 10000 and ids2 == ["p1"], {"kn_eq": kn_eq, "kn_before": kn_before, "as_of_eq": at_eq, "ids_to_T2": ids2})
    # R3-02: move dd->cc 600 (T3) to before dd was funded (T2) -> dd negative in [T1, T2)
    s, j, _ = correct(tk["dd"], "p5", 1, 600, T1)
    record("S3-049/R3-02", "backdated time move before funding -> 409 historical_overdraft", (s, code(j)) == (409, "historical_overdraft"), {"s": s, "c": code(j)})


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--base", required=True)
    a.add_argument("--out", required=True)
    x = a.parse_args()
    ap.BASE = x.base
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for f in (main_probe, holds_probe, time_move_probe):
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

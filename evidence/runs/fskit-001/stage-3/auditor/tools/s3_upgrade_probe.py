#!/usr/bin/env python3
"""Auditor-owned upgrade probe 1->3 and 2->3 (fskit-001; S3-071, S3-072, S3-058/D3-18, D3-13, D2-13, S3-902).
Sources are the ACCEPTED stage-1 and stage-2 images; targets are fresh stage-3 containers.
Export bodies are held in memory only; only SHA-256 is recorded.

usage: s3_upgrade_probe.py --s1 URL --s2 URL --t13 URL --t23 URL --out results.json
"""
import argparse, hashlib, json, os, sys, time, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "stage-1", "auditor", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "stage-2", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, record, k
from s2_upgrade_probe import raw_call, populate_stage1


def iso(off):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=off)).isoformat(timespec="seconds")


def common_checks(tag, src, tgt, st, extra_receipts=()):
    t = st["tokens"]
    s, ex, _ = call("GET", "/_test/export", base=src)
    ex_sha = hashlib.sha256(json.dumps(ex, sort_keys=True).encode()).hexdigest()
    src_bal = {h: call("GET", "/me", token=t[h], base=src)[1]["balance"] for h in t}
    ap.reset(ap.fixture([("zz", 5)]), base=tgt)
    tz = ap.login("zz", base=tgt)
    si, _, _ = call("POST", "/_test/import", ex, base=tgt)
    mes = {h: call("GET", "/me", token=t[h], base=tgt) for h in t}
    record("S3-071/S3-072 " + tag, "import accepted; old tokens valid; balances kept; destination creds removed",
           s == 200 and si == 204 and all(m[0] == 200 and m[1]["balance"] == src_bal[h] for h, m in mes.items()) and call("GET", "/me", token=tz, base=tgt)[0] == 401,
           {"import": si, "export_sha256": ex_sha})
    reps = [raw_call("POST", "/payments", st["k1"][1], t["aa"], st["k1"][0], tgt), raw_call("POST", "/payments", st["k2"][1], t["aa"], st["k2"][0], tgt),
            raw_call("POST", "/settlements", st["sk"][1], t["op"], st["sk"][0], tgt)]
    origs = [st["r1"][1], st["r2"][1], st["rs"][1]]
    for (path, body, tok, key, orig) in extra_receipts:
        reps.append(raw_call("POST", path, body, tok, key, tgt))
        origs.append(orig)
    record("D2-13/S3-072 " + tag, "source receipts replay 200 with ORIGINAL bytes", all(r[0] == 200 for r in reps) and [r[1] for r in reps] == origs,
           {"statuses": [r[0] for r in reps], "byte_equal": [r[1] == o for r, o in zip(reps, origs)]})
    # historical views over imported history
    tot = sum(call("GET", "/me", token=t[h], base=tgt)[1]["balance"] for h in t)
    tot_past = sum(call("GET", "/me?as_of=2000-01-01T00:00:00%2B00:00", token=t[h], base=tgt)[1]["balance"] for h in t)
    s, sta, _ = call("GET", "/statement?limit=200", token=t["aa"], base=tgt)
    ok_stmt = s == 200 and sta["opening_balance"] + sum(e["delta"] for e in sta["entries"]) == sta["closing_balance"] == src_bal["aa"] and len(sta["entries"]) >= 4
    record("S3-072/D3-13 " + tag, "historical /me and /statement over imported history; conservation now and at opening",
           tot == 15000 and tot_past == 15000 and ok_stmt, {"total": tot, "total_opening": tot_past, "entries": len(sta.get("entries", [])),
                                                            "opening": sta.get("opening_balance"), "closing": sta.get("closing_balance")})
    # correct an imported direct payment (K1: aa->bb 700) at its original instant
    p1 = json.loads(st["r1"][1])
    s, rv, _ = call("GET", "/payments/%s/revisions" % p1["payment_id"], token=t["aa"], base=tgt)
    r1 = rv["revisions"][0] if s == 200 else {}
    s2, c, _ = call("POST", "/payments/%s/corrections" % p1["payment_id"], {"expected_revision": 1, "amount": 600, "effective_at": p1["created_at"], "reason": "upgrade fix"},
                    token=t["aa"], key=k(), base=tgt)
    record("S3-072/D3-13 " + tag, "imported payment has revision 1 at created_at and can be corrected",
           r1.get("effective_at") == p1["created_at"] == r1.get("recorded_at") and r1.get("amount") == 700 and s2 == 201 and c.get("revision") == 2,
           {"rev1": r1, "correct": s2})
    rs = json.loads(st["rs"][1])
    s3, j3, _ = call("POST", "/payments/%s/corrections" % rs["payments"][0]["payment_id"], {"expected_revision": 1, "amount": 1, "effective_at": rs["committed_at"], "reason": "x"},
                     token=t["bb"], key=k(), base=tgt)
    rv2 = call("GET", "/payments/%s/revisions" % rs["payments"][0]["payment_id"], token=t["bb"], base=tgt)[1]["revisions"][0]
    record("S3-070 " + tag, "imported settlement member: rev1 at committed_at; correction 422 linked_payment_immutable",
           (s3, code(j3)) == (422, "linked_payment_immutable") and rv2["effective_at"] == rs["committed_at"], {"s": s3, "c": code(j3)})
    pay = call("POST", "/requests/%s/pay" % st["pending_rq"], {}, token=t["aa"], key=k(), base=tgt)
    record("S3-072 " + tag, "imported pending request payable", pay[0] == 201, {"s": pay[0]})
    return t


def populate_stage2_holds(s2, t):
    """On the stage-2 source (already populated by populate_stage1): open, partial-open, captured, voided holds + a seeded-expired one cannot be added post-reset,
    so an API hold with the service TTL is left open; replay receipts for authorize and capture are recorded."""
    out = {}
    ka = k()
    body = {"to_handle": "cc", "amount": 400, "note": "open-hold"}
    out["auth_open"] = (ka, body, raw_call("POST", "/authorizations", body, t["aa"], ka, s2))
    a_open = json.loads(out["auth_open"][2][1])
    s, a_part, _ = call("POST", "/authorizations", {"to_handle": "cc", "amount": 300}, token=t["aa"], key=k(), base=s2)
    kc = k()
    cb = {"amount": 100, "final": False}
    out["cap_part"] = (a_part["authorization_id"], kc, cb, raw_call("POST", "/authorizations/%s/capture" % a_part["authorization_id"], cb, t["cc"], kc, s2))
    s, a_cap, _ = call("POST", "/authorizations", {"to_handle": "cc", "amount": 200}, token=t["bb"], key=k(), base=s2)
    s, cap_full, _ = call("POST", "/authorizations/%s/capture" % a_cap["authorization_id"], {"amount": 150}, token=t["cc"], key=k(), base=s2)
    s, a_void, _ = call("POST", "/authorizations", {"to_handle": "cc", "amount": 250}, token=t["bb"], key=k(), base=s2)
    call("POST", "/authorizations/%s/void" % a_void["authorization_id"], None, token=t["bb"], base=s2)
    out.update(a_open=a_open, a_part=a_part, a_cap=a_cap, cap_full=cap_full, a_void=a_void)
    return out


def main():
    a = argparse.ArgumentParser()
    for n in ("--s1", "--s2", "--t13", "--t23", "--out"):
        a.add_argument(n, required=True)
    x = a.parse_args()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        ap.BASE = x.s1
        st1 = populate_stage1(x.s1)
        common_checks("1->3", x.s1, x.t13, st1)
    except Exception as e:
        record("ERROR", "1->3", False, {"exception": repr(e)[:300]})
    try:
        ap.BASE = x.s2
        st2 = populate_stage1(x.s2)
        h = populate_stage2_holds(x.s2, st2["tokens"])
        t = st2["tokens"]
        import_before = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 1))
        extra = [("/authorizations", h["auth_open"][1], t["aa"], h["auth_open"][0], h["auth_open"][2][1]),
                 ("/authorizations/%s/capture" % h["cap_part"][0], h["cap_part"][2], t["cc"], h["cap_part"][1], h["cap_part"][3][1])]
        common_checks("2->3", x.s2, x.t23, st2, extra_receipts=extra)
        tgt = x.t23
        lst = {z["authorization_id"]: z for z in call("GET", "/authorizations?limit=200", token=t["cc"], base=tgt)[1]["authorizations"]}
        o, p, c, v = (lst[h[n]["authorization_id"]] for n in ("a_open", "a_part", "a_cap", "a_void"))
        me_aa = call("GET", "/me", token=t["aa"], base=tgt)[1]
        record("S3-071/S3-082/D3-18 2->3", "imported holds: statuses, held, closed_at (capture time; void at import time)",
               o["status"] == "open" and o["closed_at"] is None and p["status"] == "open" and p["remaining_amount"] == 200 and me_aa["held"] == 600
               and c["status"] == "captured" and c["closed_at"] == h["cap_full"]["created_at"] and v["status"] == "voided" and v["closed_at"] is not None
               and v["closed_at"] >= import_before, {"held_aa": me_aa["held"], "cap_closed": c.get("closed_at"), "void_closed": v.get("closed_at")})
        s, j, _ = call("POST", "/payments/%s/corrections" % h["cap_full"]["payment_id"], {"expected_revision": 1, "amount": 1, "effective_at": h["cap_full"]["created_at"],
                       "reason": "x"}, token=t["bb"], key=k(), base=tgt)
        cp = call("POST", "/authorizations/%s/capture" % h["a_open"]["authorization_id"], {"amount": 100}, token=t["cc"], key=k(), base=tgt)
        me2 = call("GET", "/me", token=t["aa"], base=tgt)[1]
        s_ = call("GET", "/statement?limit=200", token=t["cc"], base=tgt)[1]
        caps = [e for e in s_["entries"] if e["payment"].get("authorization_id")]
        record("S3-071/S3-084 2->3", "imported capture correction 422 linked; imported open hold capturable; captures once in statement",
               (s, code(j)) == (422, "linked_payment_immutable") and cp[0] == 201 and me2["held"] == 200 and len(caps) == 3
               and len({e["payment"]["payment_id"] for e in caps}) == 3, {"corr": s, "cap": cp[0], "held": me2["held"], "capture_entries": len(caps)})
    except Exception as e:
        import traceback
        record("ERROR", "2->3", False, {"exception": repr(e)[:300], "at": traceback.format_exc().splitlines()[-3][:200]})
    R = ap.RESULTS
    summ = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(r["pass"] for r in R), "failed": sum(not r["pass"] for r in R), "total": len(R), "results": R}
    json.dump(summ, open(x.out, "w"), indent=1, ensure_ascii=False)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

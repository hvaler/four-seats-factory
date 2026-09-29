#!/usr/bin/env python3
"""Auditor-owned upgrade probe 1->4, 2->4, 3->4 (fskit-001; S4-050/051, D2-13, D3-18, D4-05).
Sources: ACCEPTED stage-1/2/3 images. Targets: fresh stage-4 containers. Export bodies in memory only.
usage: s4_upgrade_probe.py --s1 URL --s2 URL --s3 URL --t14 URL --t24 URL --t34 URL --out results.json"""
import argparse, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ("stage-1", "stage-2", "stage-3"):
    sys.path.insert(0, os.path.join(HERE, "..", "..", "..", d, "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, record, k
from s2_upgrade_probe import raw_call, populate_stage1
from s3_upgrade_probe import populate_stage2_holds


def migrate(tag, src, tgt, st, extra=()):
    t = st["tokens"]
    s, ex, _ = call("GET", "/_test/export", base=src)
    bal = {h: call("GET", "/me", token=t[h], base=src)[1]["balance"] for h in t}
    ap.reset(ap.fixture([("zz", 5)]), base=tgt)
    tz = ap.login("zz", base=tgt)
    si, _, _ = call("POST", "/_test/import", ex, base=tgt)
    ok = si == 204 and all(call("GET", "/me", token=t[h], base=tgt)[1]["balance"] == bal[h] for h in t) and call("GET", "/me", token=tz, base=tgt)[0] == 401
    record("S4-050 " + tag, "import; tokens; balances; destination creds removed", ok, {"import": si, "export_sha256": hashlib.sha256(json.dumps(ex, sort_keys=True).encode()).hexdigest()})
    reps = [raw_call("POST", "/payments", st["k1"][1], t["aa"], st["k1"][0], tgt), raw_call("POST", "/payments", st["k2"][1], t["aa"], st["k2"][0], tgt),
            raw_call("POST", "/settlements", st["sk"][1], t["op"], st["sk"][0], tgt)] + [raw_call(p, b, tk, kk, tgt) for p, b, tk, kk, _ in extra]
    origs = [st["r1"][1], st["r2"][1], st["rs"][1]] + [o for *_, o in extra]
    record("D2-13/S4-042 " + tag, "source receipts replay byte-identical", all(r[0] == 200 for r in reps) and [r[1] for r in reps] == origs,
           {"byte_equal": [r[1] == o for r, o in zip(reps, origs)]})
    p1 = json.loads(st["r1"][1])
    rf = call("POST", "/payments/%s/refunds" % p1["payment_id"], {"amount": 50}, token=t["bb"], key=k(), base=tgt)
    rs = json.loads(st["rs"][1])
    items = [{"payment_id": p["payment_id"], "expected_revision": 1, "amount": 0, "effective_at": rs["committed_at"], "reason": "rev"} for p in rs["payments"]]
    b = call("POST", "/correction-batches", {"corrections": items}, token=t["op"], key=k(), base=tgt)
    rv = call("GET", "/payments/%s/revisions" % p1["payment_id"], token=t["aa"], base=tgt)[1]["revisions"]
    tot = sum(call("GET", "/me", token=t[h], base=tgt)[1]["total"] for h in t)
    record("S4-050 " + tag, "refund of imported payment; batch reversal of imported settlement; imported rev1 correction_batch_id null; conservation",
           rf[0] == 201 and rf[1]["refund_of"] == p1["payment_id"] and b[0] == 201 and len(b[1]["revisions"]) == len(items)
           and rv[0].get("correction_batch_id", "MISSING") is None and tot == 15000, {"refund": rf[0], "batch": b[0], "c": code(b[1]), "total": tot})
    pay = call("POST", "/requests/%s/pay" % st["pending_rq"], {}, token=t["aa"], key=k(), base=tgt)
    record("S4-050 " + tag, "imported pending request payable", pay[0] == 201, {"s": pay[0]})
    return t


def main():
    a = argparse.ArgumentParser()
    for n in ("--s1", "--s2", "--s3", "--t14", "--t24", "--t34", "--out"):
        a.add_argument(n, required=True)
    x = a.parse_args()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for tag, src, tgt in (("1->4", x.s1, x.t14), ("2->4", x.s2, x.t24), ("3->4", x.s3, x.t34)):
        try:
            ap.BASE = src
            st = populate_stage1(src)
            extra = []
            if tag != "1->4":
                h = populate_stage2_holds(src, st["tokens"])
                t = st["tokens"]
                extra = [("/authorizations", h["auth_open"][1], t["aa"], h["auth_open"][0], h["auth_open"][2][1]),
                         ("/authorizations/%s/capture" % h["cap_part"][0], h["cap_part"][2], t["cc"], h["cap_part"][1], h["cap_part"][3][1])]
            snap = None
            if tag == "3->4":
                t = st["tokens"]
                p1 = json.loads(st["r1"][1])
                ck = k()
                cb = {"expected_revision": 1, "amount": 650, "effective_at": p1["created_at"], "reason": "s3 fix"}
                cr = raw_call("POST", "/payments/%s/corrections" % p1["payment_id"], cb, t["aa"], ck, src)
                extra.append(("/payments/%s/corrections" % p1["payment_id"], cb, t["aa"], ck, cr[1]))
                s, s0, _ = call("GET", "/statement?limit=2", token=t["aa"], base=src)
                s, sfull, _ = call("GET", "/statement?snapshot=%s&limit=200" % s0["snapshot"], token=t["aa"], base=src)
                revs_src = call("GET", "/payments/%s/revisions" % p1["payment_id"], token=t["aa"], base=src)[1]
                snap = (s0, sfull, revs_src, p1)
            t = migrate(tag, src, tgt, st, extra)
            if snap:
                s0, sfull, revs_src, p1 = snap
                s, a0, _ = call("GET", "/statement?snapshot=%s&limit=2" % s0["snapshot"], token=t["aa"], base=tgt)
                s2, afull, _ = call("GET", "/statement?snapshot=%s&limit=200" % s0["snapshot"], token=t["aa"], base=tgt)
                rv_t = call("GET", "/payments/%s/revisions" % p1["payment_id"], token=t["aa"], base=tgt)[1]
                same_hist = [{kk: v for kk, v in r.items() if kk != "correction_batch_id"} for r in rv_t["revisions"][:2]] == revs_src["revisions"]
                NEW = {"refund_of", "correction_batch_id"}      # stage-4 additions to representations

                def proj(ents, ref):   # project target entries onto the source field set (recursively for the payment object)
                    out = []
                    for e, r in zip(ents, ref):
                        pe = {kk: e.get(kk) for kk in r}
                        if isinstance(r.get("payment"), dict):
                            pe["payment"] = {kk: e["payment"].get(kk) for kk in r["payment"]}
                        out.append(pe)
                    return out
                extra_fields = set()
                for e in afull.get("entries", []):
                    extra_fields |= set(e.get("payment", {})) - set(sfull["entries"][0]["payment"])
                superset_ok = (s == 200 and len(afull["entries"]) == len(sfull["entries"]) and proj(afull["entries"], sfull["entries"]) == sfull["entries"]
                               and proj(a0["entries"], s0["entries"]) == s0["entries"] and afull["closing_balance"] == sfull["closing_balance"]
                               and afull["opening_balance"] == sfull["opening_balance"] and extra_fields <= NEW)
                record("S4-050/S4-043 3->4", "stage-3 snapshot pages the same entries after import (every stage-3 field equal; only stage-4 fields added); revision history preserved",
                       superset_ok and same_hist, {"s": [s, s2], "hist_same": same_hist, "added_fields": sorted(extra_fields)})
                record("OBS 3->4", "snapshot entries byte-equal including new fields (observation, not asserted)", True,
                       {"exact_equal": afull.get("entries") == sfull["entries"]})
        except Exception as e:
            import traceback
            record("ERROR", tag, False, {"exception": repr(e)[:300], "at": traceback.format_exc().splitlines()[-3][:200]})
    R = ap.RESULTS
    summ = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(r["pass"] for r in R), "failed": sum(not r["pass"] for r in R), "total": len(R), "results": R}
    json.dump(summ, open(x.out, "w"), indent=1, ensure_ascii=False)
    print("SUMMARY passed=%d failed=%d total=%d" % (summ["passed"], summ["failed"], summ["total"]))
    sys.exit(0 if summ["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

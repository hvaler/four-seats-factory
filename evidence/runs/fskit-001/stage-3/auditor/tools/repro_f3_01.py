#!/usr/bin/env python3
"""Auditor's independent reproduction of adversary F3-01 (voided hold seen through an earlier known_at never expires)."""
import json, os, sys, time, datetime as dt, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, k

ap.BASE = sys.argv[1]
q = lambda v: urllib.parse.quote(v, safe="")


def sh(s, ms):
    return (dt.datetime.fromisoformat(s) + dt.timedelta(milliseconds=ms)).isoformat(timespec="milliseconds")


ap.reset(ap.fixture([("aa", 10000), ("bb", 0)]))
ta = ap.login("aa")
s, a, _ = call("POST", "/authorizations", {"to_handle": "bb", "amount": 1000}, token=ta, key=k())
time.sleep(0.05)
K = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
time.sleep(0.05)
v = call("POST", "/authorizations/%s/void" % a["authorization_id"], None, token=ta)[1]
held = lambda as_of, kn=None: call("GET", "/me?as_of=%s%s" % (q(as_of), "&known_at=" + q(kn) if kn else ""), token=ta)[1]["held"]
res = {"A as_of=exp-1ms known=K (exp 1000)": held(sh(a["expires_at"], -1), K),
       "B as_of=exp+1ms known=K (exp 0)": held(sh(a["expires_at"], 1), K),
       "C as_of=2099 known=K (exp 0)": held("2099-01-01T00:00:00+00:00", K),
       "D as_of=2099 no known (exp 0)": held("2099-01-01T00:00:00+00:00")}
print(json.dumps({"created": a["created_at"], "K": K, "closed_at": v.get("closed_at"), "expires": a["expires_at"], "held": res}))
print("REPRODUCED" if res["B as_of=exp+1ms known=K (exp 0)"] == 1000 or res["C as_of=2099 known=K (exp 0)"] == 1000 else "NOT_REPRODUCED")

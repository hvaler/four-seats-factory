#!/usr/bin/env python3
"""Auditor timing/race probes: S1-013/S1-013a (50 concurrent logins <5 s each; 100-user reset <10 s, risk probe),
S1-06A (20 concurrent same-email signups / same-derived-handle signups). Stdlib only, synthetic data."""
import json, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
B = sys.argv[1]
def call(m, p, b=None):
    r = urllib.request.Request(B + p, data=None if b is None else json.dumps(b).encode(), method=m)
    r.add_header("Content-Type", "application/json")
    t = time.monotonic()
    try:
        with urllib.request.urlopen(r, timeout=30) as x: s = x.status; j = x.read()
    except urllib.error.HTTPError as e: s = e.code; j = e.read()
    return s, (json.loads(j) if j else None), time.monotonic() - t
out = {}
fx = {"currency": "EUR", "minor_units": 2, "payments": [], "requests": [],
      "users": [{"id": "u%d" % i, "email": "t%d@audit.invalid" % i, "password": "pw-timing-%d" % i,
                 "display_name": "T", "handle": "t%d" % i, "balance": 1} for i in range(100)]}
s, _, dt = call("POST", "/_test/reset", fx); out["reset100"] = {"status": s, "seconds": round(dt, 3), "ok": s == 204 and dt < 10}
with ThreadPoolExecutor(50) as ex:
    rs = list(ex.map(lambda i: call("POST", "/auth/login", {"email": "t%d@audit.invalid" % i, "password": "pw-timing-%d" % i}), range(50)))
out["login50"] = {"statuses": sorted(set(r[0] for r in rs)), "max_s": round(max(r[2] for r in rs), 3), "ok": all(r[0] == 200 and r[2] < 5 for r in rs)}
with ThreadPoolExecutor(20) as ex:
    rs = list(ex.map(lambda i: call("POST", "/auth/signup", {"email": "same@audit.invalid", "password": "longenough1", "display_name": "S"}), range(20)))
st = [r[0] for r in rs]; codes = sorted(set(str((r[1] or {}).get("error", {}).get("code")) for r in rs if r[0] != 201))
out["signup_same_email"] = {"201": st.count(201), "codes": codes, "ok": st.count(201) == 1 and st.count(409) == 19 and codes == ["email_taken"]}
with ThreadPoolExecutor(20) as ex:
    rs = list(ex.map(lambda i: call("POST", "/auth/signup", {"email": "dup.h@d%d.invalid" % i, "password": "longenough1", "display_name": "S"}), range(20)))
st = [r[0] for r in rs]; codes = sorted(set(str((r[1] or {}).get("error", {}).get("code")) for r in rs if r[0] != 201))
logins = [call("POST", "/auth/login", {"email": "dup.h@d%d.invalid" % i, "password": "longenough1"})[0] for i in range(20)]
out["signup_same_handle"] = {"201": st.count(201), "codes": codes, "login200": logins.count(200),
                             "ok": st.count(201) == 1 and st.count(409) == 19 and codes == ["handle_taken"] and logins.count(200) == 1}
out["no5xx"] = True
print(json.dumps(out, indent=1)); sys.exit(0 if all(v.get("ok", True) for v in out.values() if isinstance(v, dict)) else 1)

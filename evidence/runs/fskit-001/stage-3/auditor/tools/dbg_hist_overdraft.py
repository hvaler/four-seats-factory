#!/usr/bin/env python3
"""Diagnose the S3-049/D3-11 check: after a rejected historical_overdraft correction, did anything change?"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, code, k
import s3_probe as p3

ap.BASE = sys.argv[1]
ap.reset(p3.fixture())
tk = {h: ap.login(h) for h in ("aa", "dd", "ff")}
print("dd before funding", call("GET", "/me", token=tk["dd"])[1]["balance"])
s, j, _ = call("POST", "/payments", {"to_handle": "dd", "amount": 1000}, token=tk["ff"], key=k())
print("fund", s, "dd now", call("GET", "/me", token=tk["dd"])[1]["balance"])
rb = call("GET", "/payments/p4/revisions", token=tk["aa"])
s, j, _ = p3.correct(tk["aa"], "p4", 1, 550, p3.T2)
ra = call("GET", "/payments/p4/revisions", token=tk["aa"])
print("correction", s, code(j))
print("revisions equal:", rb == ra, json.dumps(rb[1])[:200])
print("dd after rejected", call("GET", "/me", token=tk["dd"])[1]["balance"], "aa", call("GET", "/me", token=tk["aa"])[1]["balance"])

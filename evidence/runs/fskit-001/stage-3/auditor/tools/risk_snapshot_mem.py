#!/usr/bin/env python3
"""RISK probe (not a requirement): every first GET /statement stores a snapshot until reset.
~500 payments of history, 5000 statement reads (20 concurrent). Reports p50/p99 latency, 5xx count.
Container memory is sampled by the caller (docker stats) before and after."""
import json, sys, os, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, k

ap.BASE = sys.argv[1]
ap.reset(ap.fixture([("aa", 10 ** 9), ("bb", 10 ** 9)]))
ta, tb = ap.login("aa"), ap.login("bb")
with ThreadPoolExecutor(20) as ex:
    list(ex.map(lambda i: call("POST", "/payments", {"to_handle": "bb" if i % 2 else "aa", "amount": 1 + i}, token=ta if i % 2 else tb, key=k()), range(500)))


def read(i):
    t0 = time.monotonic()
    s, j, _ = call("GET", "/statement?limit=200", token=ta if i % 2 else tb, timeout=30)
    return s, time.monotonic() - t0


t0 = time.monotonic()
with ThreadPoolExecutor(20) as ex:
    rs = list(ex.map(read, range(5000)))
lat = sorted(r[1] for r in rs)
out = {"reads": len(rs), "status": sorted(set(r[0] for r in rs)), "n5xx": sum(1 for r in rs if r[0] >= 500),
       "p50_s": round(lat[len(lat) // 2], 4), "p99_s": round(lat[int(len(lat) * 0.99)], 4), "max_s": round(lat[-1], 4), "wall_s": round(time.monotonic() - t0, 1)}
print(json.dumps(out))

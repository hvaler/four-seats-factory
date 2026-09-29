#!/usr/bin/env python3
"""Count successful GET /statement reads (20 concurrent) until the service stops answering, for a given history size.
usage: risk_snapshot_count.py BASE N_PAYMENTS MAX_READS"""
import json, sys, os, time, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "stage-1", "auditor", "tools"))
import audit_probe as ap
from audit_probe import call, k

ap.BASE = sys.argv[1]
N, MAX = int(sys.argv[2]), int(sys.argv[3])
ap.reset(ap.fixture([("aa", 10 ** 9), ("bb", 10 ** 9)]))
ta, tb = ap.login("aa"), ap.login("bb")
with ThreadPoolExecutor(20) as ex:
    list(ex.map(lambda i: call("POST", "/payments", {"to_handle": "bb" if i % 2 else "aa", "amount": 1 + i}, token=ta if i % 2 else tb, key=k()), range(N)))
ok = [0]
fail = []
lock = threading.Lock()
t0 = time.monotonic()


def read(i):
    if fail:
        return
    try:
        s, _, _ = call("GET", "/statement?limit=1", token=ta if i % 2 else tb, timeout=30)
        with lock:
            if s == 200:
                ok[0] += 1
            else:
                fail.append(("status", s, ok[0]))
    except Exception as e:
        with lock:
            fail.append(("exception", repr(e)[:80], ok[0]))


with ThreadPoolExecutor(20) as ex:
    list(ex.map(read, range(MAX)))
print(json.dumps({"payments": N, "successful_reads": ok[0], "first_failure": fail[0] if fail else None, "wall_s": round(time.monotonic() - t0, 1)}))

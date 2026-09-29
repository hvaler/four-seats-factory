"""RISK PROBE (analyst 88e934d1), not a requirement: ~5000 GET /statement over ~500 payments.
Records latency percentiles, status counts and errors. Memory is recorded by the wrapper script."""
import statistics, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/mnt/c/nexus/dev/band-kit/wt/adversary/verification/adversary/stage-3")
from adv3 import Api, W3, fx3, user

api = Api(timeout=30)
w = W3(api, fx3(users=[user("u_a", "a", 10**9), user("u_b", "b", 10**9)], settlement_operator_ids=[]))
for i in range(500):
    f, t = ("a", "b") if i % 2 == 0 else ("b", "a")
    assert w.api.pay(w.tok[f], t, 1 + i % 7).status == 201
print("payments_created 500", flush=True)
import os
N, TH = int(os.environ.get("PROBE_N", "5000")), int(os.environ.get("PROBE_TH", "10"))
lat, codes, lock = [], {}, threading.Lock()
def worker(k):
    a = Api(timeout=30)
    for i in range(k, N, TH):
        t0 = time.monotonic()
        try:
            r = a.call("GET", "/statement", token=w.tok["ab"[i % 2]], params={"limit": "50"})
            s = r.status
        except Exception as e:
            s = "EXC:" + type(e).__name__
        dt = time.monotonic() - t0
        with lock:
            lat.append(dt); codes[s] = codes.get(s, 0) + 1
    a.close()
t0 = time.monotonic()
with ThreadPoolExecutor(TH) as ex:
    list(ex.map(worker, range(TH)))
wall = time.monotonic() - t0
lat.sort()
q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))]
print(f"reads={len(lat)} wall_s={wall:.1f} codes={codes}")
print(f"latency_s p50={q(0.50):.3f} p95={q(0.95):.3f} p99={q(0.99):.3f} max={lat[-1]:.3f} mean={statistics.mean(lat):.3f}")
print(f"over_5s={sum(1 for x in lat if x > 5)}")
r = w.api.call("GET", "/health"); print("health_after", r.status)

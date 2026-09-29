"""Stage-3 CONC rows: S3-045, S3-065, S3-085."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from adv3 import Api, W3, fx3, iso_ms, new_key, parse_ts, tick, total, user
from datetime import datetime, timezone


def burst(n, fn):
    barrier = threading.Barrier(n)

    def run(i):
        a = Api()
        try:
            barrier.wait(timeout=30)
            return fn(a, i)
        finally:
            a.close()

    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(run, range(n)))


def corr(api, tok, pid, rev, amount, eff, key=None):
    return api.call("POST", f"/payments/{pid}/corrections",
                    {"expected_revision": rev, "amount": amount, "effective_at": eff, "reason": "c"},
                    token=tok, key=key or new_key())


@pytest.mark.obl("S3-065")
@pytest.mark.parametrize("rep", range(3))
def test_same_expected_revision_only_one_wins(w, rep):
    p = w.api.pay(w.tok["ada"], "bob", 1000).json
    tick()
    res = burst(12, lambda a, i: corr(a, w.tok["ada"], p["payment_id"], 1, 900 - i, p["created_at"]))
    assert not [r for r in res if r.status >= 500]
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 1, [r.status for r in res]
    assert all(r.status == 409 and r.code == "stale_revision" for r in res if r.status != 201)
    revs = w.revisions("ada", p["payment_id"]).json["revisions"]
    assert len(revs) == 2 and revs[1]["amount"] == ok[0].json["amount"]
    assert w.me("bob")["balance"] == 2500 + ok[0].json["amount"]


@pytest.mark.obl("S3-045")
def test_recorded_at_strictly_increases_back_to_back(w):
    p = w.api.pay(w.tok["ada"], "bob", 1000).json
    rec = []
    for rev in range(1, 11):
        r = corr(w.api, w.tok["ada"], p["payment_id"], rev, 1000 - rev, p["created_at"])
        assert r.status == 201, r
        rec.append(r.json["recorded_at"])
    revs = w.revisions("bob", p["payment_id"]).json["revisions"]
    strs = [x["recorded_at"] for x in revs]
    assert all(parse_ts(a) < parse_ts(b) for a, b in zip(strs, strs[1:])), strs
    assert all(a < b for a, b in zip(strs[1:], strs[2:])), strs  # as strings too (same format)


@pytest.mark.obl("S3-065", "S3-061", "S3-084")
def test_snapshot_stable_under_concurrent_writes(w):
    for i in range(6):
        w.api.pay(w.tok["ada"], "bob", 10 + i)
        tick(5)
    first = w.statement("ada", limit=200).json
    tok = first["snapshot"]
    stop = threading.Event()
    errs = []

    def writer(i):
        a = Api()
        n = 0
        while not stop.is_set():
            if i % 2:
                r = a.pay(w.tok["ada"], "cy", 1)
            else:
                r = a.call("POST", "/authorizations", {"to_handle": "bob", "amount": 1}, token=w.tok["ada"], key=new_key())
            if r.status >= 500:
                errs.append(r.status)
            n += 1
        a.close()

    th = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
    for t in th:
        t.start()
    reads = []
    for _ in range(20):
        r = w.statement("ada", snapshot=tok, limit=200)
        assert r.status == 200
        reads.append(r.json)
        time.sleep(0.05)
    stop.set()
    for t in th:
        t.join()
    assert not errs
    for r in reads:
        assert r["entries"] == first["entries"] and r["opening_balance"] == first["opening_balance"]
        assert r["closing_balance"] == first["closing_balance"]


@pytest.mark.obl("S3-085", "S3-050")
def test_mixed_concurrent_invariants(api):
    fx = fx3(users=[user(f"u_{h}", h, 5000) for h in ("a", "b", "c")] + [user("u_o", "o", 0)],
             settlement_operator_ids=["u_o"])
    w = W3(api, fx)
    base = [w.api.pay(w.tok[f], t, 300).json for f, t in [("a", "b"), ("b", "c"), ("c", "a")] * 2]
    tick()
    rev = {p["payment_id"]: 1 for p in base}

    def act(a, i):
        k = i % 5
        p = base[i % len(base)]
        if k == 0:
            return corr(a, w.tok[p["from_handle"]], p["payment_id"], rev[p["payment_id"]], 250, p["created_at"])
        if k == 1:
            return a.pay(w.tok["abc"[i % 3]], "abc"[(i + 1) % 3], 40)
        if k == 2:
            return a.call("GET", "/statement", token=w.tok["abc"[i % 3]])
        if k == 3:
            return a.call("GET", "/me", token=w.tok["abc"[i % 3]], params={"as_of": base[0]["created_at"]})
        return a.call("POST", "/authorizations", {"to_handle": "o", "amount": 30}, token=w.tok["abc"[i % 3]], key=new_key())

    for _ in range(3):
        res = burst(40, act)
        assert not [r for r in res if r.status >= 500], [r.status for r in res if r.status >= 500]
        for r in res:
            if r.status == 201 and "revision" in (r.json or {}):
                rev[r.json["payment_id"]] = r.json["revision"]
    now = iso_ms(datetime.now(timezone.utc))
    for T in [base[0]["created_at"], base[-1]["created_at"], now]:
        tot = 0
        for h in ("a", "b", "c", "o"):
            m = w.me_at(h, as_of=T).json
            assert m["total"] >= 0 and m["available"] >= 0 and m["available"] == m["total"] - m["held"], (h, T, m)
            tot += m["total"]
        assert tot == total(fx), T

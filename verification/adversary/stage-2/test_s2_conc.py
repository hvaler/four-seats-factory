"""Stage-2 CONC rows: S2-051, S2-070, S2-071, S1-001/002 as superseded."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from adv2 import Api, W2, fx2, new_key, total, user


def burst(n, fn):
    barrier = threading.Barrier(n)
    lat = [0.0] * n

    def run(i):
        api = Api()
        try:
            barrier.wait(timeout=30)
            t0 = time.monotonic()
            r = fn(api, i)
            lat[i] = time.monotonic() - t0
            return r
        finally:
            api.close()

    with ThreadPoolExecutor(max_workers=n) as ex:
        res = list(ex.map(run, range(n)))
    return res, max(lat)


def no_5xx(res):
    assert not [r for r in res if r.status >= 500], [r for r in res if r.status >= 500]


def cap(api, tok, aid, body, key=None):
    return api.call("POST", f"/authorizations/{aid}/capture", body, token=tok, key=key or new_key())


@pytest.mark.obl("S2-051", "S2-070")
def test_concurrent_partial_captures_never_exceed(w):
    aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
    res, worst = burst(12, lambda a, i: cap(a, w.tok["bob"], aid, {"amount": 300, "final": False}))
    no_5xx(res)
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 6, [r.status for r in res]
    assert all(r.status == 422 and r.code == "capture_exceeds_authorization" for r in res if r.status != 201)
    assert w.me("bob")["total"] == 2500 + 1800 and w.held("ada") == 200
    assert worst < 5


@pytest.mark.obl("S2-051")
def test_concurrent_final_captures_one_wins(w):
    aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
    res, _ = burst(15, lambda a, i: cap(a, w.tok["bob"], aid, {"amount": 100 + i}))
    no_5xx(res)
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 1, [r.status for r in res]
    assert all(r.status == 409 and r.code == "authorization_not_open" for r in res if r.status != 201)
    assert w.me("bob")["total"] == 2500 + ok[0].json["amount"] and w.held("ada") == 0
    assert w.me("ada")["total"] == 10000 - ok[0].json["amount"]


@pytest.mark.obl("S2-051", "S1-078")
def test_concurrent_same_capture_key(w):
    aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
    k = new_key()
    res, _ = burst(15, lambda a, i: cap(a, w.tok["bob"], aid, {"amount": 700, "final": False}, key=k))
    no_5xx(res)
    assert sorted(r.status for r in res) == [200] * 14 + [201]
    assert w.me("bob")["total"] == 3200 and w.held("ada") == 1300


@pytest.mark.obl("S1-078")
def test_concurrent_same_authorization_key(w):
    k = new_key()
    res, _ = burst(15, lambda a, i: a.call("POST", "/authorizations", {"to_handle": "bob", "amount": 900},
                                           token=w.tok["ada"], key=k))
    no_5xx(res)
    assert sorted(r.status for r in res) == [200] * 14 + [201]
    assert w.held("ada") == 900


@pytest.mark.obl("S2-070")
@pytest.mark.parametrize("rep", range(3))
def test_capture_races_void(api, rep):
    w = W2(api, fx2())
    aids = [w.authorize("ada", "bob", 500).json["authorization_id"] for _ in range(8)]

    def act(a, i):
        aid = aids[i // 2]
        if i % 2 == 0:
            return cap(a, w.tok["bob"], aid, {})
        return a.call("POST", f"/authorizations/{aid}/void", token=w.tok["ada"])

    res, _ = burst(16, act)
    no_5xx(res)
    captured = 0
    for j in range(8):
        c, v = res[2 * j], res[2 * j + 1]
        winners = (c.status == 201) + (v.status == 200)
        assert winners == 1, (c, v)
        loser = v if c.status == 201 else c
        assert loser.status == 409 and loser.code == "authorization_not_open", loser
        captured += c.status == 201
    me = w.me("ada")
    assert me["held"] == 0 and me["total"] == 10000 - 500 * captured
    assert w.me("bob")["total"] == 2500 + 500 * captured


@pytest.mark.obl("S2-070", "S1-002")
def test_authorizations_and_payments_compete_for_available(api):
    fx = fx2(users=[user("u_a", "a", 1000), user("u_b", "b", 0), user("u_c", "c", 0)], payments=[],
             requests=[], settlement_operator_ids=[])
    w = W2(api, fx)

    def act(a, i):
        if i % 2:
            return a.call("POST", "/authorizations", {"to_handle": "b", "amount": 70}, token=w.tok["a"], key=new_key())
        return a.pay(w.tok["a"], "c", 70)

    res, _ = burst(40, act)
    no_5xx(res)
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 14, [r.status for r in res]  # 14 * 70 = 980 ≤ 1000 < 15 * 70
    assert all(r.status == 409 and r.code == "insufficient_funds" for r in res if r.status != 201)
    me = w.me("a")
    assert me["available"] == 20 and me["available"] >= 0 and me["total"] + w.me("c")["total"] == 1000


@pytest.mark.obl("S2-071", "S1-001", "S1-002", "S2-070")
def test_mixed_load_conserves_and_never_negative(api):
    fx = fx2(users=[user(f"u_{h}", h, 3000) for h in ("a", "b", "c")] + [user("u_o", "o", 0)],
             payments=[], requests=[], settlement_operator_ids=["u_o"])
    w = W2(api, fx)
    pre = [w.authorize(h, t, 400).json["authorization_id"] for h, t in [("a", "b"), ("b", "c"), ("c", "a")] * 3]
    seen = []
    stop = threading.Event()

    def reader():
        a = Api()
        while not stop.is_set():
            for h in ("a", "b", "c"):
                r = a.call("GET", "/me", token=w.tok[h])
                if r.status == 200:
                    seen.append((r.json["available"], r.json["held"], r.json["total"]))
        a.close()

    th = [threading.Thread(target=reader) for _ in range(2)]
    for x in th:
        x.start()
    owner = {pre[i]: ["b", "c", "a"][i % 3] for i in range(len(pre))}
    payer = {pre[i]: ["a", "b", "c"][i % 3] for i in range(len(pre))}

    def act(a, i):
        k = i % 6
        aid = pre[i % len(pre)]
        if k == 0:
            return a.pay(w.tok[["a", "b", "c"][i % 3]], ["b", "c", "a"][i % 3], 150)
        if k == 1:
            return cap(a, w.tok[owner[aid]], aid, {"amount": 100, "final": False})
        if k == 2:
            return a.call("POST", f"/authorizations/{aid}/void", token=w.tok[payer[aid]])
        if k == 3:
            return a.call("POST", "/authorizations", {"to_handle": "a", "amount": 250}, token=w.tok["b"], key=new_key())
        if k == 4:
            return a.call("POST", "/settlements", {"transfers": [
                {"from_handle": "c", "to_handle": "a", "amount": 200},
                {"from_handle": "a", "to_handle": "b", "amount": 120}]}, token=w.tok["o"], key=new_key())
        return cap(a, w.tok[owner[aid]], aid, {})

    for _ in range(3):
        res, worst = burst(48, act)
        no_5xx(res)
        assert worst < 5, worst
    stop.set()
    for x in th:
        x.join()
    assert seen and all(av >= 0 and held >= 0 and av == tot - held for av, held, tot in seen), \
        [s for s in seen if not (s[0] >= 0 and s[1] >= 0 and s[0] == s[2] - s[1])][:5]
    assert w.totals() == total(fx)

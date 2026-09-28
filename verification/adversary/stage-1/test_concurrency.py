"""CONC rows: §1 invariants, §7 concurrent retries, §11 overlaps, §2 limits."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from advlib import PASSWORD, Api, World, fixture, new_key, total, user


def burst(n, fn):
    """Run fn(i) n times, all released together. Returns (results, max latency)."""
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


def no_5xx(results):
    bad = [r for r in results if r.status >= 500]
    assert not bad, bad


@pytest.mark.obl("S1-002", "S1-058", "S1-013")
def test_overdraft_storm_single_wallet(api):
    fx = fixture(users=[user("u_src", "src", 1000)] + [user(f"u_d{i}", f"d{i}", 0) for i in range(5)],
                 payments=[], requests=[], settlement_operator_ids=[])
    w = World(api, fx)
    tok = w.tok["src"]
    res, worst = burst(50, lambda a, i: a.pay(tok, f"d{i % 5}", 70))
    no_5xx(res)
    ok = [r for r in res if r.status == 201]
    assert all(r.status in (201, 409) for r in res), [r for r in res if r.status not in (201, 409)]
    assert all(r.code == "insufficient_funds" for r in res if r.status == 409)
    assert len(ok) == 1000 // 70  # 14: exactly as many as the balance allows
    assert w.bal("src") == 1000 - 70 * len(ok) >= 0
    assert w.sum() == total(fx)
    assert worst < 5, worst


@pytest.mark.obl("S1-002", "S1-001")
def test_balance_never_read_negative_during_load(api):
    fx = fixture(users=[user("u_a", "a", 500), user("u_b", "b", 500), user("u_c", "c", 0)],
                 payments=[], requests=[], settlement_operator_ids=[])
    w = World(api, fx)
    stop = threading.Event()
    seen = []

    def reader():
        a = Api()
        while not stop.is_set():
            for h in ("a", "b", "c"):
                r = a.call("GET", "/me", token=w.tok[h])
                if r.status == 200:
                    seen.append(r.json["balance"])
        a.close()

    th = [threading.Thread(target=reader) for _ in range(3)]
    for x in th:
        x.start()
    pairs = [("a", "b"), ("b", "c"), ("c", "a"), ("b", "a"), ("a", "c"), ("c", "b")]
    res, _ = burst(40, lambda a, i: a.pay(w.tok[pairs[i % 6][0]], pairs[i % 6][1], 90))
    stop.set()
    for x in th:
        x.join()
    no_5xx(res)
    assert seen and min(seen) >= 0, min(seen)
    assert w.sum() == total(fx)


@pytest.mark.obl("S1-003")
def test_request_paid_at_most_once_different_keys(w):
    rid = w.api.request(w.tok["bob"], "ada", 100).json["request_id"]
    res, _ = burst(20, lambda a, i: a.pay_request(w.tok["ada"], rid, {}))
    no_5xx(res)
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 1, res
    assert all(r.status == 409 and r.code == "request_not_pending" for r in res if r.status != 201)
    assert w.bal("ada") == 9900 and w.bal("bob") == 2600


@pytest.mark.obl("S1-003")
@pytest.mark.parametrize("rounds", range(5))
def test_pay_races_cancel_and_decline(api, rounds):
    w = World(api, fixture())
    rids = [api.request(w.tok["bob"], "ada", 10).json["request_id"] for _ in range(10)]

    def act(a, i):
        rid = rids[i // 3]
        kind = i % 3
        if kind == 0:
            return a.pay_request(w.tok["ada"], rid, {})
        if kind == 1:
            return a.call("POST", f"/requests/{rid}/cancel", token=w.tok["bob"])
        return a.call("POST", f"/requests/{rid}/decline", token=w.tok["ada"])

    res, _ = burst(30, act)
    no_5xx(res)
    paid = 0
    for idx, rid in enumerate(rids):
        trio = res[idx * 3: idx * 3 + 3]
        winners = [r for r in trio if r.status in (200, 201)]
        assert len(winners) == 1, trio
        assert all(r.code == "request_not_pending" for r in trio if r.status == 409), trio
        paid += trio[0].status == 201
    assert w.bal("ada") == 10000 - 10 * paid and w.bal("bob") == 2500 + 10 * paid
    final = {x["request_id"]: x for x in api.requests(w.tok["bob"], limit=200).json["requests"]}
    assert sum(final[r]["status"] == "paid" for r in rids) == paid


@pytest.mark.obl("S1-078")
@pytest.mark.parametrize("name", ["payments", "requests", "pay", "splits", "settlements"])
def test_concurrent_identical_requests_one_effect(w, name):
    rid = w.api.request(w.tok["bob"], "ada", 5).json["request_id"]
    spec = {
        "payments": (w.tok["ada"], "/payments", {"to_handle": "cy", "amount": 100}),
        "requests": (w.tok["ada"], "/requests", {"payer_handle": "cy", "amount": 100}),
        "pay": (w.tok["ada"], f"/requests/{rid}/pay", {"visibility": "private"}),
        "splits": (w.tok["ada"], "/splits", {"amount": 9, "participant_handles": ["ada", "cy"]}),
        "settlements": (w.tok["op"], "/settlements",
                        {"transfers": [{"from_handle": "ada", "to_handle": "cy", "amount": 100}]}),
    }[name]
    tok, path, body = spec
    k = new_key()
    res, _ = burst(20, lambda a, i: a.call("POST", path, body, token=tok, key=k))
    no_5xx(res)
    assert sorted(r.status for r in res) == [200] * 19 + [201], [r.status for r in res]
    first = [r for r in res if r.status == 201][0]
    assert all(r.json == first.json for r in res)
    if name in ("payments", "settlements"):
        assert w.bal("cy") == 100
    if name == "pay":
        assert w.bal("bob") == 2505
    if name in ("requests", "splits"):
        assert len(w.api.requests(w.tok["cy"], limit=200).json["requests"]) == 1


@pytest.mark.obl("S1-078")
@pytest.mark.decision("D-14")
def test_concurrent_same_key_different_bodies(w):
    k = new_key()
    res, _ = burst(20, lambda a, i: a.pay(w.tok["ada"], "cy", 100 + (i % 2), key=k))
    no_5xx(res)
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 1, [r.status for r in res]
    amt = ok[0].json["amount"]
    for r in res:
        if r.status == 200:
            assert r.json == ok[0].json
        elif r.status != 201:
            assert r.status == 409 and r.code == "idempotency_key_reuse", r
    assert w.bal("cy") == amt


@pytest.mark.obl("S1-204", "S1-203", "S1-001")
def test_opposing_payments_and_overlapping_settlements(api):
    fx = fixture(users=[user("u_a", "a", 3000), user("u_b", "b", 3000), user("u_c", "c", 3000),
                        user("u_o", "o", 0)], payments=[], requests=[],
                 settlement_operator_ids=["u_o"])
    w = World(api, fx)

    def act(a, i):
        k = i % 5
        if k == 0:
            return a.pay(w.tok["a"], "b", 37)
        if k == 1:
            return a.pay(w.tok["b"], "a", 41)
        if k == 2:
            return a.pay(w.tok["c"], "a", 29)
        body = {"transfers": [{"from_handle": "a", "to_handle": "c", "amount": 53},
                              {"from_handle": "b", "to_handle": "c", "amount": 31},
                              {"from_handle": "c", "to_handle": "b", "amount": 11}]}
        if k == 4:
            body["transfers"].reverse()
        return a.call("POST", "/settlements", body, token=w.tok["o"], key=new_key())

    for _ in range(3):
        res, worst = burst(50, act)
        no_5xx(res)
        assert all(r.status in (201, 409) for r in res), [r for r in res if r.status not in (201, 409)]
        assert worst < 5, worst
    bal = w.balances()
    assert all(v >= 0 for v in bal.values()), bal
    assert sum(bal.values()) == total(fx)


@pytest.mark.obl("S1-203", "S1-002")
def test_concurrent_settlements_cannot_overdraw(api):
    fx = fixture(users=[user("u_a", "a", 100), user("u_b", "b", 0), user("u_o", "o", 0)],
                 payments=[], requests=[], settlement_operator_ids=["u_o"])
    w = World(api, fx)
    body = {"transfers": [{"from_handle": "a", "to_handle": "b", "amount": 30}]}
    res, _ = burst(20, lambda a_, i: a_.call("POST", "/settlements", body, token=w.tok["o"], key=new_key()))
    no_5xx(res)
    assert sum(r.status == 201 for r in res) == 3
    assert w.bal("a") == 10 and w.bal("b") == 90


@pytest.mark.obl("S1-06A")
def test_concurrent_signup_same_email(w):
    res, _ = burst(20, lambda a, i: a.call("POST", "/auth/signup", {
        "email": "race@example.com", "password": PASSWORD, "display_name": f"R{i}"}))
    no_5xx(res)
    assert sorted(r.status for r in res) == [201] + [409] * 19, [r.status for r in res]
    assert all(r.code == "email_taken" for r in res if r.status == 409)


@pytest.mark.obl("S1-06A")
def test_concurrent_signup_same_handle(w):
    res, _ = burst(20, lambda a, i: a.call("POST", "/auth/signup", {
        "email": f"samehandle@d{i}.example", "password": PASSWORD, "display_name": "H"}))
    no_5xx(res)
    assert sorted(r.status for r in res) == [201] + [409] * 19, [r.status for r in res]
    assert all(r.code == "handle_taken" for r in res if r.status == 409)
    winner = [i for i, r in enumerate(res) if r.status == 201][0]
    for i in range(20):
        r = w.api.call("POST", "/auth/login", {"email": f"samehandle@d{i}.example", "password": PASSWORD})
        assert r.status == (200 if i == winner else 401), (i, r)


@pytest.mark.obl("S1-013a", "S1-013")
def test_50_concurrent_logins_under_5s(w):
    res, worst = burst(50, lambda a, i: a.call("POST", "/auth/login",
                                               {"email": "ada@example.com", "password": PASSWORD}))
    no_5xx(res)
    assert all(r.status == 200 for r in res)
    assert worst < 5, worst


@pytest.mark.obl("S1-013")
def test_50_in_flight_mixed(w):
    def act(a, i):
        k = i % 4
        if k == 0:
            return a.call("GET", "/me", token=w.tok["ada"])
        if k == 1:
            return a.activity(w.tok["bob"])
        if k == 2:
            return a.pay(w.tok["dee"], "cy", 1)
        return a.requests(w.tok["ada"])
    res, worst = burst(50, act)
    no_5xx(res)
    assert all(r.status in (200, 201) for r in res)
    assert worst < 5, worst
    assert w.sum() == total(w.fx)

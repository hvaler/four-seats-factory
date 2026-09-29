"""Stage-4 CONC (S4-023, S4-024, S4-046) and XC upgrades 1→4, 2→4, 3→4 (S4-050..052)."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from adv4 import (Api, W4, assert_error, fixture, fx2, fx3, item, new_key, parse_ts, plus_ms, tick, total, user)


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


def batch_call(a, tok, items, key=None):
    return a.call("POST", "/correction-batches", {"corrections": items}, token=tok, key=key or new_key())


@pytest.mark.obl("S4-024")
def test_same_key_refunds_and_batches(w):
    p = w.api.pay(w.tok["ada"], "bob", 1000).json
    k = new_key()
    res = burst(15, lambda a, i: a.call("POST", f"/payments/{p['payment_id']}/refunds", {"amount": 100},
                                        token=w.tok["bob"], key=k))
    assert sorted(r.status for r in res) == [200] * 14 + [201], [r.status for r in res]
    assert w.me("bob")["total"] == 3400
    q = w.api.pay(w.tok["ada"], "cy", 500).json
    tick()
    kb = new_key()
    res = burst(15, lambda a, i: batch_call(a, w.tok["op"], [item(q, 250)], key=kb))
    assert sorted(r.status for r in res) == [200] * 14 + [201], [r.status for r in res]
    assert len(w.revisions("ada", q["payment_id"]).json["revisions"]) == 2 and w.me("cy")["total"] == 250


@pytest.mark.obl("S4-023")
@pytest.mark.parametrize("rep", range(3))
def test_concurrent_refunds_never_exceed(w, rep):
    p = w.api.pay(w.tok["ada"], "bob", 1000).json
    res = burst(20, lambda a, i: a.call("POST", f"/payments/{p['payment_id']}/refunds", {"amount": 70},
                                        token=w.tok["bob"], key=new_key()))
    assert not [r for r in res if r.status >= 500]
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 14, [r.status for r in res]          # 14 * 70 = 980 <= 1000 < 15 * 70
    assert all(r.code == "refund_exceeds_payment" for r in res if r.status != 201)
    assert w.me("bob")["total"] == 3500 - 980 and w.me("bob")["available"] >= 0
    assert sum(w.me(h)["total"] for h in w.tok) == total(w.fx)


@pytest.mark.obl("S4-046")
@pytest.mark.parametrize("rep", range(3))
def test_overlapping_corrections_one_wins(w, rep):
    p = w.api.pay(w.tok["ada"], "bob", 1000).json
    q = w.api.pay(w.tok["dee"], "cy", 500).json
    tick()

    def act(a, i):
        if i % 3 == 0:
            return a.call("POST", f"/payments/{p['payment_id']}/corrections",
                          {"expected_revision": 1, "amount": 900 - i, "effective_at": p["created_at"], "reason": "s"},
                          token=w.tok["ada"], key=new_key())
        if i % 3 == 1:
            return batch_call(a, w.tok["op"], [item(p, 800 - i), item(q, 400)])
        return batch_call(a, w.tok["op"], [item(q, 300 - i), item(p, 700)])

    res = burst(12, act)
    assert not [r for r in res if r.status >= 500]
    ok = [r for r in res if r.status == 201]
    assert len(ok) == 1, [r.status for r in res]
    assert all(r.status == 409 and r.code == "stale_revision" for r in res if r.status != 201)
    assert len(w.revisions("ada", p["payment_id"]).json["revisions"]) == 2
    assert sum(w.me(h)["total"] for h in w.tok) == total(w.fx)


# --- upgrades ---------------------------------------------------------------------------------

def populate(src, stage):
    fx = fixture() if stage == 1 else fx2()
    src.reset(fx)
    tok = {u["handle"]: src.login(u["email"]) for u in fx["users"]}
    rec = {"fx": fx, "tok": tok}
    rec["k_pay"] = new_key()
    rec["pay"] = src.pay(tok["ada"], "bob", 321, key=rec["k_pay"], note="pre-upgrade")
    rec["k_set"] = new_key()
    rec["set"] = src.call("POST", "/settlements", {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 40},
                                                                 {"from_handle": "ada", "to_handle": "dee", "amount": 15}]},
                          token=tok["op"], key=rec["k_set"])
    if stage >= 2:
        a = src.call("POST", "/authorizations", {"to_handle": "cy", "amount": 600}, token=tok["ada"], key=new_key()).json
        rec["cap"] = src.call("POST", f"/authorizations/{a['authorization_id']}/capture", {"amount": 200, "final": False},
                              token=tok["cy"], key=new_key())
        rec["auth"] = a["authorization_id"]
    if stage == 3:
        p = rec["pay"].json
        rec["k_corr"] = new_key()
        rec["corr"] = src.call("POST", f"/payments/{p['payment_id']}/corrections",
                               {"expected_revision": 1, "amount": 300, "effective_at": p["created_at"], "reason": "s3 fix"},
                               token=tok["ada"], key=rec["k_corr"])
        assert rec["corr"].status == 201
        st = src.call("GET", "/statement", token=tok["bob"], params={"limit": "2"})
        rec["snap"] = st.json["snapshot"]
        rec["snap_pages"] = [src.call("GET", "/statement", token=tok["bob"],
                                      params={"snapshot": rec["snap"], "limit": "2", "offset": str(o)}).json for o in (0, 2)]
        rec["revs"] = src.call("GET", f"/payments/{p['payment_id']}/revisions", token=tok["ada"]).json
    rec["balances"] = {h: src.balance(t) for h, t in tok.items()}
    return rec


def run(src, dst, stage):
    rec = populate(src, stage)
    tok = rec["tok"]
    exp = src.call("GET", "/_test/export")
    dst.reset(fx3())
    assert dst.call("POST", "/_test/import", raw=exp.raw).status == 204
    w = W4.__new__(W4)
    w.api, w.fx, w.tok = dst, rec["fx"], tok
    for h, b in rec["balances"].items():
        assert dst.balance(tok[h]) == b, h
    assert dst.pay(tok["ada"], "bob", 321, key=rec["k_pay"], note="pre-upgrade").raw == rec["pay"].raw
    set_body = {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 40},
                              {"from_handle": "ada", "to_handle": "dee", "amount": 15}]}
    assert dst.call("POST", "/settlements", set_body, token=tok["op"], key=rec["k_set"]).raw == rec["set"].raw
    p = rec["pay"].json
    if stage == 3:
        c = dst.call("POST", f"/payments/{p['payment_id']}/corrections",
                     {"expected_revision": 1, "amount": 300, "effective_at": p["created_at"], "reason": "s3 fix"},
                     token=tok["ada"], key=rec["k_corr"])
        assert c.status == 200 and c.raw == rec["corr"].raw
        exact = True
        for o, pg in zip((0, 2), rec["snap_pages"]):
            got = dst.call("GET", "/statement", token=tok["bob"], params={"snapshot": rec["snap"], "limit": "2", "offset": str(o)}).json
            exact = exact and got == pg
            for k in ("opening_balance", "closing_balance", "has_more"):
                assert got[k] == pg[k], k
            assert len(got["entries"]) == len(pg["entries"])
            for ge, pe in zip(got["entries"], pg["entries"]):
                for k in pe:
                    if k == "payment":
                        assert {kk: ge["payment"][kk] for kk in pe["payment"]} == pe["payment"]
                    else:
                        assert ge[k] == pe[k], k
        rec["snapshot_exact"] = exact
        revs = w.revisions("ada", p["payment_id"]).json["revisions"]
        for old, new in zip(rec["revs"]["revisions"], revs):
            assert {k: new[k] for k in old} == old
            assert new.get("correction_batch_id", "MISSING") is None
    # exercise the imported state with stage-4 features
    cur = p["amount"] if stage < 3 else 300
    assert w.refund("bob", p["payment_id"], cur + 1).code == "refund_exceeds_payment"
    assert w.refund("bob", p["payment_id"], 20).status == 201
    if stage >= 2:
        cap = rec["cap"].json
        r = w.refund("cy", cap["payment_id"], 50)
        assert r.status == 201 and r.json["refund_of"] == cap["payment_id"]
        auth = [x for x in dst.call("GET", "/authorizations", token=tok["ada"]).json["authorizations"]
                if x["authorization_id"] == rec["auth"]][0]
        assert auth["remaining_amount"] == 400 and auth["status"] == "open"
    members = rec["set"].json["payments"]
    b = w.batch([item(m, 0, eff=rec["set"].json["committed_at"]) for m in members])
    assert b.status == 201, b
    assert dst.call("POST", "/settlements", set_body, token=tok["op"], key=rec["k_set"]).raw == rec["set"].raw
    assert sum(dst.balance(t) for t in tok.values()) == total(rec["fx"])
    return rec


@pytest.mark.xc
@pytest.mark.upgrade
@pytest.mark.obl("S4-050", "S4-051")
def test_upgrade_1_to_4(api_s1, api):
    run(api_s1, api, 1)


@pytest.mark.xc
@pytest.mark.upgrade
@pytest.mark.obl("S4-050", "S4-051")
def test_upgrade_2_to_4(api_s2, api):
    run(api_s2, api, 2)


@pytest.mark.xc
@pytest.mark.upgrade
@pytest.mark.obl("S4-050", "S4-051", "S4-052")
def test_upgrade_3_to_4(api_s3, api, record_property):
    rec = run(api_s3, api, 3)
    record_property("observation", f"stage-3 snapshot pages byte-equal as JSON after 3->4: {rec['snapshot_exact']}")

"""XC upgrades 1→3 and 2→3 (S3-071, S3-072, S3-058, S3-902). Exports stay in memory only."""
import pytest

from adv3 import (Ledger, W3, assert_error, fixture, fx2, iso_ms, new_key, parse_ts, plus_ms, tick, total)
from datetime import datetime, timezone

pytestmark = [pytest.mark.xc, pytest.mark.upgrade]


def populate(src, stage):
    fx = fixture() if stage == 1 else fx2()
    src.reset(fx)
    tok = {u["handle"]: src.login(u["email"]) for u in fx["users"]}
    rec = {"fx": fx, "tok": tok}
    rec["k_pay"] = new_key()
    rec["pay"] = src.pay(tok["ada"], "bob", 321, key=rec["k_pay"], note="pre-upgrade")
    rec["pay2"] = src.pay(tok["dee"], "cy", 700)
    rec["set"] = src.call("POST", "/settlements", {"transfers": [{"from_handle": "dee", "to_handle": "cy", "amount": 40}]},
                          token=tok["op"], key=new_key())
    rec["rq"] = src.request(tok["bob"], "ada", 250).json["request_id"]
    rec["failed_key"] = new_key()
    assert src.pay(tok["cy"], "ada", 10**6, key=rec["failed_key"]).status == 409
    if stage == 2:
        rec["k_auth"] = new_key()
        rec["auth_open"] = src.call("POST", "/authorizations", {"to_handle": "bob", "amount": 1000},
                                    token=tok["ada"], key=rec["k_auth"])
        a2 = src.call("POST", "/authorizations", {"to_handle": "cy", "amount": 600}, token=tok["ada"], key=new_key()).json
        rec["k_cap"] = new_key()
        rec["cap"] = src.call("POST", f"/authorizations/{a2['authorization_id']}/capture", {"amount": 200, "final": False},
                              token=tok["cy"], key=rec["k_cap"])
        a3 = src.call("POST", "/authorizations", {"to_handle": "bob", "amount": 50}, token=tok["dee"], key=new_key()).json
        src.call("POST", f"/authorizations/{a3['authorization_id']}/void", token=tok["dee"])
        rec["a2"], rec["a3"] = a2["authorization_id"], a3["authorization_id"]
    rec["balances"] = {h: src.balance(t) for h, t in tok.items()}
    return rec


def run(src, dst, stage):
    rec = populate(src, stage)
    tok = rec["tok"]
    exp = src.call("GET", "/_test/export")
    assert exp.status == 200
    dst.reset(fx2())
    t_import = datetime.now(timezone.utc)
    assert dst.call("POST", "/_test/import", raw=exp.raw).status == 204
    w = W3.__new__(W3)
    w.api, w.fx, w.tok = dst, rec["fx"], tok
    # sessions, balances, receipts
    for h, b in rec["balances"].items():
        assert dst.balance(tok[h]) == b, h
    rp = dst.pay(tok["ada"], "bob", 321, key=rec["k_pay"], note="pre-upgrade")
    assert rp.status == 200 and rp.raw == rec["pay"].raw
    assert dst.pay(tok["cy"], "ada", 1, key=rec["failed_key"]).status == 201
    if stage == 2:
        r = dst.call("POST", "/authorizations", {"to_handle": "bob", "amount": 1000}, token=tok["ada"], key=rec["k_auth"])
        assert r.status == 200 and r.raw == rec["auth_open"].raw
        r = dst.call("POST", f"/authorizations/{rec['a2']}/capture", {"amount": 200, "final": False}, token=tok["cy"], key=rec["k_cap"])
        assert r.status == 200 and r.raw == rec["cap"].raw
    # imported history: revision 1 per payment, statement consistent with a reference ledger
    p = rec["pay"].json
    revs = w.revisions("ada", p["payment_id"]).json["revisions"]
    assert len(revs) == 1 and revs[0]["amount"] == 321 and parse_ts(revs[0]["effective_at"]) == parse_ts(p["created_at"])
    m = dst.call("GET", "/me", token=tok["ada"], params={"as_of": plus_ms(p["created_at"], -1)}).json
    open_ada = rec["fx"]["users"][0]["balance"]
    assert m["balance"] == open_ada, m
    first, entries = w.full_statement("cy")
    assert first["opening_balance"] + sum(e["delta"] for e in entries) == first["closing_balance"]
    assert first["closing_balance"] == dst.balance(tok["cy"])   # default `to` = now
    assert entries[-1]["balance_after"] == first["closing_balance"]
    # corrections on imported payments
    c = w.correct("ada", p["payment_id"], 1, 300, p["created_at"], reason="post-upgrade fix")
    assert c.status == 201, c
    # +1 from cy's reused failed key, +21 returned by the 321→300 correction
    assert dst.balance(tok["ada"]) == rec["balances"]["ada"] + 1 + 21
    set_member = rec["set"].json["payments"][0]
    assert_error(w.correct("dee", set_member["payment_id"], 1, 1, set_member["created_at"]), 422, "linked_payment_immutable")
    if stage == 2:
        cap = rec["cap"].json
        assert_error(w.correct("ada", cap["payment_id"], 1, 1, cap["created_at"]), 422, "linked_payment_immutable")
        # imported open hold is capturable; historical held reflects the imported holds
        aid = rec["auth_open"].json["authorization_id"]
        assert dst.call("POST", f"/authorizations/{aid}/capture", {"amount": 10}, token=tok["bob"], key=new_key()).status == 201
        lst = {x["authorization_id"]: x for x in
               dst.call("GET", "/authorizations", token=tok["ada"], params={"limit": "200"}).json["authorizations"]}
        assert lst[aid]["closed_at"] is not None and lst[rec["a2"]]["closed_at"] is None
    # the request is still payable; conservation in historical views
    assert dst.pay_request(tok["ada"], rec["rq"]).status == 201
    for T in [plus_ms(p["created_at"], -1), p["created_at"], iso_ms(datetime.now(timezone.utc))]:
        assert sum(dst.call("GET", "/me", token=t, params={"as_of": T}).json["total"] for t in tok.values()) == total(rec["fx"])
    return rec, w, t_import


@pytest.mark.obl("S3-058", "S3-083")
@pytest.mark.decision("D3-18", "D3-21")
def test_imported_void_artifact_does_not_block_unrelated_correction(api_s2, api):
    fx = fx2()
    api_s2.reset(fx)
    tok = {u["handle"]: api_s2.login(u["email"]) for u in fx["users"]}
    a = api_s2.call("POST", "/authorizations", {"to_handle": "bob", "amount": 5000}, token=tok["dee"], key=new_key()).json
    assert api_s2.call("POST", f"/authorizations/{a['authorization_id']}/void", token=tok["dee"]).status == 200
    assert api_s2.pay(tok["dee"], "cy", 5000).status == 201      # spends the freed money before the export
    p = api_s2.pay(tok["ada"], "bob", 400).json                   # unrelated to dee
    exp = api_s2.call("GET", "/_test/export")
    api.reset(fx2())
    assert api.call("POST", "/_test/import", raw=exp.raw).status == 204
    r = api.call("POST", f"/payments/{p['payment_id']}/corrections",
                 {"expected_revision": 1, "amount": 350, "effective_at": p["created_at"], "reason": "unrelated"},
                 token=tok["ada"], key=new_key())
    assert r.status == 201, r   # the literal rule would reject because of dee's artifact negative; D3-21 must not
    assert api.balance(tok["ada"]) == 10000 - 350 and api.balance(tok["dee"]) == 0


@pytest.mark.obl("S3-071", "S3-072", "S3-902", "S2-040")
@pytest.mark.decision("D3-13", "D2-13")
def test_upgrade_1_to_3(api_s1, api):
    run(api_s1, api, 1)


@pytest.mark.obl("S3-071", "S3-072", "S3-902", "S3-058")
@pytest.mark.decision("D3-13", "D3-18", "D2-13")
def test_upgrade_2_to_3(api_s2, api):
    rec, w, t_import = run(api_s2, api, 2)
    # D3-18: the stage-2 void releases at the import time (tested as a decision)
    lst = {x["authorization_id"]: x for x in
           w.api.call("GET", "/authorizations", token=rec["tok"]["dee"], params={"limit": "200"}).json["authorizations"]}
    closed = parse_ts(lst[rec["a3"]]["closed_at"])
    assert closed >= t_import.replace(microsecond=(t_import.microsecond // 1000) * 1000), (closed, t_import)

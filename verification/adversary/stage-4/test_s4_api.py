"""Stage-4 API rows: refunds (S4-010..023) and batch corrections (S4-030..047)."""
from datetime import datetime, timedelta, timezone

import pytest

from adv4 import W4, assert_error, fx3, item, iso_ms, new_key, parse_ts, plus_ms, tick, total, user


def mk(w, frm, to, amount, **kw):
    r = w.api.pay(w.tok[frm], to, amount, **kw)
    assert r.status == 201, r
    tick()
    return r.json


def now_iso():
    return iso_ms(datetime.now(timezone.utc))


# --- refunds ---------------------------------------------------------------------------------

@pytest.mark.obl("S4-010", "S4-011", "S4-013")
def test_refund_access_and_validation(w):
    p = mk(w, "ada", "bob", 1000)
    pid = p["payment_id"]
    assert_error(w.api.call("POST", f"/payments/{pid}/refunds", {"amount": 1}, key=new_key()), 401, "unauthenticated")
    assert_error(w.api.call("POST", f"/payments/{pid}/refunds", {"amount": 1}, token=w.tok["bob"]), 400,
                 "missing_idempotency_key")
    for h in ("ada", "cy", "op"):
        assert_error(w.refund(h, pid, 1), 403, "forbidden")
    assert_error(w.refund("bob", "p_nope", 1), 404, "not_found")
    for bad in (0, -1, 1000000001, 1.5, "5", True, None):
        assert_error(w.refund("bob", pid, bad), 422, "validation_failed")
    assert w.me("bob")["total"] == 3500


@pytest.mark.obl("S4-014", "S4-015", "S4-018", "S4-019")
def test_refund_shape_limits_and_feed(w):
    k0 = new_key()
    p = w.api.pay(w.tok["ada"], "bob", 1000, key=k0, note="dinner", visibility="private")
    orig = p.raw
    p = p.json
    assert p["refund_of"] is None
    k = new_key()
    r = w.refund("bob", p["payment_id"], 400, key=k)
    assert r.status == 201, r
    f = r.json
    assert f["refund_of"] == p["payment_id"] and f["from_handle"] == "bob" and f["to_handle"] == "ada"
    assert f["amount"] == 400 and f["note"] == "dinner" and f["visibility"] == "private"
    assert f["request_id"] is None and f["authorization_id"] is None and f["settlement_id"] is None
    assert f["payment_id"] != p["payment_id"]
    rep = w.refund("bob", p["payment_id"], 400, key=k)
    assert rep.status == 200 and rep.json == f
    assert_error(w.refund("bob", p["payment_id"], 401, key=k), 409, "idempotency_key_reuse")
    assert w.refund("bob", p["payment_id"], 600).status == 201          # exactly the rest
    assert_error(w.refund("bob", p["payment_id"], 1), 422, "refund_exceeds_payment")
    assert w.me("ada")["total"] == 10000 and w.me("bob")["total"] == 2500
    feed = w.api.activity(w.tok["ada"], limit=200).json["payments"]
    refunds = [x for x in feed if x.get("refund_of") == p["payment_id"]]
    assert len(refunds) == 2 and all(x["visibility"] == "private" for x in refunds)
    assert all("refund_of" in x for x in feed)
    assert f["payment_id"] not in {x["payment_id"] for x in w.api.activity(w.tok["cy"], limit=200).json["payments"]}
    ents = w.statement("ada").json["entries"]
    got = {e["payment"]["payment_id"]: e for e in ents}
    assert got[f["payment_id"]]["delta"] == 400 and got[f["payment_id"]]["payment"]["refund_of"] == p["payment_id"]
    assert w.api.pay(w.tok["ada"], "bob", 1000, key=k0, note="dinner", visibility="private").raw == orig
    revs = w.revisions("ada", f["payment_id"]).json["revisions"]
    assert len(revs) == 1 and revs[0].get("correction_batch_id", "MISSING") is None


@pytest.mark.obl("S4-012")
@pytest.mark.decision("D4-01")
def test_refund_targets(w):
    rq = w.api.request(w.tok["ada"], "bob", 300).json["request_id"]
    rp = w.api.pay_request(w.tok["bob"], rq).json                       # bob -> ada 300
    assert w.refund("ada", rp["payment_id"], 100).status == 201
    st = [x for x in w.api.requests(w.tok["ada"]).json["requests"] if x["request_id"] == rq][0]
    assert st["status"] == "paid" and st["payment_id"] == rp["payment_id"]
    a = w.authorize("dee", "cy", 500).json
    cap = w.capture("cy", a["authorization_id"], {"amount": 200, "final": False}).json
    rf = w.refund("cy", cap["payment_id"], 50)
    assert rf.status == 201, rf
    auth = [x for x in w.auths("dee").json["authorizations"] if x["authorization_id"] == a["authorization_id"]][0]
    assert auth["status"] == "open" and auth["captured_amount"] == 200 and auth["remaining_amount"] == 300
    assert w.held("dee") == 300
    s = w.settle([{"from_handle": "ada", "to_handle": "cy", "amount": 70}, {"from_handle": "dee", "to_handle": "bob", "amount": 5}]).json
    m = s["payments"][0]
    r = w.refund("cy", m["payment_id"], 20)
    assert r.status == 201 and r.json["settlement_id"] is None, r
    # refunds of refunds: only the refund's receiver (the original sender) reaches invalid_refund_target
    refund = rf.json
    assert_error(w.refund("cy", refund["payment_id"], 1), 403, "forbidden")
    assert_error(w.refund("dee", refund["payment_id"], 1), 422, "invalid_refund_target")


@pytest.mark.obl("S4-014")
@pytest.mark.decision("D4-03", "D4-04")
def test_refund_limit_follows_corrections(w):
    p = mk(w, "ada", "bob", 1000)
    assert w.correct("ada", p["payment_id"], 1, 300, p["created_at"]).status == 201
    assert_error(w.refund("bob", p["payment_id"], 301), 422, "refund_exceeds_payment")
    assert w.refund("bob", p["payment_id"], 300).status == 201
    z = mk(w, "ada", "cy", 10)
    assert w.correct("ada", z["payment_id"], 1, 0, z["created_at"]).status == 201
    assert_error(w.refund("cy", z["payment_id"], 1), 422, "refund_exceeds_payment")


@pytest.mark.obl("S4-016")
def test_refund_uses_available(w):
    p = mk(w, "ada", "cy", 1000)                  # cy total 1000
    w.authorize("cy", "bob", 900)                 # cy available 100
    assert_error(w.refund("cy", p["payment_id"], 101), 409, "insufficient_funds")
    assert w.refund("cy", p["payment_id"], 100).status == 201
    assert w.me("cy")["available"] == 0 and w.me("cy")["held"] == 900


@pytest.mark.obl("S4-017")
@pytest.mark.decision("D4-09")
def test_refund_never_restores_closed_hold(w):
    a = w.authorize("ada", "bob", 1000).json
    cap = w.capture("bob", a["authorization_id"], {"amount": 600}).json     # final: closes, releases 400
    w.refund("bob", cap["payment_id"], 600)
    auth = [x for x in w.auths("ada").json["authorizations"] if x["authorization_id"] == a["authorization_id"]][0]
    assert auth["status"] == "captured" and auth["captured_amount"] == 600 and auth["remaining_amount"] == 0
    assert w.held("ada") == 0 and w.me("ada")["total"] == 10000


@pytest.mark.obl("S4-020", "S4-021", "S4-022")
def test_correction_floor_and_immutables(w):
    p = mk(w, "ada", "bob", 1000)
    f = w.refund("bob", p["payment_id"], 300).json
    assert_error(w.correct("ada", p["payment_id"], 1, 299, p["created_at"]), 422, "refund_exceeds_payment")
    assert_error(w.correct("bob", f["payment_id"], 1, 1, f["created_at"]), 422, "linked_payment_immutable")
    a = w.authorize("ada", "cy", 100).json
    cap = w.capture("cy", a["authorization_id"]).json
    assert_error(w.correct("ada", cap["payment_id"], 1, 1, cap["created_at"]), 422, "linked_payment_immutable")
    w.authorize("bob", "dee", 3000)                     # bob: total 3200, held 3000 -> available 200
    assert_error(w.correct("ada", p["payment_id"], 1, 300, p["created_at"]), 409, "insufficient_funds")
    assert w.correct("ada", p["payment_id"], 1, 800, p["created_at"]).status == 201   # debits bob 200 exactly
    assert w.me("bob")["available"] == 0


# --- batches ----------------------------------------------------------------------------------

@pytest.mark.obl("S4-030", "S4-031", "S4-032")
def test_batch_access_and_shape(w):
    p = mk(w, "ada", "bob", 100)
    good = [item(p, 50)]
    assert_error(w.api.call("POST", "/correction-batches", {"corrections": good}, key=new_key()), 401, "unauthenticated")
    assert_error(w.batch(good, h="ada"), 403, "forbidden")
    assert_error(w.api.call("POST", "/correction-batches", {"corrections": good}, token=w.tok["op"]), 400,
                 "missing_idempotency_key")
    for bad in ([], [item(p, 50), item(p, 40)], "x", [1]):
        assert_error(w.batch(bad), 422, "validation_failed")
    many = [mk(w, "ada", "bob", 1) for _ in range(33)]
    assert_error(w.batch([item(x, 0) for x in many]), 422, "validation_failed")
    assert w.batch([item(x, 0) for x in many[:32]]).status == 201
    assert_error(w.batch([item(p, 50, rev=2)]), 409, "stale_revision")
    assert_error(w.batch([item("p_nope", 1, eff=p["created_at"])]), 404, "not_found")
    assert_error(w.batch([item(p, 50, reason="")]), 422, "validation_failed")
    assert_error(w.batch([item(p, 50, eff=iso_ms(datetime.now(timezone.utc) + timedelta(minutes=5)))]), 422,
                 "validation_failed")
    r = w.batch([item(p, 50, zz_unknown=1)])
    assert r.status == 201, r


@pytest.mark.obl("S4-037")
@pytest.mark.decision("D4-06")
def test_batch_item_precedence_in_input_order(w):
    p = mk(w, "ada", "bob", 100)
    assert_error(w.batch([item(p, 50, rev=5), item("p_nope", 1, eff=p["created_at"])]), 409, "stale_revision")
    assert_error(w.batch([item("p_nope", 1, eff=p["created_at"]), item(p, 50, rev=5)]), 404, "not_found")
    f = w.refund("bob", p["payment_id"], 10).json
    assert_error(w.batch([item(f, 5), item(p, 50, rev=5)]), 422, "linked_payment_immutable")
    assert_error(w.batch([item(p, 5), item("p_nope", 1, eff=p["created_at"])]), 422, "refund_exceeds_payment")


@pytest.mark.obl("S4-033", "S4-034", "S4-035", "S4-036", "S4-042")
@pytest.mark.decision("D4-10", "D4-12")
def test_batch_settlements(w):
    k = new_key()
    s1r = w.settle([{"from_handle": "ada", "to_handle": "bob", "amount": 100},
                    {"from_handle": "dee", "to_handle": "cy", "amount": 50}], key=k)
    s1, s1raw = s1r.json, s1r.raw
    s2 = w.settle([{"from_handle": "ada", "to_handle": "dee", "amount": 30}]).json
    other = mk(w, "bob", "cy", 7)
    m1, m2 = s1["payments"]
    assert_error(w.correct("ada", m1["payment_id"], 1, 1, m1["created_at"]), 422, "linked_payment_immutable")
    assert_error(w.batch([item(m1, 0)]), 422, "incomplete_settlement")
    t = s1["committed_at"]
    alt = parse_ts(t).astimezone(timezone(timedelta(hours=2))).isoformat(timespec="milliseconds")
    assert_error(w.batch([item(m1, 0, eff=t), item(m2, 0, eff=plus_ms(t, -1))]), 422, "validation_failed")
    r = w.batch([item(m1, 0, eff=t), item(m2, 0, eff=alt), item(other, 3), item(s2["payments"][0], 30)])
    assert r.status == 201, r
    b = r.json
    assert set(b) >= {"correction_batch_id", "recorded_at", "revisions"}
    assert [x["payment_id"] for x in b["revisions"]] == [m1["payment_id"], m2["payment_id"], other["payment_id"],
                                                       s2["payments"][0]["payment_id"]]
    assert all(x["recorded_at"] == b["recorded_at"] and x["correction_batch_id"] == b["correction_batch_id"]
               for x in b["revisions"])
    assert parse_ts(b["revisions"][1]["effective_at"]) == parse_ts(t)
    assert w.me("ada")["total"] == 10000 - 30 and w.me("bob")["total"] == 2500 - 3
    assert w.settle([{"from_handle": "ada", "to_handle": "bob", "amount": 100},
                     {"from_handle": "dee", "to_handle": "cy", "amount": 50}], key=k).raw == s1raw
    revs = w.revisions("ada", m1["payment_id"]).json["revisions"]
    assert [x["revision"] for x in revs] == [1, 2] and revs[1]["correction_batch_id"] == b["correction_batch_id"]
    assert revs[0]["correction_batch_id"] is None
    assert parse_ts(revs[1]["recorded_at"]) > parse_ts(revs[0]["recorded_at"])
    assert w.correct("bob", other["payment_id"], 2, 4, other["created_at"]).status == 201   # single after batch
    rv = w.revisions("bob", other["payment_id"]).json["revisions"]
    assert parse_ts(rv[2]["recorded_at"]) > parse_ts(b["recorded_at"]) and rv[2]["correction_batch_id"] is None


@pytest.mark.obl("S4-038", "S4-039", "S4-047")
def test_batch_combined_affordability_and_no_trace(w):
    a = mk(w, "bob", "cy", 2000)          # cy 2000
    mk(w, "cy", "dee", 1500)              # cy 500
    b = mk(w, "dee", "cy", 1500)          # cy 2000
    # reducing a alone to 0 debits cy 2000 now (affordable) but historically cy would be -1500 after its spend;
    # raising b (credit to cy) by 1500 AT THE SAME EARLY INSTANT as a's reduction compensates
    k = new_key()
    lone = w.batch([item(a, 0)], key=k)
    assert_error(lone, 409, "historical_overdraft")
    assert len(w.revisions("cy", a["payment_id"]).json["revisions"]) == 1 and w.me("cy")["total"] == 2000
    combo = w.batch([item(a, 0), item(b, 3000, eff=a["created_at"])], key=k)   # key was not claimed
    assert combo.status == 201, combo
    assert w.me("cy")["total"] == 2000 - 2000 + 1500 and w.me("dee")["total"] == 5000 + 1500 - 3000
    tot = sum(w.me_at(h, as_of=plus_ms(a["created_at"], 1)).json["total"] for h in w.tok)
    assert tot == total(w.fx)


@pytest.mark.obl("S4-037")
def test_batch_current_available_before_historical(w):
    p = mk(w, "ada", "cy", 1000)
    w.authorize("cy", "bob", 950)                 # cy available 50
    assert_error(w.batch([item(p, 900)]), 409, "insufficient_funds")   # debits cy 100 > available 50


@pytest.mark.obl("S4-043")
def test_batch_snapshot_and_known_at(w):
    s = w.settle([{"from_handle": "ada", "to_handle": "bob", "amount": 100},
                  {"from_handle": "bob", "to_handle": "ada", "amount": 40}]).json
    tick()
    snap = w.statement("bob").json
    before = iso_ms(datetime.now(timezone.utc))
    tick()
    r = w.batch([item(m, 0, eff=s["committed_at"]) for m in s["payments"]])
    assert r.status == 201, r
    frozen = w.statement("bob", snapshot=snap["snapshot"]).json
    assert frozen["entries"] == snap["entries"] and frozen["closing_balance"] == snap["closing_balance"]
    new = w.statement("bob").json
    assert new["closing_balance"] == 2500 and all(e["delta"] == 0 for e in new["entries"])
    old = w.statement("bob", known_at=before).json
    assert old["closing_balance"] == 2560 and all(e["revision"] == 1 for e in old["entries"])


@pytest.mark.obl("S4-044")
def test_batch_replay_and_reuse(w):
    p = mk(w, "ada", "bob", 100)
    k = new_key()
    first = w.batch([item(p, 60)], key=k)
    assert first.status == 201
    assert w.batch([item(p, 60, rev=2)]).status == 201
    rep = w.batch([item(p, 60)], key=k)
    assert rep.status == 200 and rep.json == first.json
    assert_error(w.batch([item(p, 61)], key=k), 409, "idempotency_key_reuse")
    assert_error(w.batch([item("p_nope", 1, eff=p["created_at"])], key=k), 409, "idempotency_key_reuse")


@pytest.mark.obl("S4-021", "S4-045")
def test_batch_refund_floor_on_settlement_member(w):
    s = w.settle([{"from_handle": "ada", "to_handle": "cy", "amount": 100},
                  {"from_handle": "dee", "to_handle": "bob", "amount": 10}]).json
    m1, m2 = s["payments"]
    rf = w.refund("cy", m1["payment_id"], 30).json
    assert_error(w.batch([item(m1, 0), item(m2, 0)]), 422, "refund_exceeds_payment")
    assert_error(w.batch([item(m1, 30), item(m2, 0), item(rf, 1)]), 422, "linked_payment_immutable")
    r = w.batch([item(m1, 30), item(m2, 0)])
    assert r.status == 201, r
    assert w.me("cy")["total"] == 0 and w.me("ada")["total"] == 10000

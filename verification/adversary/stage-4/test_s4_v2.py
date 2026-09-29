"""Stage-4 suite v2: r2 rows not covered by v1 (S4-025, S4-026, S4-030/036, S4-038 two-instant, S4-040)."""
from datetime import datetime, timezone

import pytest

from adv4 import W4, assert_error, fx3, item, iso_ms, new_key, parse_ts, plus_ms, tick, total


def mk(w, frm, to, amount, **kw):
    r = w.api.pay(w.tok[frm], to, amount, **kw)
    assert r.status == 201, r
    tick()
    return r.json


@pytest.mark.obl("S4-025", "S4-021")
def test_refund_counts_in_history_and_boundaries(w):
    p = mk(w, "ada", "cy", 1000)                       # t1: cy 1000
    f = w.refund("cy", p["payment_id"], 300).json      # t2: cy 700, ada gets 300 back
    tick()
    assert w.me_at("cy", as_of=plus_ms(f["created_at"], -1)).json["balance"] == 1000
    assert w.me_at("cy", as_of=f["created_at"]).json["balance"] == 700
    ents = {e["payment"]["payment_id"]: e for e in w.statement("cy").json["entries"]}
    assert ents[f["payment_id"]]["delta"] == -300
    # the named case: sender backdates a correction of the target down to exactly the refunded total
    r = w.correct("ada", p["payment_id"], 1, 300, p["created_at"])
    assert r.status == 201, r                         # cy: 300 at t1, then refund 300 at t2 -> 0, never negative
    assert w.me("cy")["balance"] == 0 and w.me_at("cy", as_of=f["created_at"]).json["balance"] == 0
    assert_error(w.correct("ada", p["payment_id"], 2, 299, p["created_at"]), 422, "refund_exceeds_payment")
    assert sum(w.me_at(h, as_of=f["created_at"]).json["total"] for h in w.tok) == total(w.fx)


@pytest.mark.obl("S4-026")
def test_refund_revisions_readers(w):
    p = mk(w, "ada", "bob", 100)
    f = w.refund("bob", p["payment_id"], 40).json
    for h in ("ada", "bob"):
        r = w.revisions(h, f["payment_id"])
        assert r.status == 200 and len(r.json["revisions"]) == 1 and r.json["revisions"][0]["amount"] == 40
    for h in ("cy", "op"):
        assert_error(w.revisions(h, f["payment_id"]), 404, "not_found")
    assert_error(w.batch([item(f, 1)]), 422, "linked_payment_immutable")


@pytest.mark.obl("S4-030", "S4-036")
def test_operator_sender_and_non_operator_paths(api):
    fx = fx3(settlement_operator_ids=["u_ada"])
    w = W4(api, fx)
    w.tok["op"] = w.tok["ada"]                      # ada is the operator here
    s = w.settle([{"from_handle": "ada", "to_handle": "bob", "amount": 50},
                  {"from_handle": "bob", "to_handle": "cy", "amount": 5}]).json
    m = s["payments"][0]
    assert_error(w.correct("ada", m["payment_id"], 1, 0, m["created_at"]), 422, "linked_payment_immutable")
    assert w.batch([item(x, 0, eff=s["committed_at"]) for x in s["payments"]], h="ada").status == 201
    p = mk(w, "bob", "cy", 10)
    assert_error(w.batch([item(p, 5)], h="bob"), 403, "forbidden")
    assert w.correct("bob", p["payment_id"], 1, 5, p["created_at"]).status == 201


@pytest.mark.obl("S4-038", "S4-047")
def test_two_instant_combined_batch(w):
    # dee: 5000. t1: dee -> cy 3000 (x); t2: dee -> bob 2000 (y). dee is at 0 after t2.
    x = mk(w, "dee", "cy", 3000)
    y = mk(w, "dee", "bob", 2000)
    t0 = plus_ms(x["created_at"], -20)
    # moving y earlier to t0 alone: at t0 dee pays 2000 then 3000 at t1 -> fine (5000); not interesting.
    # raise y to 2500 alone -> current dee available 0 -> insufficient_funds (current check first)
    assert_error(w.batch([item(y, 2500)]), 409, "insufficient_funds")
    # combined: reduce x to 2500 at t1 AND raise y to 2500 moved to t0: net debit 0 now;
    # history: t0 dee 5000-2500=2500, t1 2500-2500=0 -> never negative -> 201
    ok = w.batch([item(x, 2500), item(y, 2500, eff=t0)])
    assert ok.status == 201, ok
    assert w.me("dee")["total"] == 0 and w.me("cy")["total"] == 2500 and w.me("bob")["total"] == 5000
    # an arrangement that overdraws in history: cy spends 2000 of x at t3, then the batch moves x after t3.
    # Current balances are unchanged (same amounts), so only the historical check can reject it.
    spend = mk(w, "cy", "ada", 2000)
    later = iso_ms(datetime.now(timezone.utc))
    assert parse_ts(later) > parse_ts(spend["created_at"])
    bad = w.batch([item(x, 2500, eff=later, rev=2), item(y, 2500, eff=t0, rev=2)])
    assert_error(bad, 409, "historical_overdraft")
    assert len(w.revisions("dee", x["payment_id"]).json["revisions"]) == 2
    for T in (plus_ms(t0, -1), t0, x["created_at"], y["created_at"]):
        assert sum(w.me_at(h, as_of=T).json["total"] for h in w.tok) == total(w.fx), T
        assert all(w.me_at(h, as_of=T).json["total"] >= 0 for h in w.tok), T


@pytest.mark.obl("S4-040")
def test_recorded_at_across_batches_and_singles(w):
    p = mk(w, "ada", "bob", 100)
    q = mk(w, "ada", "cy", 100)
    b1 = w.batch([item(p, 90), item(q, 90)]).json
    c = w.correct("ada", p["payment_id"], 2, 80, p["created_at"]).json
    b2 = w.batch([item(p, 70, rev=3), item(q, 70, rev=2)]).json
    t1, tc, t2 = parse_ts(b1["recorded_at"]), parse_ts(c["recorded_at"]), parse_ts(b2["recorded_at"])
    assert t1 < tc < t2, (b1["recorded_at"], c["recorded_at"], b2["recorded_at"])
    assert all(r["recorded_at"] == b2["recorded_at"] for r in b2["revisions"])
    revs = w.revisions("ada", p["payment_id"]).json["revisions"]
    assert [r["correction_batch_id"] for r in revs] == [None, b1["correction_batch_id"], None, b2["correction_batch_id"]]

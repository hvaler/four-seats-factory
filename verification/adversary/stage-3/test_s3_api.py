"""Stage-3 API rows (S3-010..S3-084), checked against the independent reference Ledger."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from adv3 import (W3, Ledger, assert_error, assert_ts, auth_rec, fx3, iso_ms, new_key, parse_ts, plus_ms, tick,
                  total, user)

OPEN = {"ada": 10000, "bob": 2500, "cy": 0, "dee": 5000, "op": 0}
REV_KEYS = {"payment_id", "revision", "amount", "effective_at", "recorded_at", "reason"}


def mk(w, frm, to, amount, **kw):
    r = w.api.pay(w.tok[frm], to, amount, **kw)
    assert r.status == 201, r
    tick()
    return r.json


def now_iso():
    return iso_ms(datetime.now(timezone.utc))


# --- timestamps ----------------------------------------------------------------------------

@pytest.mark.obl("S3-010", "S3-011", "S3-012")
def test_seeded_created_at(api):
    past = "2026-09-01T10:00:00.000+00:00"
    fx = fx3(payments=[{"id": "p_old", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 500,
                        "note": "", "visibility": "public", "created_at": past},
                       {"id": "p_now", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 100,
                        "note": "", "visibility": "public"}])
    w = W3(api, fx)
    assert w.me("ada")["balance"] == 10000 and w.me("bob")["balance"] == 2500  # final balances, not replayed
    feed = {p["payment_id"]: p for p in api.activity(w.tok["ada"]).json["payments"]}
    assert feed["p_old"]["created_at"] == past
    assert_ts(feed["p_now"]["created_at"])
    newp = mk(w, "ada", "bob", 1)
    assert parse_ts(newp["created_at"]) > parse_ts(feed["p_now"]["created_at"]) >= parse_ts(past)
    # opening = seeded ending minus net of original seeded payments
    assert w.me_at("ada", as_of="2026-08-01T00:00:00.000+00:00").json["balance"] == 10000 + 600 + 1 - 1 + 0
    assert w.me_at("bob", as_of="2026-08-01T00:00:00.000+00:00").json["balance"] == 2500 - 600


@pytest.mark.obl("S3-011")
def test_future_seeded_created_at_rejected(api):
    w = W3(api, fx3())
    future = iso_ms(datetime.now(timezone.utc) + timedelta(hours=2))
    bad = fx3(payments=[{"id": "p_f", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 1, "note": "",
                         "visibility": "public", "created_at": future}])
    assert_error(api.call("POST", "/_test/reset", bad), 422, "validation_failed")
    assert w.me("ada")["balance"] == 10000


# --- /me as_of --------------------------------------------------------------------------------

@pytest.mark.obl("S3-020")
@pytest.mark.parametrize("bad", ["2026-09-24T13:20:00", "2026-09-24", "", "yesterday", "2026-13-01T00:00:00+00:00"])
def test_as_of_invalid(w, bad):
    assert_error(w.me_at("ada", as_of=bad), 422, "validation_failed")


@pytest.mark.obl("S3-021", "S3-022")
def test_as_of_inclusive_opening_current_and_echo(w):
    p1 = mk(w, "ada", "bob", 1000)
    p2 = mk(w, "bob", "cy", 300)
    p3 = mk(w, "dee", "ada", 50)
    r = w.me_at("ada", as_of=p1["created_at"])
    assert r.status == 200 and r.json["balance"] == 9000 and r.json["as_of"] == p1["created_at"], r
    assert w.me_at("ada", as_of=plus_ms(p1["created_at"], -1)).json["balance"] == 10000
    assert w.me_at("ada", as_of="2020-01-01T00:00:00+00:00").json["balance"] == 10000
    assert w.me_at("ada", as_of=p3["created_at"]).json["balance"] == 9050
    assert w.me_at("ada", as_of="2099-01-01T00:00:00+00:00").json["balance"] == w.me("ada")["balance"] == 9050
    off = parse_ts(p2["created_at"]).astimezone(timezone(timedelta(hours=2))).isoformat(timespec="milliseconds")
    r = w.me_at("bob", as_of=off)
    assert r.json["as_of"] == off and r.json["balance"] == 2500 + 1000 - 300
    m = w.me_at("bob", as_of=off).json
    assert m["balance"] == m["total"] and m["available"] == m["total"] - m["held"]


# --- statement ---------------------------------------------------------------------------------

def _assert_statement(w, led, h, **q):
    first, entries = w.full_statement(h, **q)
    frm = parse_ts(q["from"]) if "from" in q else None
    to = parse_ts(q["to"]) if "to" in q else None
    kn = parse_ts(q["known_at"]) if "known_at" in q else None
    want = led.entries(h, frm, to, kn)
    got = [(parse_ts(e["effective_at"]), e["payment"]["payment_id"], e["delta"], e["revision"]) for e in entries]
    assert got == want, (h, q, got, want)
    ob = led.balance_before(h, frm, kn) if frm else led.opening[h]
    assert first["opening_balance"] == ob, (first["opening_balance"], ob)
    cb = ob + sum(d for _, _, d, _ in want)
    assert first["closing_balance"] == cb
    run = ob
    for e in entries:
        run += e["delta"]
        assert e["balance_after"] == run
        assert e["payment"]["amount"] == abs(e["delta"]) or e["delta"] == 0
    return first, entries


@pytest.mark.obl("S3-030", "S3-031", "S3-032", "S3-033", "S3-034", "S3-036")
def test_statement_window_order_balances(w):
    led = Ledger(OPEN)
    ps = [mk(w, *t) for t in [("ada", "bob", 100), ("bob", "ada", 40), ("cy", "dee", 0 + 1) if False else ("dee", "cy", 7),
                              ("ada", "cy", 3, ), ("dee", "ada", 25)]]
    priv = mk(w, "ada", "bob", 9, visibility="private")
    other = mk(w, "dee", "bob", 11)          # public but not ada's
    for p in ps + [priv, other]:
        led.add_payment(p)
    first, entries = _assert_statement(w, led, "ada")
    ids = [e["payment"]["payment_id"] for e in entries]
    assert priv["payment_id"] in ids and other["payment_id"] not in ids
    for k in ("opening_balance", "entries", "closing_balance", "has_more", "snapshot"):
        assert k in first, k
    for e in entries:
        assert set(e) >= {"payment", "delta", "balance_after", "revision", "effective_at", "recorded_at"}
    # half-open: a payment exactly at from is in, exactly at to is out
    frm, to = ps[1]["created_at"], ps[4]["created_at"]
    _, win = _assert_statement(w, led, "ada", **{"from": frm, "to": to})
    wid = [e["payment"]["payment_id"] for e in win]
    assert ps[1]["payment_id"] in wid and ps[4]["payment_id"] not in wid
    _assert_statement(w, led, "bob")
    _assert_statement(w, led, "cy", **{"to": ps[3]["created_at"]})


@pytest.mark.obl("S3-035", "S3-064", "S3-030")
def test_statement_pagination_invariant(w):
    led = Ledger(OPEN)
    for i in range(9):
        led.add_payment(mk(w, "ada", "bob", 10 + i))
    full = w.statement("ada", limit=200).json
    seen = []
    for off in (0, 3, 6):
        pg = w.statement("ada", limit=3, offset=off).json
        assert pg["opening_balance"] == full["opening_balance"] and pg["closing_balance"] == full["closing_balance"]
        assert pg["has_more"] is (off < 6)
        seen += pg["entries"]
    assert [e["balance_after"] for e in seen] == [e["balance_after"] for e in full["entries"]]
    pg = w.statement("ada", limit=4, offset=8).json
    assert len(pg["entries"]) == 1 and pg["has_more"] is False
    pg = w.statement("ada", limit=4, offset=50).json
    assert pg["entries"] == [] and pg["has_more"] is False
    for bad in ({"limit": "0"}, {"limit": "1e1"}, {"offset": "-1"}):
        assert_error(w.statement("ada", **bad), 422, "validation_failed")


@pytest.mark.obl("S3-030", "S3-053")
@pytest.mark.parametrize("field", ["from", "to", "known_at"])
@pytest.mark.parametrize("bad", ["2026-09-24T13:20:00", "2026-09-24", ""])
def test_statement_bad_instants(w, field, bad):
    assert_error(w.statement("ada", **{field: bad}), 422, "validation_failed")


@pytest.mark.obl("S3-030")
@pytest.mark.decision("D3-08")
def test_statement_from_after_to(w):
    assert_error(w.statement("ada", **{"from": "2026-09-25T00:00:00+00:00", "to": "2026-09-24T00:00:00+00:00"}),
                 422, "validation_failed")
    r = w.statement("ada", **{"from": "2026-09-24T00:00:00+00:00", "to": "2026-09-24T00:00:00+00:00"})
    assert r.status == 200 and r.json["entries"] == [] and r.json["opening_balance"] == r.json["closing_balance"]


@pytest.mark.obl("S3-032")
@pytest.mark.decision("D3-19")
def test_tie_order_by_id_bytes(api):
    t = "2026-09-10T10:00:00.000+00:00"
    pays = [{"id": pid, "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": n, "note": "",
             "visibility": "public", "created_at": t} for pid, n in [("p_9", 1), ("p_10", 2), ("P_2", 3), ("p_1", 4)]]
    w = W3(api, fx3(payments=pays))
    ids = [e["payment"]["payment_id"] for e in w.statement("ada").json["entries"]]
    assert ids == sorted(ids, key=lambda s: s.encode()) == ["P_2", "p_1", "p_10", "p_9"], ids


# --- corrections -------------------------------------------------------------------------------

@pytest.mark.obl("S3-042", "S3-043")
def test_correction_access_and_validation(w):
    p = mk(w, "ada", "bob", 1000)
    pid, eff = p["payment_id"], p["created_at"]
    assert_error(w.api.call("POST", f"/payments/{pid}/corrections", {"expected_revision": 1, "amount": 1,
                 "effective_at": eff, "reason": "x"}, key=new_key()), 401, "unauthenticated")
    assert_error(w.correct("bob", pid, 1, 900, eff), 403, "forbidden")
    assert_error(w.correct("cy", pid, 1, 900, eff), 403, "forbidden")
    assert_error(w.correct("ada", "p_nope", 1, 900, eff), 404, "not_found")
    assert_error(w.api.call("POST", f"/payments/{pid}/corrections", {"expected_revision": 1, "amount": 1,
                 "effective_at": eff, "reason": "x"}, token=w.tok["ada"]), 400, "missing_idempotency_key")
    future = iso_ms(datetime.now(timezone.utc) + timedelta(minutes=5))
    bads = [dict(amount=-1), dict(amount=1000000001), dict(amount=1.5), dict(reason=""), dict(reason="r" * 201),
            dict(effective_at=future), dict(effective_at="2026-09-24T10:00:00"), dict(expected_revision=0),
            dict(expected_revision=-1)]
    for b in bads:
        body = {"expected_revision": 1, "amount": 900, "effective_at": eff, "reason": "fix", **b}
        r = w.api.call("POST", f"/payments/{pid}/corrections", body, token=w.tok["ada"], key=new_key())
        assert_error(r, 422, "validation_failed")
    for missing in ("expected_revision", "amount", "effective_at", "reason"):
        body = {"expected_revision": 1, "amount": 900, "effective_at": eff, "reason": "fix"}
        del body[missing]
        assert_error(w.api.call("POST", f"/payments/{pid}/corrections", body, token=w.tok["ada"], key=new_key()),
                     422, "validation_failed")
    assert len(w.revisions("ada", pid).json["revisions"]) == 1
    assert w.me("ada")["balance"] == 9000


@pytest.mark.obl("S3-043")
@pytest.mark.decision("D3-02")
def test_correction_wrong_types_are_422(w):
    p = mk(w, "ada", "bob", 1000)
    for b in (dict(expected_revision="1"), dict(reason=5), dict(effective_at=0), dict(amount="900"), dict(amount=True)):
        body = {"expected_revision": 1, "amount": 900, "effective_at": p["created_at"], "reason": "fix", **b}
        assert_error(w.api.call("POST", f"/payments/{p['payment_id']}/corrections", body, token=w.tok["ada"],
                                key=new_key()), 422, "validation_failed")
    r = w.api.call("POST", f"/payments/{p['payment_id']}/corrections",
                   raw='{"expected_revision":1.0,"amount":9e2,"effective_at":"%s","reason":"x"}' % p["created_at"],
                   token=w.tok["ada"], key=new_key())
    assert r.status == 201 and r.json["amount"] == 900, r


@pytest.mark.obl("S3-044", "S3-045", "S3-048", "S3-051", "S3-052", "S3-040")
def test_correction_moves_difference_and_keeps_original(w):
    k = new_key()
    orig = w.api.pay(w.tok["ada"], "bob", 1000, key=k, note="n", visibility="private")
    p = orig.json
    tick()
    c1 = w.correct("ada", p["payment_id"], 1, 1200, p["created_at"], reason="up")
    assert c1.status == 201, c1
    assert set(c1.json) >= REV_KEYS and c1.json["revision"] == 2 and c1.json["amount"] == 1200
    assert c1.json["effective_at"] == p["created_at"] or parse_ts(c1.json["effective_at"]) == parse_ts(p["created_at"])
    assert w.me("ada")["balance"] == 8800 and w.me("bob")["balance"] == 3700
    c2 = w.correct("ada", p["payment_id"], 2, 400, p["created_at"], reason="down")
    assert c2.status == 201 and c2.json["revision"] == 3
    assert w.me("ada")["balance"] == 9600 and w.me("bob")["balance"] == 2900
    revs = w.revisions("bob", p["payment_id"]).json["revisions"]
    assert [r["revision"] for r in revs] == [1, 2, 3] and [r["amount"] for r in revs] == [1000, 1200, 400]
    assert revs[0]["reason"] == "" and revs[0]["effective_at"] == revs[0]["recorded_at"]
    assert parse_ts(revs[0]["recorded_at"]) == parse_ts(p["created_at"])
    rec = [parse_ts(r["recorded_at"]) for r in revs]
    assert rec[0] < rec[1] < rec[2]
    assert set(revs[1]) >= REV_KEYS
    # original payment and its idempotent response are unchanged; the feed shows the original
    rep = w.api.pay(w.tok["ada"], "bob", 1000, key=k, note="n", visibility="private")
    assert rep.status == 200 and rep.raw == orig.raw
    feed = [x for x in w.api.activity(w.tok["bob"], limit=200).json["payments"] if x["payment_id"] == p["payment_id"]]
    assert len(feed) == 1 and feed[0]["amount"] == 1000 and feed[0]["visibility"] == "private"
    assert len(w.api.activity(w.tok["bob"], limit=200).json["payments"]) == 1


@pytest.mark.obl("S3-052")
def test_revisions_access(w):
    p = mk(w, "ada", "bob", 10)
    assert w.revisions("ada", p["payment_id"]).status == 200
    assert w.revisions("bob", p["payment_id"]).status == 200
    assert_error(w.revisions("cy", p["payment_id"]), 404, "not_found")
    assert_error(w.revisions("op", p["payment_id"]), 404, "not_found")
    assert_error(w.api.call("GET", f"/payments/{p['payment_id']}/revisions"), 401, "unauthenticated")
    assert_error(w.revisions("ada", "p_nope"), 404, "not_found")


@pytest.mark.obl("S3-046", "S3-047", "S3-049")
def test_stale_replay_and_key_rules(w):
    p = mk(w, "ada", "bob", 1000)
    k = new_key()
    c = w.correct("ada", p["payment_id"], 1, 800, p["created_at"], key=k)
    assert c.status == 201
    assert_error(w.correct("ada", p["payment_id"], 1, 700, p["created_at"]), 409, "stale_revision")
    assert w.correct("ada", p["payment_id"], 2, 700, p["created_at"]).status == 201
    rep = w.correct("ada", p["payment_id"], 1, 800, p["created_at"], key=k)
    assert rep.status == 200 and rep.json == c.json, rep
    assert_error(w.correct("ada", p["payment_id"], 1, 801, p["created_at"], key=k), 409, "idempotency_key_reuse")
    assert w.me("ada")["balance"] == 9300 and len(w.revisions("ada", p["payment_id"]).json["revisions"]) == 3


@pytest.mark.obl("S3-049")
def test_insufficient_funds_on_increase_and_decrease(w):
    p = mk(w, "cy", "bob", 0) if False else mk(w, "bob", "cy", 2000)   # bob 500, cy 2000
    kf = new_key()
    assert_error(w.correct("bob", p["payment_id"], 1, 2501, p["created_at"], key=kf), 409, "insufficient_funds")
    mk(w, "cy", "dee", 1900)                                               # cy spends: cy 100
    assert_error(w.correct("bob", p["payment_id"], 1, 1800, p["created_at"]), 409, "insufficient_funds")
    assert len(w.revisions("bob", p["payment_id"]).json["revisions"]) == 1
    assert w.me("bob")["balance"] == 500 and w.me("cy")["balance"] == 100
    r = w.correct("bob", p["payment_id"], 1, 1900, p["created_at"], key=kf)   # failed key is reusable
    assert r.status == 201, r
    assert w.me("cy")["balance"] == 0 and w.me("bob")["balance"] == 600


@pytest.mark.obl("S3-049", "S3-083")
def test_historical_overdraft_receiver_spent_earlier(w):
    p = mk(w, "ada", "cy", 1000)        # cy 1000
    q = mk(w, "cy", "dee", 900)         # cy 100
    mk(w, "dee", "cy", 900)             # cy 1000 again: current decrease affordable
    r = w.correct("ada", p["payment_id"], 1, 50, p["created_at"])
    assert_error(r, 409, "historical_overdraft")   # cy would be 50 - 900 < 0 between q and the refund
    assert w.me("cy")["balance"] == 1000 and len(w.revisions("ada", p["payment_id"]).json["revisions"]) == 1


@pytest.mark.obl("S3-049", "S3-055")
def test_historical_overdraft_time_move_sender(w):
    fund = mk(w, "dee", "cy", 500)       # cy 0 -> 500 at t1
    spend = mk(w, "cy", "bob", 500)      # cy -> 0 at t2
    early = plus_ms(fund["created_at"], -5)
    r = w.correct("cy", spend["payment_id"], 1, 500, early, reason="moved earlier")
    assert_error(r, 409, "historical_overdraft")
    later = plus_ms(fund["created_at"], 5)
    r = w.correct("cy", spend["payment_id"], 1, 500, later, reason="moved slightly")
    assert r.status == 201, r
    assert w.me("cy")["balance"] == 0 and w.me("bob")["balance"] == 3000


@pytest.mark.obl("S3-083")
def test_historical_overdraft_via_available_and_holds(w):
    p = mk(w, "ada", "cy", 1000)                                   # cy total 1000 at t1
    aid = w.authorize("cy", "bob", 800).json["authorization_id"]   # hold 800 at t2
    tick()
    assert w.void("cy", aid).status == 200                         # released at t3
    tick()
    r = w.correct("ada", p["payment_id"], 1, 100, p["created_at"])
    assert_error(r, 409, "historical_overdraft")                   # available 100-800 < 0 in [t2,t3)
    r = w.correct("ada", p["payment_id"], 1, 800, p["created_at"])
    assert r.status == 201, r                                      # available exactly 0 in [t2,t3)
    assert w.me("cy")["available"] == 800


@pytest.mark.obl("S3-055", "S3-021", "S3-032")
@pytest.mark.decision("D3-03", "D3-04")
def test_same_amount_time_move_changes_history_only(w):
    led = Ledger(OPEN)
    a = mk(w, "ada", "bob", 100)
    b = mk(w, "ada", "bob", 200)
    c = mk(w, "ada", "bob", 300)
    for x in (a, b, c):
        led.add_payment(x)
    before = (w.me("ada")["balance"], w.me("bob")["balance"])
    new_eff = plus_ms(a["created_at"], -10)
    cr = w.correct("ada", c["payment_id"], 1, 300, new_eff, reason="it happened first")
    assert cr.status == 201, cr
    led.add_revision(cr.json)
    assert (w.me("ada")["balance"], w.me("bob")["balance"]) == before
    for t in (plus_ms(new_eff, -1), new_eff, a["created_at"], b["created_at"], c["created_at"]):
        assert w.me_at("ada", as_of=t).json["balance"] == led.balance("ada", as_of=parse_ts(t)), t
    _assert_statement(w, led, "ada")
    _assert_statement(w, led, "bob", **{"from": a["created_at"]})   # c moved out of this window


@pytest.mark.obl("S3-054")
def test_zero_amount_revision_and_selected_amount(w):
    led = Ledger(OPEN)
    p = mk(w, "ada", "bob", 700)
    led.add_payment(p)
    cr = w.correct("ada", p["payment_id"], 1, 0, p["created_at"], reason="reversed")
    assert cr.status == 201
    led.add_revision(cr.json)
    assert w.me("ada")["balance"] == 10000 and w.me("bob")["balance"] == 2500
    first, entries = _assert_statement(w, led, "ada")
    e = [x for x in entries if x["payment"]["payment_id"] == p["payment_id"]]
    assert len(e) == 1 and e[0]["delta"] == 0 and e[0]["payment"]["amount"] == 0 and e[0]["revision"] == 2
    assert [x["amount"] for x in w.api.activity(w.tok["ada"]).json["payments"]] == [700]   # D3-06


@pytest.mark.obl("S3-053", "S3-050")
@pytest.mark.decision("D3-07", "D3-14")
def test_known_at_selection_and_conservation_grid(w):
    led = Ledger(OPEN)
    p = mk(w, "ada", "bob", 1000)
    q = mk(w, "bob", "cy", 400)
    led.add_payment(p)
    led.add_payment(q)
    before_p = plus_ms(p["created_at"], -1)
    c1 = w.correct("ada", p["payment_id"], 1, 600, p["created_at"]).json
    led.add_revision(c1)
    tick()
    c2 = w.correct("bob", q["payment_id"], 1, 450, plus_ms(p["created_at"], 2)).json
    led.add_revision(c2)
    tick()
    ks = [before_p, p["created_at"], q["created_at"], c1["recorded_at"], plus_ms(c1["recorded_at"], 1),
          c2["recorded_at"], now_iso(), "2099-01-01T00:00:00.000+00:00"]
    ts = [before_p, p["created_at"], plus_ms(p["created_at"], 2), q["created_at"], "2099-01-01T00:00:00.000+00:00"]
    for K in ks:
        for T in ts:
            tot = 0
            for h in OPEN:
                r = w.me_at(h, as_of=T, known_at=K)
                assert r.status == 200, r
                if h in ("ada", "bob", "cy"):
                    assert r.json["balance"] == led.balance(h, parse_ts(T), parse_ts(K)), (h, T, K)
                assert r.json["known_at"] == K and r.json["as_of"] == T
                tot += r.json["balance"]
            assert tot == total(w.fx), (T, K)
    r = w.me_at("ada", known_at=c1["recorded_at"])          # D3-07: as_of = now
    assert r.json["balance"] == led.balance("ada", None, parse_ts(c1["recorded_at"]))
    for K in (before_p, c1["recorded_at"], plus_ms(c1["recorded_at"], -1)):
        _assert_statement(w, led, "bob", known_at=K)


# --- snapshots ------------------------------------------------------------------------------------

@pytest.mark.obl("S3-060", "S3-061", "S3-062", "S3-063", "S3-064", "S3-065")
@pytest.mark.decision("D3-09")
def test_snapshot_is_frozen(w):
    for i in range(5):
        mk(w, "ada", "bob", 10 + i)
    first = w.statement("ada", limit=2).json
    tok = first["snapshot"]
    assert isinstance(tok, str) and tok
    frozen = w.statement("ada", limit=200).json
    p = mk(w, "ada", "bob", 999)
    w.correct("ada", w.statement("ada").json["entries"][0]["payment"]["payment_id"], 1, 1, now_iso())
    pages = []
    for off in (0, 2, 4):
        r = w.statement("ada", snapshot=tok, limit=2, offset=off)
        assert r.status == 200, r
        assert r.json["opening_balance"] == first["opening_balance"] and r.json["closing_balance"] == first["closing_balance"]
        assert r.json["has_more"] is (off < 4)
        pages += r.json["entries"]
    assert [e["payment"]["payment_id"] for e in pages] == [e["payment"]["payment_id"] for e in frozen["entries"]][:5]
    assert [e["balance_after"] for e in pages] == [e["balance_after"] for e in frozen["entries"]][:5]
    assert p["payment_id"] not in [e["payment"]["payment_id"] for e in pages]
    r = w.statement("ada", snapshot=tok, limit=2, offset=40)
    assert r.status == 200 and r.json["entries"] == [] and r.json["has_more"] is False
    for extra in ({"from": "2026-01-01T00:00:00+00:00"}, {"to": "2099-01-01T00:00:00+00:00"},
                  {"known_at": "2099-01-01T00:00:00+00:00"}):
        assert_error(w.statement("ada", snapshot=tok, **extra), 422, "validation_failed")
    assert w.statement("ada", snapshot=tok, as_of="2026-01-01T00:00:00+00:00", zz="1").status == 200
    assert_error(w.statement("bob", snapshot=tok), 404, "not_found")
    assert_error(w.statement("ada", snapshot="not-a-token"), 404, "not_found")
    w.api.reset(fx3())
    t2 = w.api.login("ada@example.com")
    assert_error(w.api.call("GET", "/statement", token=t2, params={"snapshot": tok}), 404, "not_found")


# --- linked payments --------------------------------------------------------------------------------

@pytest.mark.obl("S3-070", "S3-071")
def test_linked_payments_immutable(w):
    s = w.api.call("POST", "/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 10},
                                                          {"from_handle": "dee", "to_handle": "cy", "amount": 5}]},
                   token=w.tok["op"], key=new_key()).json
    m = s["payments"][0]
    assert_error(w.correct("ada", m["payment_id"], 1, 5, m["created_at"]), 422, "linked_payment_immutable")
    revs = w.revisions("ada", m["payment_id"]).json["revisions"]
    assert revs[0]["effective_at"] == revs[0]["recorded_at"] and parse_ts(revs[0]["effective_at"]) == parse_ts(s["committed_at"])
    aid = w.authorize("ada", "bob", 100).json["authorization_id"]
    cap = w.capture("bob", aid).json
    assert_error(w.correct("ada", cap["payment_id"], 1, 50, cap["created_at"]), 422, "linked_payment_immutable")
    entries = w.statement("bob").json["entries"]
    assert [e["payment"]["payment_id"] for e in entries].count(cap["payment_id"]) == 1
    assert [e for e in entries if e["payment"]["payment_id"] == cap["payment_id"]][0]["payment"]["authorization_id"] == aid


@pytest.mark.obl("S3-042", "S3-070")
@pytest.mark.decision("D3-05")
def test_request_payment_correctable_zero_upward(w):
    sp = w.api.call("POST", "/splits", {"amount": 1, "participant_handles": ["bob", "cy", "dee"]},
                    token=w.tok["bob"], key=new_key()).json
    rq = [r for r in sp["requests"] if r["payer_handle"] == "cy"][0]
    pay = w.api.pay_request(w.tok["cy"], rq["request_id"]).json
    assert pay["amount"] == 0
    tick()
    assert_error(w.correct("cy", pay["payment_id"], 1, 5, pay["created_at"]), 409, "insufficient_funds")
    mk(w, "dee", "cy", 5)
    r = w.correct("cy", pay["payment_id"], 1, 5, now_iso())
    assert r.status == 201, r
    assert w.me("cy")["balance"] == 0
    st = [x for x in w.api.requests(w.tok["bob"]).json["requests"] if x["request_id"] == rq["request_id"]][0]
    assert st["status"] == "paid" and st["payment_id"] == pay["payment_id"]


# --- historical holds --------------------------------------------------------------------------------

@pytest.mark.obl("S3-080", "S3-082", "S3-023")
def test_hold_lifecycle_in_history(w):
    a = w.authorize("ada", "bob", 2000).json
    tick(30)
    c1 = w.capture("bob", a["authorization_id"], {"amount": 500, "final": False}).json
    tick(30)
    v = w.void("ada", a["authorization_id"]).json
    assert v["closed_at"] is not None and parse_ts(v["closed_at"]) >= parse_ts(c1["created_at"])
    assert_ts(v["closed_at"])
    open_a = w.authorize("ada", "cy", 100).json
    assert open_a["closed_at"] is None
    def at(t):
        return w.me_at("ada", as_of=t).json
    m = at(plus_ms(a["created_at"], -1))
    assert m["held"] == 0 and m["total"] == 10000
    m = at(a["created_at"])
    assert (m["total"], m["held"], m["available"]) == (10000, 2000, 8000), m
    m = at(c1["created_at"])
    assert (m["total"], m["held"], m["available"]) == (9500, 1500, 8000), m
    m = at(v["closed_at"])
    assert (m["total"], m["held"]) == (9500, 0), m
    assert m["balance"] == m["total"] and m["available"] == m["total"] - m["held"]
    lst = {x["authorization_id"]: x for x in w.auths("ada").json["authorizations"]}
    assert lst[a["authorization_id"]]["closed_at"] == v["closed_at"]
    assert lst[open_a["authorization_id"]]["closed_at"] is None


@pytest.mark.slow
@pytest.mark.obl("S3-080", "S3-081", "S3-082")
def test_expiry_in_history_and_future(api):
    w = W3(api, fx3(authorization_ttl_seconds=2))
    a = w.authorize("ada", "bob", 1000).json
    exp = a["expires_at"]
    assert w.me_at("ada", as_of=plus_ms(exp, 10)).json["held"] == 0          # future: expires at its deadline
    assert w.me_at("ada", as_of=plus_ms(exp, -10)).json["held"] == 1000
    time.sleep(2.5)
    lst = [x for x in w.auths("ada").json["authorizations"] if x["authorization_id"] == a["authorization_id"]][0]
    assert lst["status"] == "expired" and parse_ts(lst["closed_at"]) == parse_ts(exp)
    assert w.me_at("ada", as_of=plus_ms(exp, -10)).json["held"] == 1000
    assert w.me_at("ada", as_of=exp).json["held"] == 0


@pytest.mark.obl("S3-081")
def test_void_unknown_before_its_event_time(w):
    a = w.authorize("ada", "bob", 1000).json
    tick(30)
    before_void = now_iso()
    tick(30)
    v = w.void("ada", a["authorization_id"]).json
    far = "2099-01-01T00:00:00.000+00:00"
    # known before the void: the hold is still open, so at a far future as_of it has expired at its deadline
    m = w.me_at("ada", as_of=plus_ms(a["expires_at"], -1), known_at=before_void).json
    assert m["held"] == 1000, m
    m = w.me_at("ada", as_of=plus_ms(a["expires_at"], -1), known_at=v["closed_at"]).json
    assert m["held"] == 0, m
    m = w.me_at("ada", as_of=far, known_at=before_void).json
    assert m["held"] == 0 and m["available"] == m["total"]


@pytest.mark.obl("S3-084")
def test_statement_money_only(w):
    a = w.authorize("ada", "bob", 300).json
    w.capture("bob", a["authorization_id"], {"amount": 100, "final": False})
    w.void("ada", a["authorization_id"])
    ents = w.statement("ada").json["entries"]
    assert len(ents) == 1 and ents[0]["delta"] == -100 and ents[0]["payment"]["authorization_id"] == a["authorization_id"]


@pytest.mark.obl("S2-058", "S3-082")
def test_seeded_hold_created_at_default_and_supplied(api):
    past = "2026-09-20T08:00:00.000+00:00"
    fx = fx3(authorizations=[auth_rec("a_s1", "u_ada", "u_bob", 300), auth_rec("a_s2", "u_ada", "u_bob", 200, created_at=past)])
    w = W3(api, fx)
    assert w.me_at("ada", as_of="2026-09-21T00:00:00.000+00:00").json["held"] == 200
    assert w.me("ada")["held"] == 500

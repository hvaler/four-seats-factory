"""§4 request lifecycle, §8 POST /requests, pay, decline, cancel, GET /requests."""
import pytest

from advlib import World, assert_error, assert_ts, fixture, new_key, user

REQUEST_KEYS = {"request_id", "requester_id", "requester_handle", "payer_id",
                "payer_handle", "amount", "currency", "note", "status",
                "payment_id", "created_at"}


@pytest.mark.obl("S1-100", "S1-102", "S1-037")
def test_create_request_above_balance(w):
    r = w.api.request(w.tok["bob"], "cy", 999999, note="big")
    assert r.status == 201, r
    rq = r.json
    assert set(rq) >= REQUEST_KEYS
    assert rq["requester_id"] == "u_bob" and rq["requester_handle"] == "bob"
    assert rq["payer_id"] == "u_cy" and rq["payer_handle"] == "cy"
    assert rq["amount"] == 999999 and rq["currency"] == "EUR" and rq["note"] == "big"
    assert rq["status"] == "pending" and rq["payment_id"] is None
    assert_ts(rq["created_at"])
    assert_error(w.api.pay_request(w.tok["cy"], rq["request_id"]), 409, "insufficient_funds")
    assert w.bal("cy") == 0
    got = w.api.requests(w.tok["cy"]).json["requests"]
    assert [x for x in got if x["request_id"] == rq["request_id"]][0]["status"] == "pending"


@pytest.mark.obl("S1-037", "S1-110")
def test_request_becomes_payable_later(w):
    rq = w.api.request(w.tok["bob"], "cy", 300, note="later").json
    assert_error(w.api.pay_request(w.tok["cy"], rq["request_id"]), 409, "insufficient_funds")
    assert w.api.pay(w.tok["ada"], "cy", 300).status == 201
    r = w.api.pay_request(w.tok["cy"], rq["request_id"], {"visibility": "private"})
    assert r.status == 201, r
    p = r.json
    assert p["from_user_id"] == "u_cy" and p["to_user_id"] == "u_bob"
    assert p["amount"] == 300 and p["visibility"] == "private"
    assert p["request_id"] == rq["request_id"] and p["settlement_id"] is None
    assert p["note"] == "later"  # D-10
    assert w.bal("cy") == 0 and w.bal("bob") == 2800
    got = [x for x in w.api.requests(w.tok["bob"]).json["requests"]
           if x["request_id"] == rq["request_id"]][0]
    assert got["status"] == "paid" and got["payment_id"] == p["payment_id"]


@pytest.mark.obl("S1-110")
def test_pay_default_visibility_public(w):
    r = w.api.pay_request(w.tok["ada"], "rq_1")
    assert r.status == 201 and r.json["visibility"] == "public", r


@pytest.mark.obl("S1-110")
@pytest.mark.decision("D-20")
def test_pay_empty_body_reads_as_empty_object(w):
    k = new_key()
    r = w.api.call("POST", "/requests/rq_1/pay", token=w.tok["ada"], key=k)
    assert r.status == 201 and r.json["visibility"] == "public", r
    r2 = w.api.call("POST", "/requests/rq_1/pay", {}, token=w.tok["ada"], key=k)
    assert r2.status == 200 and r2.json == r.json, r2


@pytest.mark.obl("S1-101")
def test_request_validation(w):
    b = w.tok["bob"]
    assert_error(w.api.request(b, "bob", 1), 422, "self_request")
    assert_error(w.api.request(b, "nobody", 1), 404, "not_found")
    assert_error(w.api.request(b, "ada", 0), 422, "validation_failed")
    assert_error(w.api.request(b, "ada", 1000000001), 422, "validation_failed")
    assert_error(w.api.request(b, "ada", "5"), 422, "validation_failed")
    assert_error(w.api.request(b, "ada", True), 422, "validation_failed")
    assert_error(w.api.request(b, "ada", 1, note="x" * 201), 422, "validation_failed")
    assert_error(w.api.request(b, "ada", 1, note=None), 422, "validation_failed")
    assert w.api.request(b, "ada", 1000000000, note="x" * 200).status == 201
    r = w.api.call("POST", "/requests", {"payer_handle": 7, "amount": 1}, token=b, key=new_key())
    assert_error(r, 400, "malformed_request")
    r = w.api.call("POST", "/requests", {"amount": 1}, token=b, key=new_key())
    assert_error(r, 422, "validation_failed")


@pytest.mark.obl("S1-112", "S1-036")
def test_pay_errors(w):
    assert_error(w.api.pay_request(w.tok["bob"], "rq_1"), 403, "forbidden")
    assert_error(w.api.pay_request(w.tok["cy"], "rq_1"), 403, "forbidden")  # D-04
    assert_error(w.api.pay_request(w.tok["ada"], "rq_nope"), 404, "not_found")
    assert w.api.pay_request(w.tok["ada"], "rq_1").status == 201
    assert_error(w.api.pay_request(w.tok["ada"], "rq_1"), 409, "request_not_pending")
    assert w.bal("ada") == 8800 and w.bal("bob") == 3700


@pytest.mark.obl("S1-120", "S1-206")
def test_decline(w):
    a = w.tok["ada"]
    assert_error(w.api.call("POST", "/requests/rq_1/decline", token=w.tok["bob"]), 403, "forbidden")
    assert_error(w.api.call("POST", "/requests/rq_nope/decline", token=a), 404, "not_found")
    r = w.api.call("POST", "/requests/rq_1/decline", token=a)  # no body at all
    assert r.status == 200 and r.json["status"] == "declined", r
    assert set(r.json) >= REQUEST_KEYS
    r = w.api.call("POST", "/requests/rq_1/decline", {"junk": 1}, token=a)
    assert r.status == 200 and r.json["status"] == "declined", r
    assert_error(w.api.call("POST", "/requests/rq_1/cancel", token=w.tok["bob"]), 409, "request_not_pending")
    assert_error(w.api.pay_request(a, "rq_1"), 409, "request_not_pending")
    assert w.bal("ada") == 10000


@pytest.mark.obl("S1-121", "S1-206")
def test_cancel(w):
    b = w.tok["bob"]
    assert_error(w.api.call("POST", "/requests/rq_1/cancel", token=w.tok["ada"]), 403, "forbidden")
    r = w.api.call("POST", "/requests/rq_1/cancel", token=b)
    assert r.status == 200 and r.json["status"] == "cancelled", r
    r = w.api.call("POST", "/requests/rq_1/cancel", raw="not even json", token=b)
    assert r.status == 200 and r.json["status"] == "cancelled", r
    assert_error(w.api.call("POST", "/requests/rq_1/decline", token=w.tok["ada"]), 409, "request_not_pending")
    assert_error(w.api.pay_request(w.tok["ada"], "rq_1"), 409, "request_not_pending")


@pytest.mark.obl("S1-120", "S1-121")
def test_paid_cannot_be_declined_or_cancelled(w):
    assert w.api.pay_request(w.tok["ada"], "rq_1").status == 201
    assert_error(w.api.call("POST", "/requests/rq_1/decline", token=w.tok["ada"]), 409, "request_not_pending")
    assert_error(w.api.call("POST", "/requests/rq_1/cancel", token=w.tok["bob"]), 409, "request_not_pending")


@pytest.mark.obl("S1-070")
def test_decline_cancel_need_no_key_and_paths_need_key(w):
    a = w.tok["ada"]
    for path, body in [("/payments", {"to_handle": "bob", "amount": 1}),
                       ("/requests", {"payer_handle": "bob", "amount": 1}),
                       ("/requests/rq_1/pay", {}),
                       ("/splits", {"amount": 3, "participant_handles": ["ada", "bob"]}),
                       ("/settlements", {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 1}]})]:
        tok = w.tok["op"] if path == "/settlements" else a
        assert_error(w.api.call("POST", path, body, token=tok), 400, "missing_idempotency_key")
        assert_error(w.api.call("POST", path, body, token=tok, key=""), 400, "missing_idempotency_key")
    assert w.bal("ada") == 10000


@pytest.mark.obl("S1-040", "S1-130", "S1-131")
def test_get_requests_scope_and_filters(w):
    a, b, c = w.tok["ada"], w.tok["bob"], w.tok["cy"]
    r2 = w.api.request(a, "bob", 10).json      # ada requests from bob
    r3 = w.api.request(c, "ada", 20).json      # cy requests from ada
    w.api.call("POST", f"/requests/{r3['request_id']}/decline", token=a)
    r4 = w.api.request(b, "cy", 30).json       # bob <-> cy only
    ids = lambda resp: [x["request_id"] for x in resp.json["requests"]]
    everything = ids(w.api.requests(a))
    assert set(everything) == {"rq_1", r2["request_id"], r3["request_id"]}
    assert r4["request_id"] not in everything
    assert everything[0] in (r3["request_id"], r2["request_id"])  # newest first
    assert everything[-1] == "rq_1"                                # D-32
    assert set(ids(w.api.requests(a, direction="incoming"))) == {"rq_1", r3["request_id"]}
    assert set(ids(w.api.requests(a, direction="outgoing"))) == {r2["request_id"]}
    assert set(ids(w.api.requests(a, status="declined"))) == {r3["request_id"]}
    assert set(ids(w.api.requests(a, direction="incoming", status="pending"))) == {"rq_1"}
    assert ids(w.api.requests(a, direction="outgoing", status="declined")) == []
    assert ids(w.api.requests(w.tok["op"])) == []   # operator sees nothing extra
    assert ids(w.api.requests(w.tok["dee"])) == []


@pytest.mark.obl("S1-131")
@pytest.mark.parametrize("params", [{"direction": "both"}, {"direction": "INCOMING"},
                                    {"status": "open"}, {"status": "Paid"}])
def test_get_requests_bad_filters(w, params):
    assert_error(w.api.requests(w.tok["ada"], **params), 422, "validation_failed")


@pytest.mark.obl("S1-131")
@pytest.mark.decision("D-13")
def test_get_requests_empty_filter(w):
    assert_error(w.api.requests(w.tok["ada"], status=""), 422, "validation_failed")


def _pagination(w, lister, key, n_items, make):
    tok = w.tok["ada"]
    for i in range(n_items):
        make(i)
    r = lister(tok, limit=3, offset=0)
    assert r.status == 200 and len(r.json[key]) == 3 and r.json["has_more"] is True, r
    total_n = len(lister(tok, limit=200).json[key])
    r = lister(tok, limit=3, offset=total_n - 3)
    assert len(r.json[key]) == 3 and r.json["has_more"] is False, r
    r = lister(tok, limit=200, offset=total_n)
    assert r.json[key] == [] and r.json["has_more"] is False, r
    r = lister(tok, limit=200, offset=total_n + 50)
    assert r.status == 200 and r.json[key] == [] and r.json["has_more"] is False, r
    r = lister(tok, limit="01")
    assert r.status == 200 and len(r.json[key]) == 1, r
    r = lister(tok)
    assert len(r.json[key]) == min(50, total_n)
    for bad in [{"limit": "0"}, {"limit": "201"}, {"limit": "-1"}, {"limit": "1.0"},
                {"limit": "1e2"}, {"limit": "+4"}, {"limit": " 1"}, {"limit": "abc"},
                {"offset": "-1"}, {"offset": "1e1"}, {"offset": "4.0"}, {"offset": "+4"},
                {"limit": ""}]:
        assert_error(lister(tok, **bad), 422, "validation_failed")
    assert lister(tok, limit="200").status == 200


@pytest.mark.obl("S1-132", "S1-056", "S1-057")
def test_requests_pagination(w):
    _pagination(w, w.api.requests, "requests", 55,
                lambda i: w.api.request(w.tok["ada"], "bob", i + 1))


@pytest.mark.obl("S1-150", "S1-056", "S1-057")
def test_activity_pagination(w):
    _pagination(w, w.api.activity, "payments", 55,
                lambda i: w.api.pay(w.tok["ada"], "dee", 1))

"""§4 amounts, §5 validation, §8 POST /payments."""
import pytest

from advlib import World, assert_error, assert_ts, fixture, new_key, user

PAYMENT_KEYS = {"payment_id", "from_user_id", "from_handle", "to_user_id",
                "to_handle", "amount", "currency", "note", "visibility",
                "request_id", "settlement_id", "created_at"}


@pytest.mark.obl("S1-091", "S1-035", "S1-199")
def test_payment_shape_and_defaults(w):
    r = w.api.pay(w.tok["ada"], "bob", 1500)
    assert r.status == 201, r
    p = r.json
    assert set(p) >= PAYMENT_KEYS, set(PAYMENT_KEYS) - set(p)
    assert p["from_user_id"] == "u_ada" and p["from_handle"] == "ada"
    assert p["to_user_id"] == "u_bob" and p["to_handle"] == "bob"
    assert p["amount"] == 1500 and p["currency"] == "EUR"
    assert p["note"] == "" and p["visibility"] == "public"
    assert p["request_id"] is None and p["settlement_id"] is None
    assert_ts(p["created_at"])
    assert w.bal("ada") == 8500 and w.bal("bob") == 4000


@pytest.mark.obl("S1-092", "S1-097")
def test_insufficient_funds_leaves_no_trace(w):
    before = w.api.activity(w.tok["bob"]).json["payments"]
    assert_error(w.api.pay(w.tok["bob"], "ada", 2501), 409, "insufficient_funds")
    assert w.bal("bob") == 2500 and w.bal("ada") == 10000
    assert w.api.activity(w.tok["bob"]).json["payments"] == before


@pytest.mark.obl("S1-092")
@pytest.mark.decision("D-16")
def test_pay_exact_balance(w):
    assert w.api.pay(w.tok["bob"], "ada", 2500).status == 201
    assert w.bal("bob") == 0


@pytest.mark.obl("S1-093", "S1-031", "S1-055")
@pytest.mark.parametrize("raw_amount", ["0", "-1", "1000000001", "1.5", "1000.5",
                                        "\"100\"", "true", "false", "null", "[]",
                                        "{}", "-0", "0.0", "1e10", "1.0000000001e9"])
def test_invalid_amount_is_422(w, raw_amount):
    raw = '{"to_handle":"bob","amount":%s}' % raw_amount
    r = w.api.call("POST", "/payments", raw=raw, token=w.tok["ada"], key=new_key())
    assert_error(r, 422, "validation_failed")
    assert w.bal("ada") == 10000


@pytest.mark.obl("S1-093", "S1-031")
@pytest.mark.parametrize("raw_amount,value", [("1", 1), ("1000", 1000), ("1000.0", 1000),
                                              ("1e3", 1000), ("1E3", 1000), ("1.0e3", 1000),
                                              ("1000000000", 10**9), ("1e9", 10**9),
                                              ("10000000000e-1", 10**9)])
def test_integral_amount_forms_valid(api, raw_amount, value):
    w = World(api, fixture(users=[user("u_ada", "ada", 2 * 10**9), user("u_bob", "bob", 0)],
                           payments=[], requests=[], settlement_operator_ids=[]))
    raw = '{"to_handle":"bob","amount":%s}' % raw_amount
    r = api.call("POST", "/payments", raw=raw, token=w.tok["ada"], key=new_key())
    assert r.status == 201, r
    assert r.json["amount"] == value and isinstance(r.json["amount"], int)
    assert w.bal("bob") == value


@pytest.mark.obl("S1-094")
def test_self_payment(w):
    assert_error(w.api.pay(w.tok["ada"], "ada", 1), 422, "self_payment")


@pytest.mark.obl("S1-096")
@pytest.mark.parametrize("h", ["nobody", "Bob", "", "bob "])
def test_unknown_handle(w, h):
    assert_error(w.api.pay(w.tok["ada"], h, 1), 404, "not_found")


@pytest.mark.obl("S1-095")
def test_note_length_boundary_ascii(w):
    assert w.api.pay(w.tok["ada"], "bob", 1, note="x" * 200).status == 201
    assert_error(w.api.pay(w.tok["ada"], "bob", 1, note="x" * 201), 422, "validation_failed")


@pytest.mark.obl("S1-095")
@pytest.mark.decision("D-07")
def test_note_length_counts_code_points(w):
    emoji = "\U0001F600"  # 1 code point, 2 UTF-16 units, 4 UTF-8 bytes
    r = w.api.pay(w.tok["ada"], "bob", 1, note=emoji * 200)
    assert r.status == 201, r
    assert r.json["note"] == emoji * 200
    assert_error(w.api.pay(w.tok["ada"], "bob", 1, note=emoji * 201), 422, "validation_failed")


@pytest.mark.obl("S1-095", "S1-055")
@pytest.mark.parametrize("vis", ["PUBLIC", "", "friends", None, 1, True, ["public"]])
def test_bad_visibility(w, vis):
    assert_error(w.api.pay(w.tok["ada"], "bob", 1, visibility=vis), 422, "validation_failed")


@pytest.mark.obl("S1-055")
@pytest.mark.parametrize("note", [None, 5, True, ["x"], {"a": 1}])
def test_non_string_note_is_422(w, note):
    assert_error(w.api.pay(w.tok["ada"], "bob", 1, note=note), 422, "validation_failed")


@pytest.mark.obl("S1-051")
@pytest.mark.parametrize("to", [5, None, ["bob"], {"h": "bob"}, True])
def test_wrong_type_handle_is_400(w, to):
    r = w.api.call("POST", "/payments", {"to_handle": to, "amount": 1},
                   token=w.tok["ada"], key=new_key())
    assert_error(r, 400, "malformed_request")


@pytest.mark.obl("S1-054")
def test_missing_required_fields(w):
    r = w.api.call("POST", "/payments", {"amount": 1}, token=w.tok["ada"], key=new_key())
    assert_error(r, 422, "validation_failed")
    r = w.api.call("POST", "/payments", {"to_handle": "bob"}, token=w.tok["ada"], key=new_key())
    assert_error(r, 422, "validation_failed")


@pytest.mark.obl("S1-051")
@pytest.mark.parametrize("raw", ["", "{", "[]", "\"str\"", "42", "null",
                                 "{\"to_handle\":\"bob\",\"amount\":1} trailing"])
def test_malformed_body(w, raw):
    r = w.api.call("POST", "/payments", raw=raw, token=w.tok["ada"], key=new_key())
    assert_error(r, 400, "malformed_request")


@pytest.mark.obl("S1-098")
@pytest.mark.parametrize("note", ["  padded  ", "café", "café", "\U0001F468‍\U0001F469‍\U0001F467",
                                  "<b>&amp;</b>", "line\nbreak\ttab", "quote\"back\\slash",
                                  "‮rtl"])
def test_note_round_trip_verbatim(w, note):
    r = w.api.pay(w.tok["ada"], "bob", 1, note=note)
    assert r.status == 201, r
    assert r.json["note"] == note
    feed = w.api.activity(w.tok["bob"], limit=1).json["payments"][0]
    assert feed["note"] == note
    assert feed["note"].encode("utf-8") == note.encode("utf-8")


@pytest.mark.obl("S1-098")
@pytest.mark.decision("D-29")
def test_note_nul_round_trip(w):
    r = w.api.pay(w.tok["ada"], "bob", 1, note="a\u0000b")
    assert r.status == 201, r
    assert r.json["note"] == "a\u0000b"


@pytest.mark.obl("S1-043")
def test_exact_arithmetic_near_2_53(api):
    big = 2**53 - 1 - 10**9
    w = World(api, fixture(users=[user("u_a", "a", big), user("u_b", "b", 10**9)],
                           payments=[], requests=[], settlement_operator_ids=[]))
    assert w.bal("a") == big
    r = api.pay(w.tok["b"], "a", 10**9)
    assert r.status == 201, r
    assert w.bal("a") == 2**53 - 1 and w.bal("b") == 0
    r = api.pay(w.tok["a"], "b", 10**9)
    assert w.bal("a") == big and w.bal("b") == 10**9


@pytest.mark.obl("S1-043")
@pytest.mark.parametrize("cur,mu", [("JPY", 0), ("BHD", 3)])
def test_minor_units_amounts_unchanged(api, cur, mu):
    w = World(api, fixture(currency=cur, minor_units=mu))
    r = api.pay(w.tok["ada"], "bob", 1)
    assert r.status == 201 and r.json["amount"] == 1
    assert w.bal("ada") == 9999 and w.bal("bob") == 2501

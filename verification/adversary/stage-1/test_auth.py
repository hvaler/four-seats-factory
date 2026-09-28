"""§6 authentication."""
import pytest

from advlib import NO_BODY, PASSWORD, World, assert_error, fixture, new_key


def signup(api, email, password=PASSWORD, name="New"):
    return api.call("POST", "/auth/signup",
                    {"email": email, "password": password, "display_name": name})


@pytest.mark.obl("S1-060", "S1-034", "S1-033")
def test_signup_derives_handle_and_zero_balance(w):
    r = signup(w.api, "Ann.Lee+x@example.com", name="Ann")
    assert r.status == 201, r
    assert set(r.json) >= {"user_id", "display_name", "token"}
    assert r.json["display_name"] == "Ann"
    me = w.api.me(r.json["token"])
    assert me["handle"] == "ann_lee_x" and me["balance"] == 0
    assert me["user_id"] == r.json["user_id"]
    # can receive and be asked immediately
    assert w.api.pay(w.tok["ada"], "ann_lee_x", 5).status == 201
    assert w.api.request(w.tok["ada"], "ann_lee_x", 5).status == 201
    assert w.api.balance(r.json["token"]) == 5


@pytest.mark.obl("S1-033")
def test_handle_truncated_to_20(w):
    r = signup(w.api, "abcdefghijklmnopqrstuvwxyz@example.com")
    assert r.status == 201, r
    assert w.api.me(r.json["token"])["handle"] == "abcdefghijklmnopqrst"


@pytest.mark.obl("S1-033")
@pytest.mark.decision("D-22")
def test_handle_derivation_non_ascii_per_code_point(w):
    r = signup(w.api, "Zoë.K@example.com")
    assert r.status == 201, r
    assert w.api.me(r.json["token"])["handle"] == "zo__k"


@pytest.mark.obl("S1-061", "S1-068")
def test_login_multiple_sessions(w):
    t1 = w.api.login("ada@example.com")
    t2 = w.api.login("ada@example.com")
    assert w.api.me(t1)["handle"] == "ada" and w.api.me(t2)["handle"] == "ada"
    assert w.api.me(w.tok["ada"])["handle"] == "ada"
    r = w.api.call("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD})
    assert r.json["user_id"] == "u_ada" and r.json["display_name"] == "Ada"


@pytest.mark.obl("S1-062")
def test_email_taken(w):
    assert_error(signup(w.api, "ada@example.com"), 409, "email_taken")
    assert signup(w.api, "zz@example.com").status == 201
    assert_error(signup(w.api, "zz@example.com"), 409, "email_taken")


@pytest.mark.obl("S1-062")
@pytest.mark.decision("D-08")
def test_email_case_variant_is_handle_taken(w):
    assert_error(signup(w.api, "ADA@example.com"), 409, "handle_taken")


@pytest.mark.obl("S1-066")
def test_handle_taken_creates_no_account(w):
    r = signup(w.api, "bob@other.example")
    assert_error(r, 409, "handle_taken")
    r = w.api.call("POST", "/auth/login", {"email": "bob@other.example", "password": PASSWORD})
    assert_error(r, 401, "unauthenticated")


@pytest.mark.obl("S1-063")
def test_password_length(w):
    assert_error(signup(w.api, "p7@example.com", password="1234567"), 422, "validation_failed")
    assert signup(w.api, "p8@example.com", password="12345678").status == 201


@pytest.mark.obl("S1-064")
@pytest.mark.parametrize("email", ["", "a", "a@", "@b", "plain.example.com"])
def test_email_form(w, email):
    assert_error(signup(w.api, email), 422, "validation_failed")


@pytest.mark.obl("S1-064")
@pytest.mark.decision("D-21")
@pytest.mark.parametrize("email", ["a@b@c", "a b@c.com"])
def test_email_form_decided(w, email):
    assert_error(signup(w.api, email), 422, "validation_failed")


@pytest.mark.obl("S1-051", "S1-054")
def test_signup_types_and_missing(w):
    r = w.api.call("POST", "/auth/signup", {"email": 5, "password": PASSWORD, "display_name": "x"})
    assert_error(r, 400, "malformed_request")
    r = w.api.call("POST", "/auth/signup", {"email": "m@example.com", "display_name": "x"})
    assert_error(r, 422, "validation_failed")
    r = w.api.call("POST", "/auth/signup", raw="{not json")
    assert_error(r, 400, "malformed_request")
    r = w.api.call("POST", "/auth/login", {"email": "ada@example.com"})
    assert_error(r, 422, "validation_failed")


@pytest.mark.obl("S1-065")
def test_login_failures(w):
    r = w.api.call("POST", "/auth/login", {"email": "ada@example.com", "password": "wrong pass"})
    assert_error(r, 401, "unauthenticated")
    r = w.api.call("POST", "/auth/login", {"email": "nobody@example.com", "password": PASSWORD})
    assert_error(r, 401, "unauthenticated")


AUTH_ROUTES = [
    ("GET", "/me"), ("GET", "/activity"), ("GET", "/requests"),
    ("POST", "/payments"), ("POST", "/requests"), ("POST", "/splits"),
    ("POST", "/settlements"), ("POST", "/requests/rq_1/pay"),
    ("POST", "/requests/rq_1/decline"), ("POST", "/requests/rq_1/cancel"),
    ("POST", "/requests/no_such_rq/pay"), ("POST", "/requests/no_such_rq/decline"),
    ("POST", "/requests/no_such_rq/cancel"),
]


@pytest.mark.obl("S1-053", "S1-067", "S1-016")
@pytest.mark.parametrize("method,path", AUTH_ROUTES)
# "Bearer " (trailing space) is not sendable: httpx rejects it client-side and HTTP strips
# trailing whitespace, so it is the same case as "Bearer" (test revision v2, see c1-run1).
@pytest.mark.parametrize("hdr", [None, "Bearer", "Token abc", "Basic YWRhOnB3",
                                 "Bearer not-a-real-token", "PRE-RESET"])
def test_unauthenticated(api, method, path, hdr):
    if hdr == "PRE-RESET":
        old = World(api, fixture()).tok["ada"]
        api.reset(fixture())
        hdr = f"Bearer {old}"
    else:
        api.reset(fixture())
    headers = {"Authorization": hdr} if hdr is not None else {}
    body = NO_BODY if method == "GET" else {"amount": 1}
    r = api.call(method, path, body,
                 headers={**headers, "Idempotency-Key": new_key()})
    assert_error(r, 401, "unauthenticated")


@pytest.mark.obl("S1-053")
@pytest.mark.decision("D-27")
def test_401_precedes_400_and_422(api):
    api.reset(fixture())
    r = api.call("POST", "/payments", raw="{broken")
    assert_error(r, 401, "unauthenticated")
    r = api.call("GET", "/activity", params={"limit": "0"})
    assert_error(r, 401, "unauthenticated")


@pytest.mark.obl("S1-069")
def test_export_has_no_plaintext_password(api):
    """Records only a boolean; the export body is never written anywhere."""
    fx = fixture(users=[*fixture()["users"],
                        {"id": "u_pw", "email": "pw@example.com",
                         "password": "Zq7-unique-plaintext-9Xk", "display_name": "P",
                         "handle": "pw", "balance": 0}])
    api.reset(fx)
    api.call("POST", "/auth/signup", {"email": "sgpw@example.com",
                                      "password": "Wm4-another-plain-2Lp",
                                      "display_name": "S"})
    r = api.call("GET", "/_test/export")
    assert r.status == 200
    leaked = [s for s in ("Zq7-unique-plaintext-9Xk", "Wm4-another-plain-2Lp", "correct horse")
              if s in r.text]
    assert leaked == [], f"plaintext password found in export: {len(leaked)} of 3 probes"

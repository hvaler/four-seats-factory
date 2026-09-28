"""Black-box HTTP helpers for the adversary stage-1 suite.

Derived from pocketful/spec/stage-1.md only. Nothing here reads the product's
source, the harness, or the shipped public tests.
"""
import copy
import json
import os
import re
import uuid

import httpx

NO_BODY = object()

RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

PASSWORD = "correct horse"


def base_url(var="ADV_BASE_URL"):
    url = os.environ.get(var)
    if not url:
        raise RuntimeError(f"{var} is not set")
    return url.rstrip("/")


class Resp:
    def __init__(self, r: httpx.Response):
        self.status = r.status_code
        self.headers = r.headers
        self.text = r.text
        self.raw = r.content
        try:
            self.json = r.json() if r.content else None
        except ValueError:
            self.json = None

    @property
    def code(self):
        try:
            return self.json["error"]["code"]
        except (TypeError, KeyError):
            return None

    def __repr__(self):
        # Never echo credentials or export snapshots into logs (S1-181).
        if isinstance(self.json, dict) and ("token" in self.json or "state" in self.json):
            shown = {k: ("<redacted>" if k in ("token", "state") else v)
                     for k, v in self.json.items()}
            return f"<Resp {self.status} {json.dumps(shown)[:300]!r}>"
        return f"<Resp {self.status} {self.text[:300]!r}>"


class Api:
    def __init__(self, base=None, timeout=20.0):
        self.base = base or base_url()
        self.client = httpx.Client(base_url=self.base, timeout=timeout)

    def close(self):
        self.client.close()

    def call(self, method, path, body=NO_BODY, *, raw=None, token=None,
             key=None, headers=None, params=None):
        h = {}
        if token is not None:
            h["Authorization"] = f"Bearer {token}"
        if key is not None:
            h["Idempotency-Key"] = key
        content = None
        if raw is not None:
            content = raw.encode("utf-8") if isinstance(raw, str) else raw
            h["Content-Type"] = "application/json"
        elif body is not NO_BODY:
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h["Content-Type"] = "application/json"
        if headers:
            h.update(headers)
        r = self.client.request(method, path, content=content, headers=h,
                                params=params)
        return Resp(r)

    # --- test control -------------------------------------------------
    def reset(self, fixture):
        r = self.call("POST", "/_test/reset", fixture)
        assert r.status == 204, r
        return r

    def login(self, email, password=PASSWORD):
        r = self.call("POST", "/auth/login",
                      {"email": email, "password": password})
        assert r.status == 200, r
        return r.json["token"]

    def me(self, token):
        r = self.call("GET", "/me", token=token)
        assert r.status == 200, r
        return r.json

    def balance(self, token):
        return self.me(token)["balance"]

    def pay(self, token, to, amount, key=None, **extra):
        body = {"to_handle": to, "amount": amount, **extra}
        return self.call("POST", "/payments", body, token=token,
                         key=key or new_key())

    def request(self, token, payer, amount, key=None, **extra):
        body = {"payer_handle": payer, "amount": amount, **extra}
        return self.call("POST", "/requests", body, token=token,
                         key=key or new_key())

    def pay_request(self, token, rid, body=None, key=None):
        return self.call("POST", f"/requests/{rid}/pay",
                         {} if body is None else body, token=token,
                         key=key or new_key())

    def activity(self, token, **params):
        return self.call("GET", "/activity", token=token, params=params)

    def requests(self, token, **params):
        return self.call("GET", "/requests", token=token, params=params)


def new_key():
    return "adv-" + uuid.uuid4().hex


def user(uid, handle, balance, email=None, name=None):
    return {"id": uid, "email": email or f"{handle}@example.com",
            "password": PASSWORD, "display_name": name or handle.title(),
            "handle": handle, "balance": balance}


BASE_FIXTURE = {
    "currency": "EUR",
    "minor_units": 2,
    "users": [
        user("u_ada", "ada", 10000),
        user("u_bob", "bob", 2500),
        user("u_cy", "cy", 0),
        user("u_dee", "dee", 5000),
        user("u_op", "op", 0),
    ],
    "payments": [
        {"id": "p_1", "from_user_id": "u_ada", "to_user_id": "u_bob",
         "amount": 500, "note": "coffee", "visibility": "public"},
    ],
    "requests": [
        {"id": "rq_1", "requester_id": "u_bob", "payer_id": "u_ada",
         "amount": 1200, "note": "taxi", "status": "pending"},
    ],
    "settlement_operator_ids": ["u_op"],
}


def fixture(**overrides):
    f = copy.deepcopy(BASE_FIXTURE)
    f.update(copy.deepcopy(overrides))
    return f


def total(fx):
    return sum(u["balance"] for u in fx["users"])


class World:
    """A reset service plus a token per seeded user."""

    def __init__(self, api, fx):
        self.api = api
        self.fx = fx
        api.reset(fx)
        self.tok = {u["handle"]: api.login(u["email"], u["password"])
                    for u in fx["users"]}

    def bal(self, handle):
        return self.api.balance(self.tok[handle])

    def balances(self):
        return {h: self.bal(h) for h in self.tok}

    def sum(self):
        return sum(self.balances().values())


def assert_error(r, status, code=None):
    assert r.status == status, r
    assert isinstance(r.json, dict) and isinstance(r.json.get("error"), dict), r
    assert isinstance(r.json["error"].get("code"), str), r
    assert isinstance(r.json["error"].get("message"), str), r
    if code is not None:
        assert r.json["error"]["code"] == code, r


def assert_ts(v):
    assert isinstance(v, str) and RFC3339.match(v), v


def assert_id(v):
    assert isinstance(v, str) and 1 <= len(v) <= 64, v

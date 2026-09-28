"""Stage-2 helpers on top of the stage-1 advlib (imported by path, unchanged)."""
import copy
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage-1"))
from advlib import (NO_BODY, PASSWORD, Api, Resp, World, assert_error, assert_ts,  # noqa: E402,F401
                    fixture, new_key, total, user)


def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def hours(h):
    return iso(datetime.now(timezone.utc) + timedelta(hours=h))


def auth_rec(aid, frm, to, amount, status="open", expires_h=2, note="", visibility="public", **extra):
    return {"id": aid, "from_user_id": frm, "to_user_id": to, "amount": amount, "note": note,
            "visibility": visibility, "status": status, "expires_at": hours(expires_h), **extra}


def fx2(**overrides):
    f = fixture()
    f["authorization_ttl_seconds"] = 600
    f["authorizations"] = []
    f.update(copy.deepcopy(overrides))
    return f


class W2(World):
    def me(self, h):
        return self.api.me(self.tok[h])

    def avail(self, h):
        return self.me(h)["available"]

    def held(self, h):
        return self.me(h)["held"]

    def totals(self):
        return sum(self.me(h)["total"] for h in self.tok)

    def authorize(self, h, to, amount, key=None, **extra):
        return self.api.call("POST", "/authorizations", {"to_handle": to, "amount": amount, **extra},
                             token=self.tok[h], key=key or new_key())

    def capture(self, h, aid, body=None, key=None):
        return self.api.call("POST", f"/authorizations/{aid}/capture", {} if body is None else body,
                             token=self.tok[h], key=key or new_key())

    def void(self, h, aid, **kw):
        return self.api.call("POST", f"/authorizations/{aid}/void", token=self.tok[h], **kw)

    def auths(self, h, **params):
        return self.api.call("GET", "/authorizations", token=self.tok[h], params=params)


def fmt(minor, mu, cur):
    minor = int(minor)
    if mu == 0:
        return f"{minor} {cur}"
    s = str(minor).rjust(mu + 1, "0")
    return f"{s[:-mu]}.{s[-mu:]} {cur}"

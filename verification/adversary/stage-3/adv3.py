"""Stage-3 helpers and an independent reference ledger (R3-15).

The ledger uses only server-returned timestamps (created_at / effective_at / recorded_at of each
revision) plus the documented rules; it never reads the server's historical money fields.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage-2"))
from adv2 import (NO_BODY, PASSWORD, Api, W2, assert_error, assert_ts, auth_rec, fixture, fmt,  # noqa: F401,E402
                  fx2, new_key, parse_ts, total, user)


def iso_ms(dt):
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+00:00"


def plus_ms(s, ms):
    return iso_ms(parse_ts(s) + timedelta(milliseconds=ms))


def tick(ms=15):
    time.sleep(ms / 1000)


def fx3(**kw):
    """A fixture with no seeded payments/requests so opening balance == seeded balance."""
    base = dict(payments=[], requests=[], authorizations=[])
    base.update(kw)
    return fx2(**base)


class W3(W2):
    def me_at(self, h, **params):
        return self.api.call("GET", "/me", token=self.tok[h], params=params)

    def statement(self, h, **params):
        return self.api.call("GET", "/statement", token=self.tok[h], params=params)

    def correct(self, h, pid, expected_revision, amount, effective_at, reason="fix", key=None, **extra):
        body = {"expected_revision": expected_revision, "amount": amount, "effective_at": effective_at,
                "reason": reason, **extra}
        return self.api.call("POST", f"/payments/{pid}/corrections", body, token=self.tok[h], key=key or new_key())

    def revisions(self, h, pid):
        return self.api.call("GET", f"/payments/{pid}/revisions", token=self.tok[h])

    def full_statement(self, h, **params):
        out, off, first = [], 0, None
        while True:
            r = self.statement(h, limit=200, offset=off, **params)
            assert r.status == 200, r
            first = first or r.json
            out += r.json["entries"]
            if not r.json["has_more"]:
                return first, out
            off += 200


class Ledger:
    """Reference model: opening balances + payments with revision histories."""

    def __init__(self, opening):
        self.opening = dict(opening)      # handle -> minor units
        self.pays = {}                    # payment_id -> {from, to, revs:[(rev, amount, eff, rec)]}

    def add_payment(self, p):
        self.pays[p["payment_id"]] = {"from": p["from_handle"], "to": p["to_handle"],
                                     "revs": [(1, p["amount"], parse_ts(p["created_at"]), parse_ts(p["created_at"]))]}

    def add_revision(self, c):
        self.pays[c["payment_id"]]["revs"].append(
            (c["revision"], c["amount"], parse_ts(c["effective_at"]), parse_ts(c["recorded_at"])))

    def selected(self, pid, known_at=None):
        revs = self.pays[pid]["revs"]
        if known_at is not None:
            revs = [r for r in revs if r[3] <= known_at]
        return revs[-1] if revs else None

    def balance(self, h, as_of=None, known_at=None):
        b = self.opening[h]
        for pid, p in self.pays.items():
            r = self.selected(pid, known_at)
            if r is None or (as_of is not None and r[2] > as_of):
                continue
            if p["from"] == h:
                b -= r[1]
            if p["to"] == h:
                b += r[1]
        return b

    def entries(self, h, frm=None, to=None, known_at=None):
        """Statement entries [(effective_at, pid, delta, revision)] in the half-open window."""
        out = []
        for pid, p in self.pays.items():
            if h not in (p["from"], p["to"]):
                continue
            r = self.selected(pid, known_at)
            if r is None:
                continue
            if (frm is not None and r[2] < frm) or (to is not None and r[2] >= to):
                continue
            d = (r[1] if p["to"] == h else 0) - (r[1] if p["from"] == h else 0)
            out.append((r[2], pid, d, r[0]))
        out.sort(key=lambda e: (e[0], e[1].encode("utf-8")))
        return out

    def balance_before(self, h, t, known_at=None):
        """Balance immediately before instant t (strictly earlier effects only)."""
        b = self.opening[h]
        for pid, p in self.pays.items():
            r = self.selected(pid, known_at)
            if r is None or (t is not None and r[2] >= t):
                continue
            if p["from"] == h:
                b -= r[1]
            if p["to"] == h:
                b += r[1]
        return b

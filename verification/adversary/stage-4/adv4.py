"""Stage-4 helpers on top of stage-3 (imported by path, unchanged)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage-3"))
from adv3 import (NO_BODY, PASSWORD, Api, Ledger, W3, assert_error, assert_ts, auth_rec, fixture, fx2, fx3,  # noqa: F401,E402
                  iso_ms, new_key, parse_ts, plus_ms, tick, total, user)


class W4(W3):
    def refund(self, h, pid, amount, key=None, raw=None):
        if raw is not None:
            return self.api.call("POST", f"/payments/{pid}/refunds", raw=raw, token=self.tok[h], key=key or new_key())
        return self.api.call("POST", f"/payments/{pid}/refunds", {"amount": amount}, token=self.tok[h],
                             key=key or new_key())

    def batch(self, items, h="op", key=None):
        return self.api.call("POST", "/correction-batches", {"corrections": items}, token=self.tok[h],
                             key=key or new_key())

    def settle(self, transfers, key=None):
        return self.api.call("POST", "/settlements", {"transfers": transfers}, token=self.tok["op"],
                             key=key or new_key())


def item(p, amount, eff=None, rev=1, reason="batch fix", **extra):
    return {"payment_id": p["payment_id"] if isinstance(p, dict) else p, "expected_revision": rev, "amount": amount,
            "effective_at": eff or (p["created_at"] if isinstance(p, dict) else None), "reason": reason, **extra}

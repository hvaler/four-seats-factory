"""Repro candidate for S3-057/S3-081: known_at before a void, as_of beyond expires_at.
Usage: ADV_BASE_URL=http://127.0.0.1:<port> python repro_void_known_at.py"""
import sys, time
sys.path.insert(0, "/mnt/c/nexus/dev/band-kit/wt/adversary/verification/adversary/stage-3")
from datetime import datetime, timezone
from adv3 import Api, W3, fx3, iso_ms, plus_ms

api = Api(); w = W3(api, fx3())
a = w.authorize("ada", "bob", 1000).json
time.sleep(0.03); before_void = iso_ms(datetime.now(timezone.utc)); time.sleep(0.03)
v = w.void("ada", a["authorization_id"]).json
print("created_at", a["created_at"], "expires_at", a["expires_at"], "before_void", before_void, "closed_at", v["closed_at"])
for label, as_of, known in [("A: as_of=exp-1ms known<void", plus_ms(a["expires_at"], -1), before_void),
                            ("B: as_of=exp+1ms known<void", plus_ms(a["expires_at"], 1), before_void),
                            ("C: as_of=2099 known<void", "2099-01-01T00:00:00.000+00:00", before_void),
                            ("D: as_of=2099 known=now", "2099-01-01T00:00:00.000+00:00", iso_ms(datetime.now(timezone.utc))),
                            ("E: as_of=2099 no known_at", "2099-01-01T00:00:00.000+00:00", None)]:
    params = {"as_of": as_of}
    if known:
        params["known_at"] = known
    m = w.me_at("ada", **params).json
    print(label, {k: m.get(k) for k in ("total", "held", "available", "as_of", "known_at")})
# a hold that is NOT voided, as a control
b = w.authorize("ada", "cy", 500).json
m = w.me_at("ada", as_of=plus_ms(b["expires_at"], 1)).json
print("F: open hold, as_of=exp+1ms", {k: m.get(k) for k in ("total", "held", "available")})
m = w.me_at("ada", as_of=plus_ms(b["expires_at"], 1), known_at=iso_ms(datetime.now(timezone.utc))).json
print("G: open hold, as_of=exp+1ms, known_at=now", {k: m.get(k) for k in ("total", "held", "available")})

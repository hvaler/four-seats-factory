"""Check for the analyst (0797c462): do D3-11 historical_overdraft boundaries honour a hold's expiry at expires_at?
dee (5000) authorizes 5000 with TTL 2 s at t2; it expires at t2+2 s; dee then pays cy 5000 at t3.
Moving that payment's effective_at inside the hold window must be 409 historical_overdraft;
moving it after expires_at (but before t3) must be 201."""
import sys, time
sys.path.insert(0, "/mnt/c/nexus/dev/band-kit/wt/adversary/verification/adversary/stage-3")
from adv3 import Api, W3, fx3, plus_ms
api = Api(); w = W3(api, fx3(authorization_ttl_seconds=2))
a = w.authorize("dee", "bob", 5000).json
time.sleep(2.6)
p = w.api.pay(w.tok["dee"], "cy", 5000).json
print("hold created", a["created_at"], "expires", a["expires_at"], "payment", p["created_at"])
inside = plus_ms(a["created_at"], 1000)
after = plus_ms(a["expires_at"], 300)
r1 = w.correct("dee", p["payment_id"], 1, 5000, inside, reason="inside hold window")
print("effective inside hold window ->", r1.status, r1.code, "(expected 409 historical_overdraft)")
r2 = w.correct("dee", p["payment_id"], 1, 5000, after, reason="after expiry")
print("effective after expires_at ->", r2.status, r2.code, "(expected 201)")
print("dee now", w.me("dee"), "revisions", len(w.revisions("dee", p["payment_id"]).json["revisions"]))

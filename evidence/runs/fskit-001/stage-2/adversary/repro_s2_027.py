"""Minimal repro for finding F2-01 (S2-027 'input kept' after a refused capture).
Usage: ADV_BASE_URL=http://127.0.0.1:<port> python repro_s2_027.py"""
import os, sys
sys.path.insert(0, "/mnt/c/nexus/dev/band-kit/wt/adversary/verification/adversary/stage-2")
from playwright.sync_api import sync_playwright, expect
from adv2 import Api, W2, fx2
from ui2 import login, goto, tid, fill_amount

api = Api()
w = W2(api, fx2())
aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 900})
    login(pg, api.base, "bob@example.com"); goto(pg, api.base, "/authorizations")
    inp = tid(pg, f"authorization-capture-amount-{aid}")
    print("prefill:", repr(inp.input_value()))
    fill_amount(pg, f"authorization-capture-amount-{aid}", "25.00")
    print("typed:", repr(inp.input_value()))
    tid(pg, f"authorization-capture-{aid}").click()
    expect(tid(pg, "authorization-error")).to_be_visible(timeout=10000)
    print("error text:", repr(tid(pg, "authorization-error").inner_text()))
    print("after refusal:", repr(inp.input_value()))
    print("status:", tid(pg, f"authorization-item-{aid}").get_attribute("data-status"),
          "held:", w.held("ada"), "bob total:", w.me("bob")["total"])
    b.close()

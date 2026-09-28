"""Stage-2 suite v2 additions: gaps named in bundle c1 (db1da6a4)."""
import pytest
from playwright.sync_api import expect, sync_playwright

from adv2 import W2, fx2, new_key, user
from ui2 import T, WIDTHS, fill_amount, goto, login, tid

pytestmark = pytest.mark.ui
XSS_NAME = '<img src=x onerror="window.__xss=9">Eve'


@pytest.fixture(scope="module")
def pw():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(params=WIDTHS, ids=lambda w: f"w{w}")
def page(pw, request):
    ctx = pw.new_context(viewport={"width": request.param, "height": 900})
    pg = ctx.new_page()
    pg.dialogs = []
    pg.on("dialog", lambda d: (pg.dialogs.append(d.message), d.dismiss()))
    yield pg
    ctx.close()


@pytest.mark.obl("S2-035", "S2-012")
def test_display_name_renders_as_text(api, page):
    fx = fx2()
    fx["users"].append(user("u_eve", "eve", 100, name=XSS_NAME))
    w = W2(api, fx)
    api.pay(w.tok["eve"], "ada", 1, note="from eve")
    login(page, api.base, "eve@example.com")
    for r in ["/", "/requests", "/split", "/authorizations"]:
        goto(page, api.base, r)
        assert XSS_NAME in tid(page, "current-user").inner_text(), r
    assert page.evaluate("() => window.__xss === undefined"), "a display name was rendered as HTML"
    assert page.dialogs == [] and page.locator('img[src="x"]').count() == 0


@pytest.mark.obl("S2-021", "S2-026")
def test_latest_refresh_wins_on_authorizations(api, page):
    w = W2(api, fx2())
    login(page, api.base, "ada@example.com")
    goto(page, api.base, "/authorizations")
    held, mode = [], {"hold": False}

    def handler(route):
        if mode["hold"] and route.request.method == "GET" and route.request.resource_type in ("fetch", "xhr"):
            held.append((route, route.fetch()))
        else:
            route.continue_()

    page.route("**/*", handler)
    mode["hold"] = True
    refresh = tid(page, "wallet-refresh")
    if refresh.count() == 0:
        pytest.skip("no wallet-refresh on /authorizations (the spec requires it on / only)")
    refresh.click()
    page.wait_for_timeout(700)
    mode["hold"] = False
    w.authorize("ada", "bob", 1500)  # another client places a hold
    refresh.click()
    expect(tid(page, "wallet-held")).to_have_attribute("data-amount", "1500", timeout=T)
    for route, resp in held:
        try:
            route.fulfill(response=resp)
        except Exception:
            pass
    page.wait_for_timeout(1500)
    expect(tid(page, "wallet-available")).to_have_attribute("data-amount", "8500")
    expect(tid(page, "wallet-held")).to_have_attribute("data-amount", "1500")
    page.unroute("**/*")


@pytest.mark.obl("S2-027")
@pytest.mark.decision("D2-19")
def test_refused_capture_keeps_input_then_success_resets_prefill(api, page):
    w = W2(api, fx2())
    aid = w.authorize("ada", "bob", 2000).json["authorization_id"]
    login(page, api.base, "bob@example.com")
    goto(page, api.base, "/authorizations")
    inp = tid(page, f"authorization-capture-amount-{aid}")
    expect(inp).to_have_value("20.00", timeout=T)
    fill_amount(page, f"authorization-capture-amount-{aid}", "25.00")
    tid(page, f"authorization-capture-{aid}").click()
    expect(tid(page, "authorization-error")).to_be_visible(timeout=T)
    expect(inp).to_have_value("25.00")
    w.capture("bob", aid, {"amount": 500, "final": False}, key=new_key())  # partial capture elsewhere
    refresh = tid(page, "wallet-refresh")
    if refresh.count():
        refresh.click()
    else:
        goto(page, api.base, "/authorizations")
    page.wait_for_timeout(1000)
    assert w.held("ada") == 1500

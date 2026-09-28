"""Playwright helpers. Everything is driven by the spec's data-testid contract only."""
import os
import re

from playwright.sync_api import expect

WIDTHS = [375, 1280]
T = 10_000  # ms


def shots_dir():
    d = os.environ.get("ADV_SHOTS")
    if d:
        os.makedirs(d, exist_ok=True)
    return d


def shot(page, name):
    d = shots_dir()
    if d:
        page.screenshot(path=os.path.join(d, f"{name}.png"), full_page=True)


def tid(page, t):
    return page.get_by_test_id(t)


def goto(page, base, path):
    page.goto(base + path, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")


def login(page, base, email, password="correct horse"):
    goto(page, base, "/login")
    tid(page, "login-email").fill(email)
    tid(page, "login-password").fill(password)
    tid(page, "login-submit").click()
    expect(tid(page, "current-user")).to_be_visible(timeout=T)


def amount_of(loc):
    v = loc.get_attribute("data-amount")
    return None if v is None else int(v)


def no_hscroll(page):
    return page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth,"
                         " document.body ? document.body.scrollWidth : 0]")


def assert_no_hscroll(page, where):
    sw, iw, bw = no_hscroll(page)
    assert sw <= iw and bw <= iw, f"horizontal scroll on {where}: scrollWidth={sw}/{bw} viewport={iw}"


class NetLog:
    """Records every API write the page sends."""

    def __init__(self, page):
        self.reqs = []
        page.on("request", self._on)

    def _on(self, req):
        if req.method != "GET":
            self.reqs.append((req.method, re.sub(r"^https?://[^/]+", "", req.url), req.headers.get("idempotency-key"),
                              req.post_data))

    def writes(self, path_prefix):
        return [r for r in self.reqs if r[1].split("?")[0].startswith(path_prefix)]


def fill_amount(page, testid, text):
    loc = tid(page, testid)
    loc.fill("")
    loc.fill(text)

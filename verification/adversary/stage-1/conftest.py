import json
import os

import pytest

from advlib import Api, World, fixture

_RESULTS = []


def pytest_runtest_makereport(item, call):
    if call.when != "call" and not (call.when == "setup" and call.excinfo is not None):
        return
    obl = [a for m in item.iter_markers("obl") for a in m.args]
    dec = [a for m in item.iter_markers("decision") for a in m.args]
    outcome = "passed" if call.excinfo is None else (
        "skipped" if call.excinfo.errisinstance(pytest.skip.Exception) else "failed")
    _RESULTS.append({"test": item.nodeid, "obligations": obl, "decisions": dec,
                     "risk": item.get_closest_marker("risk") is not None,
                     "phase": call.when, "outcome": outcome,
                     "duration_s": round(call.duration, 3),
                     "error": None if call.excinfo is None else str(call.excinfo.value)[:2000]})


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("ADV_RESULTS")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_RESULTS, f, indent=1, ensure_ascii=False)


def pytest_configure(config):
    config.addinivalue_line("markers", "obl(*ids): obligation ids covered")
    config.addinivalue_line("markers", "decision(*ids): depends on analyst decision D-xx")
    config.addinivalue_line("markers", "risk: optional robustness probe, not a contract requirement")
    config.addinivalue_line("markers", "xc: needs two independent containers")


def pytest_collection_modifyitems(config, items):
    if not os.environ.get("ADV_BASE_URL_B"):
        skip = pytest.mark.skip(reason="ADV_BASE_URL_B not set (XC needs a second container)")
        for it in items:
            if "xc" in it.keywords:
                it.add_marker(skip)


@pytest.fixture
def api():
    a = Api()
    yield a
    a.close()


@pytest.fixture
def api_b():
    a = Api(os.environ["ADV_BASE_URL_B"])
    yield a
    a.close()


@pytest.fixture
def w(api):
    return World(api, fixture())

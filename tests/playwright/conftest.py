import json
import os
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

# LambdaTest browser map: browser key → (Playwright launcher attr, LT browserName capability)
# LambdaTest now requires playwright.browser.connect() (Playwright wire protocol), NOT
# connect_over_cdp() which produces "Browser.getVersion: undefined" errors.
# With connect(), use standard LambdaTest browser names (Chrome, Firefox, etc.).
# Android routes to a real LambdaTest Android device; the HE runner stays Linux.
_BROWSER_MAP = {
    "chrome":   ("chromium", "Chrome"),
    "firefox":  ("firefox",  "Firefox"),
    "edge":     ("chromium", "MicrosoftEdge"),
    "safari":   ("webkit",   "Safari"),
    "android":  ("chromium", "Chrome"),
}

# Platform overrides per browser key (defaults to "Windows 10")
_PLATFORM_MAP = {
    "safari":  "macOS Ventura",
    "android": "Android",
}

# Extra LT:Options injected only for Android real-device execution
_ANDROID_EXTRA = {
    "deviceName": "Galaxy S22",
    "osVersion":  "12",
    "isRealMobile": True,
}


def _build_name():
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"Agentic STLC #{run_number} | {today}" if run_number else f"Agentic STLC | {today}"


def _session_name(request, browser_key: str) -> str:
    scenario_marker = request.node.get_closest_marker("scenario")
    scenario_id = scenario_marker.args[0] if scenario_marker else "unknown"
    tc_id = f"TC-{scenario_id.split('-')[1]}" if "-" in scenario_id else "TC-000"
    return f"{scenario_id} | {tc_id} | {request.node.name} | {browser_key}"


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(id): scenario ID this test covers")
    config.addinivalue_line("markers", "requirement(id): requirement ID this test covers")


def _m365_login(page, url: str) -> None:
    """Navigate to the app URL and handle Microsoft 365 login if credentials are set."""
    page.goto(url)
    page.wait_for_load_state("domcontentloaded", timeout=30000)

    username = os.environ.get("M365_USERNAME", "")
    password = os.environ.get("M365_PASSWORD", "")
    if not username or not password:
        return

    email_input = page.locator("input[type='email'], input[name='loginfmt']")
    if email_input.count() > 0:
        email_input.first.fill(username)
        page.get_by_role("button", name="Next").click()
        page.wait_for_timeout(1000)

    pwd_input = page.locator("input[type='password'], input[name='passwd']")
    if pwd_input.count() > 0:
        pwd_input.first.fill(password)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_timeout(1500)

    stay_signed = page.get_by_role("button", name="Yes")
    if stay_signed.count() > 0:
        stay_signed.click()

    page.wait_for_load_state("networkidle", timeout=30000)


# Read target browsers from env — comma-separated, e.g. "chrome,firefox,safari,android".
# Falls back to single BROWSER env var (legacy), then to chrome.
def _target_browsers() -> list[str]:
    multi = os.environ.get("BROWSERS", "")
    if multi:
        return [b.strip().lower() for b in multi.split(",") if b.strip()]
    single = os.environ.get("BROWSER", "chrome").strip().lower()
    return [single]


@pytest.fixture(params=_target_browsers(), scope="function")
def page(request):
    lt_username = os.environ.get("LT_USERNAME", "")
    lt_access_key = os.environ.get("LT_ACCESS_KEY", "")
    browser_key: str = request.param
    playwright_launcher, lt_browser_name = _BROWSER_MAP.get(browser_key, ("chromium", "pw-chromium"))

    build = _build_name()
    session_name = _session_name(request, browser_key)

    # Detect Playwright version for capabilities (required by LambdaTest)
    pw_version = ""
    try:
        import subprocess as _sp
        _r = _sp.run(["playwright", "--version"], capture_output=True, text=True, check=False)
        _parts = _r.stdout.strip().split()
        pw_version = _parts[1] if len(_parts) >= 2 else ""
    except Exception:
        pass

    # Project label: prefer AGENTIC_PROJECT_NAME env var, fall back to generic label
    project_label = os.environ.get("AGENTIC_PROJECT_NAME", "Agentic STLC")

    # Local mode: if TARGET_URL is localhost or LT credentials are absent,
    # run tests directly on the HE VM browser (no LambdaTest CDP connection).
    # HyperExecute tunnel exposes the VM's localhost to LambdaTest cloud, but
    # the Playwright test itself connects via the local browser, not CDP.
    target_url = os.environ.get("TARGET_URL", "")
    local_mode = (
        not lt_username
        or not lt_access_key
        or "localhost" in target_url
        or "127.0.0.1" in target_url
    )

    platform = _PLATFORM_MAP.get(browser_key, "Windows 10")
    lt_options: dict = {
        "platform": platform,
        "build": build,
        "name": session_name,
        "project": project_label,
        "user": lt_username,
        "accessKey": lt_access_key,
        "video": True,
        "visual": True,
        "network": True,
        "console": True,
    }
    if pw_version:
        lt_options["playwrightClientVersion"] = pw_version
    if browser_key == "android":
        lt_options.update(_ANDROID_EXTRA)

    capabilities = {
        "browserName": lt_browser_name,
        "browserVersion": "latest",
        "LT:Options": lt_options,
    }
    cdp_url = (
        f"wss://cdp.lambdatest.com/playwright"
        f"?capabilities={urllib.parse.quote(json.dumps(capabilities))}"
    )

    start_time = datetime.now(timezone.utc)
    start_mono = time.monotonic()

    with sync_playwright() as p:
        launcher = getattr(p, playwright_launcher)
        if local_mode:
            # Run tests on the HE VM's local browser — no LambdaTest CDP.
            # HyperExecute tunnel still exposes localhost to LT for recording.
            browser = launcher.launch(headless=True)
        else:
            # LambdaTest requires Playwright wire-protocol connect(), not connect_over_cdp().
            browser = launcher.connect(cdp_url)
        context = browser.new_context()
        pw_page = context.new_page()

        yield pw_page

        end_mono = time.monotonic()
        end_time = datetime.now(timezone.utc)
        duration_ms = round((end_mono - start_mono) * 1000)

        scenario_marker = request.node.get_closest_marker("scenario")
        requirement_marker = request.node.get_closest_marker("requirement")
        scenario_id = scenario_marker.args[0] if scenario_marker else "unknown"
        requirement_id = requirement_marker.args[0] if requirement_marker else "unknown"

        rep = getattr(request.node, "rep_call", None)
        if rep is None:
            status = "unknown"
        elif rep.passed:
            status = "passed"
        elif rep.skipped:
            status = "skipped"
        else:
            status = "failed"

        error_message = None
        if rep and rep.failed and hasattr(rep, "longrepr"):
            error_message = str(rep.longrepr)[:500]

        try:
            pw_page.evaluate(f"() => {{ window['lambda-status'] = '{status}'; }}")
        except Exception:
            pass

        tc_id = f"TC-{scenario_id.split('-')[1]}" if "-" in scenario_id else "TC-000"

        Path("reports").mkdir(exist_ok=True)
        # Include browser in filename so multi-browser runs don't overwrite each other
        result_path = Path(f"reports/kane_result_{scenario_id}_{browser_key}.json")
        result_path.write_text(
            json.dumps(
                {
                    "requirement_id": requirement_id,
                    "scenario_id": scenario_id,
                    "test_case_id": tc_id,
                    "function_name": request.node.name,
                    "browser": browser_key,
                    "lt_browser": lt_browser_name,
                    "status": status,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration_ms": duration_ms,
                    "error_message": error_message,
                    "session_name": session_name,
                    "build": build,
                    "source": "conftest",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        pw_page.close()
        context.close()
        browser.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)

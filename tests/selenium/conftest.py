import os
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions


LT_USERNAME = os.environ.get("LT_USERNAME", "")
LT_ACCESS_KEY = os.environ.get("LT_ACCESS_KEY", "")
SELENIUM_ENDPOINT = f"https://{LT_USERNAME}:{LT_ACCESS_KEY}@hub.lambdatest.com/wd/hub"
USE_REMOTE = os.environ.get("USE_REMOTE_GRID", "").lower() in {"1", "true", "yes"}
if not os.environ.get("USE_REMOTE_GRID"):
    USE_REMOTE = bool(LT_USERNAME and LT_ACCESS_KEY)


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(id): scenario ID this test covers")
    config.addinivalue_line("markers", "requirement(id): requirement ID this test covers")


@pytest.fixture(scope="function")
def driver(request):
    if USE_REMOTE:
        options = ChromeOptions()
        options.browser_version = "latest"
        options.platform_name = os.environ.get("TARGET_OS", "Windows 10")
        options.set_capability("LT:Options", {
            "username": LT_USERNAME,
            "accessKey": LT_ACCESS_KEY,
            "build": "Agentic STLC - eCommerce Playground",
            "project": "agentic-stlc",
            "name": request.node.name,
            "video": True,
            "visual": True,
            "network": True,
            "console": True,
            "w3c": True,
        })
        browser = webdriver.Remote(
            command_executor=SELENIUM_ENDPOINT,
            options=options,
        )
    else:
        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,2200")
        browser = webdriver.Chrome(options=options)

    browser.set_page_load_timeout(30)
    browser.implicitly_wait(10)
    browser.set_window_size(1440, 2200)

    yield browser

    def fin():
        rep_call = getattr(request.node, "rep_call", None)
        if USE_REMOTE:
            status = "failed" if (rep_call and rep_call.failed) else "passed"
            browser.execute_script(f"lambda-status={status}")
        browser.quit()

    request.addfinalizer(fin)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)

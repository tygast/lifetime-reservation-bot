"""WebDriver setup and configuration."""

from __future__ import annotations

import warnings

# Suppress all warnings before importing selenium
warnings.filterwarnings("ignore")

from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.remote.webdriver import WebDriver  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402
from webdriver_manager.chrome import ChromeDriverManager  # noqa: E402


def create_driver(
    headless: bool = False,
    window_size: tuple[int, int] = (1920, 1080),
    wait_timeout: int = 30,
) -> tuple[WebDriver, WebDriverWait]:
    """Create and configure a Chrome WebDriver instance.

    Args:
        headless: If True, run browser in headless mode.
        window_size: Browser window dimensions (width, height).
        wait_timeout: Default timeout for WebDriverWait in seconds.

    Returns:
        A tuple of (WebDriver instance, WebDriverWait instance).
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")

    if headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )

    wait = WebDriverWait(driver, wait_timeout)

    return driver, wait

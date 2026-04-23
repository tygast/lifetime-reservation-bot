"""Unit tests for the webdriver module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestCreateDriver:
    """Tests for create_driver function."""

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    def test_create_driver_returns_tuple(
        self,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that create_driver returns a tuple of driver and wait."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_driver = MagicMock()
        mock_driver.capabilities = {}
        mock_chrome.return_value = mock_driver
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        driver, wait = create_driver()

        assert driver == mock_driver
        assert wait == mock_wait_instance

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    def test_create_driver_headless_mode(
        self,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that headless mode adds correct argument."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance
        mock_chrome.return_value.capabilities = {}

        create_driver(headless=True)

        calls = mock_options_instance.add_argument.call_args_list
        headless_calls = [c for c in calls if "--headless" in str(c)]
        assert len(headless_calls) == 1

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    def test_create_driver_not_headless_by_default(
        self,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that headless mode is disabled by default."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance
        mock_chrome.return_value.capabilities = {}

        create_driver(headless=False)

        calls = mock_options_instance.add_argument.call_args_list
        headless_calls = [c for c in calls if "--headless" in str(c)]
        assert len(headless_calls) == 0

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    def test_create_driver_custom_window_size(
        self,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that custom window size is applied."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance
        mock_chrome.return_value.capabilities = {}

        create_driver(window_size=(1280, 720))

        calls = mock_options_instance.add_argument.call_args_list
        size_calls = [c for c in calls if "--window-size=1280,720" in str(c)]
        assert len(size_calls) == 1

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    def test_create_driver_custom_timeout(
        self,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that custom wait timeout is applied."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_driver = MagicMock()
        mock_driver.capabilities = {}
        mock_chrome.return_value = mock_driver

        create_driver(wait_timeout=60)

        mock_wait.assert_called_once_with(mock_driver, 60)

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    def test_create_driver_uses_selenium_manager(
        self,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that Chrome is constructed without an explicit Service (Selenium Manager)."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_chrome.return_value.capabilities = {}

        create_driver()

        mock_chrome.assert_called_once()
        _, kwargs = mock_chrome.call_args
        assert "service" not in kwargs

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    def test_create_driver_adds_required_options(
        self,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that required Chrome options are always added."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance
        mock_chrome.return_value.capabilities = {}

        create_driver()

        calls = [str(c) for c in mock_options_instance.add_argument.call_args_list]
        assert any("--disable-gpu" in c for c in calls)
        assert any("--no-sandbox" in c for c in calls)

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    def test_create_driver_logs_versions(
        self,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
        capsys,
    ) -> None:
        """Test that Chrome and ChromeDriver versions are printed."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_chrome.return_value.capabilities = {
            "browserVersion": "131.0.6778.85",
            "chrome": {"chromedriverVersion": "131.0.6778.85 (abc) trunk"},
        }

        create_driver()

        captured = capsys.readouterr()
        assert "131.0.6778.85" in captured.out

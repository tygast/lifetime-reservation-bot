"""Unit tests for the webdriver module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCreateDriver:
    """Tests for create_driver function."""

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.Service")
    @patch("lifetime_bot.webdriver.driver.ChromeDriverManager")
    def test_create_driver_returns_tuple(
        self,
        mock_manager: MagicMock,
        mock_service: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that create_driver returns a tuple of driver and wait."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        driver, wait = create_driver()

        assert driver == mock_driver
        assert wait == mock_wait_instance

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    @patch("lifetime_bot.webdriver.driver.Service")
    @patch("lifetime_bot.webdriver.driver.ChromeDriverManager")
    def test_create_driver_headless_mode(
        self,
        mock_manager: MagicMock,
        mock_service: MagicMock,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that headless mode adds correct argument."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance

        create_driver(headless=True)

        # Verify headless argument was added
        calls = mock_options_instance.add_argument.call_args_list
        headless_calls = [c for c in calls if "--headless" in str(c)]
        assert len(headless_calls) == 1

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    @patch("lifetime_bot.webdriver.driver.Service")
    @patch("lifetime_bot.webdriver.driver.ChromeDriverManager")
    def test_create_driver_not_headless_by_default(
        self,
        mock_manager: MagicMock,
        mock_service: MagicMock,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that headless mode is disabled by default."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance

        create_driver(headless=False)

        # Verify headless argument was NOT added
        calls = mock_options_instance.add_argument.call_args_list
        headless_calls = [c for c in calls if "--headless" in str(c)]
        assert len(headless_calls) == 0

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    @patch("lifetime_bot.webdriver.driver.Service")
    @patch("lifetime_bot.webdriver.driver.ChromeDriverManager")
    def test_create_driver_custom_window_size(
        self,
        mock_manager: MagicMock,
        mock_service: MagicMock,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that custom window size is applied."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance

        create_driver(window_size=(1280, 720))

        # Verify window size argument was added
        calls = mock_options_instance.add_argument.call_args_list
        size_calls = [c for c in calls if "--window-size=1280,720" in str(c)]
        assert len(size_calls) == 1

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.Service")
    @patch("lifetime_bot.webdriver.driver.ChromeDriverManager")
    def test_create_driver_custom_timeout(
        self,
        mock_manager: MagicMock,
        mock_service: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that custom wait timeout is applied."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        create_driver(wait_timeout=60)

        # Verify WebDriverWait was created with correct timeout
        mock_wait.assert_called_once_with(mock_driver, 60)

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.Service")
    @patch("lifetime_bot.webdriver.driver.ChromeDriverManager")
    def test_create_driver_uses_chrome_driver_manager(
        self,
        mock_manager: MagicMock,
        mock_service: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that ChromeDriverManager is used to install driver."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_manager_instance = MagicMock()
        mock_manager.return_value = mock_manager_instance
        mock_manager_instance.install.return_value = "/path/to/chromedriver"

        create_driver()

        mock_manager.assert_called_once()
        mock_manager_instance.install.assert_called_once()
        mock_service.assert_called_once_with("/path/to/chromedriver")

    @patch("lifetime_bot.webdriver.driver.WebDriverWait")
    @patch("lifetime_bot.webdriver.driver.webdriver.Chrome")
    @patch("lifetime_bot.webdriver.driver.webdriver.ChromeOptions")
    @patch("lifetime_bot.webdriver.driver.Service")
    @patch("lifetime_bot.webdriver.driver.ChromeDriverManager")
    def test_create_driver_adds_required_options(
        self,
        mock_manager: MagicMock,
        mock_service: MagicMock,
        mock_options: MagicMock,
        mock_chrome: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        """Test that required Chrome options are always added."""
        from lifetime_bot.webdriver.driver import create_driver

        mock_options_instance = MagicMock()
        mock_options.return_value = mock_options_instance

        create_driver()

        # Verify required arguments are added
        calls = [str(c) for c in mock_options_instance.add_argument.call_args_list]
        assert any("--disable-gpu" in c for c in calls)
        assert any("--no-sandbox" in c for c in calls)

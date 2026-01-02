"""Main bot class for Life Time Fitness class reservations."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from lifetime_bot.config import BotConfig
from lifetime_bot.notifications import EmailNotificationService, SMSNotificationService
from lifetime_bot.utils.timing import get_target_date
from lifetime_bot.webdriver import create_driver

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


class LifetimeReservationBot:
    """Automated bot for reserving classes at Life Time Fitness."""

    def __init__(self, config: BotConfig | None = None) -> None:
        """Initialize the bot with configuration.

        Args:
            config: Bot configuration. If None, loads from environment variables.
        """
        self.config = config or BotConfig.from_env()
        self._setup_notifications()
        self._setup_webdriver()
        self._already_reserved = False

    def _setup_notifications(self) -> None:
        """Initialize notification services."""
        self.email_service = EmailNotificationService(self.config.email)
        self.sms_service = SMSNotificationService(self.config.sms, self.config.email)

    def _setup_webdriver(self) -> None:
        """Initialize the WebDriver."""
        self.driver: WebDriver
        self.wait: WebDriverWait
        self.driver, self.wait = create_driver(headless=self.config.headless)

    def send_notification(self, subject: str, message: str) -> None:
        """Send notification based on configured method.

        Args:
            subject: Notification subject.
            message: Notification message body.
        """
        method = self.config.notification_method

        if method == "email":
            if self.email_service.send(subject, message):
                print(f"Notification sent via email: {subject}")
            else:
                print(f"Failed to send email notification: {subject}")

        elif method == "sms":
            if self.sms_service.send(subject, message):
                print(f"Notification sent via SMS: {subject}")
            else:
                print(f"Failed to send SMS notification: {subject}")

        elif method == "both":
            email_success = self.email_service.send(subject, message)
            sms_success = self.sms_service.send(subject, message)

            if email_success:
                print(f"Notification sent via email: {subject}")
            else:
                print(f"Failed to send email notification: {subject}")

            if sms_success:
                print(f"Notification sent via SMS: {subject}")
            else:
                print(f"Failed to send SMS notification: {subject}")

            if not email_success and not sms_success:
                print("All notification methods failed")

        else:
            print(f"Unknown notification method: {method}, defaulting to email")
            self.email_service.send(subject, message)

    def _get_target_date(self) -> str:
        """Get the target date for reservation."""
        return get_target_date(
            self.config.run_on_schedule,
            self.config.target_class.date,
        )

    def _get_class_details(self, target_date: str) -> str:
        """Get formatted class details for notifications."""
        tc = self.config.target_class
        return (
            f"Class: {tc.name}\n"
            f"Instructor: {tc.instructor}\n"
            f"Date: {target_date}\n"
            f"Time: {tc.start_time} - {tc.end_time}"
        )

    def login(self) -> None:
        """Log into Life Time Fitness website."""
        self.driver.get(self.config.login_url)
        self.wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(
            self.config.username
        )
        self.wait.until(EC.presence_of_element_located((By.NAME, "password"))).send_keys(
            self.config.password + Keys.RETURN
        )
        time.sleep(3)
        print("Logged in successfully.")

    def navigate_to_schedule(self, target_date: str) -> bool:
        """Navigate to the class schedule page.

        Args:
            target_date: Date to view schedule for (YYYY-MM-DD format).

        Returns:
            True if schedule loaded successfully, False otherwise.
        """
        club = self.config.club
        url_segment = club.get_url_segment()
        url_param = club.get_url_param()

        schedule_url = (
            f"https://my.lifetime.life/clubs/{club.state.lower()}/{url_segment}/classes.html?"
            f"teamMemberView=true&selectedDate={target_date}&mode=day&"
            f"location={url_param}"
        )
        self.driver.get(schedule_url)
        print(f"Navigated to schedules page for {target_date}.")

        try:
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "planner-entry")))
            print("Schedule loaded successfully.")
            return True
        except Exception as e:
            print(f"Schedule did not load: {e}")
            return False

    def find_target_class(self) -> WebElement | None:
        """Find and return the target class element.

        Returns:
            The clickable link element for the target class, or None if not found.
        """
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        class_elements = self.wait.until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'planner-entry')]"))
        )

        print(f"Found {len(class_elements)} classes on the page.")

        for element in class_elements:
            if self._is_matching_class(element):
                class_text = element.text.replace("\n", " ").strip()
                print(f"Found matching class: {class_text[:50]}...")
                return element.find_element(By.TAG_NAME, "a")

        print("No matching class found on this page")
        return None

    def _is_matching_class(self, element: WebElement) -> bool:
        """Check if class element matches target criteria.

        Args:
            element: The class element to check.

        Returns:
            True if the element matches all criteria.
        """
        class_text = element.text.replace("\n", " ").strip()
        time_match = re.search(
            r"(\d{1,2}:\d{2})\s?to\s?(\d{1,2}:\d{2})\s?(AM|PM)",
            class_text,
            re.IGNORECASE,
        )

        if not time_match:
            return False

        start_time = f"{time_match.group(1)} {time_match.group(3)}"
        end_time = f"{time_match.group(2)} {time_match.group(3)}"

        tc = self.config.target_class
        return (
            tc.name.lower().strip() in class_text.lower().strip()
            and start_time.strip() == tc.start_time.strip()
            and end_time.strip() == tc.end_time.strip()
            and tc.instructor.lower().strip() in class_text.lower().strip()
        )

    def reserve_class(self) -> bool:
        """Main method to handle class reservation process.

        Returns:
            True if reservation was successful (or already reserved), False otherwise.
        """
        target_date = self._get_target_date()
        class_details = self._get_class_details(target_date)

        try:
            self.login()

            if not self.navigate_to_schedule(target_date):
                raise RuntimeError("Failed to load schedule")

            class_link = self.find_target_class()
            if not class_link:
                raise RuntimeError("Target class not found")

            class_url = class_link.get_attribute("href")
            self.driver.get(class_url)
            time.sleep(5)

            reservation_result = self._complete_reservation()
            if reservation_result:
                if not self._already_reserved:
                    self.send_notification(
                        "Lifetime Bot - Success",
                        f"Your class was successfully reserved!\n\n{class_details}",
                    )
                return True
            else:
                raise RuntimeError("Reservation process failed")

        except Exception as e:
            print(f"Reservation failed: {e}")
            self.send_notification(
                "Lifetime Bot - Failure",
                f"Failed to reserve class:\n\n{class_details}\n\nError: {e!s}",
            )
            raise

        finally:
            self.driver.quit()

    def _complete_reservation(self) -> bool:
        """Complete the reservation process after finding the class.

        Returns:
            True if reservation completed successfully.
        """
        try:
            if not self._click_reserve_button():
                return True  # Class was already reserved

            # Wait for page transition after clicking reserve
            time.sleep(3)

            if "pickleball" in self.config.target_class.name.lower():
                # Check if waiver exists before handling
                waiver_elements = self.driver.find_elements(By.XPATH, "//label[@for='acceptwaiver']")
                if waiver_elements:
                    self._handle_waiver()

            self._click_finish()
            return self._verify_confirmation()

        except Exception as e:
            print(f"Error completing reservation: {e}")
            return False

    def _click_reserve_button(self) -> bool:
        """Click the reserve or waitlist button, or handle if already reserved.

        Returns:
            True if button was clicked, False if already reserved.
        """
        time.sleep(3)

        buttons = self.driver.find_elements(
            By.CSS_SELECTOR, "button[data-test-id='reserveButton']"
        )

        if not buttons:
            buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Reserve')] | "
                "//button[contains(text(), 'Add to Waitlist')] | "
                "//button[contains(text(), 'Cancel')] | "
                "//button[contains(text(), 'Leave Waitlist')]",
            )

        if not buttons:
            raise RuntimeError("No reserve/waitlist/cancel button found")

        for button in buttons:
            try:
                button_text = button.text
            except Exception:
                continue

            if "Cancel" in button_text or "Leave Waitlist" in button_text:
                print("Class is already reserved or on waitlist!")
                self._already_reserved = True
                class_details = self._get_class_details(self._get_target_date())
                self.send_notification(
                    "Lifetime Bot - Already Reserved",
                    f"The class was already reserved or waitlisted. No action needed.\n\n{class_details}",
                )
                return False

            if "Reserve" in button_text or "Add to Waitlist" in button_text:
                self.driver.execute_script("arguments[0].scrollIntoView();", button)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", button)
                return True

        raise RuntimeError("Could not click reserve/waitlist button")

    def _handle_waiver(self) -> None:
        """Handle the waiver checkbox for pickleball classes."""
        checkbox_label = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//label[@for='acceptwaiver']"))
        )
        checkbox_label.click()
        time.sleep(1)

        checkbox = self.driver.find_element(By.ID, "acceptwaiver")
        if not checkbox.is_selected():
            checkbox_label.click()
            time.sleep(1)

    def _click_finish(self) -> None:
        """Click the finish button."""
        finish_button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Finish')]"))
        )
        finish_button.click()

    def _verify_confirmation(self) -> bool:
        """Verify the reservation confirmation.

        Returns:
            True if confirmation message is found.
        """
        try:
            self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//h1[contains(text(), 'Your reservation is complete')]")
                )
            )
            return True
        except Exception:
            return False

    def cleanup(self) -> None:
        """Clean up browser resources."""
        try:
            if hasattr(self, "driver") and self.driver:
                print("Clearing browser cache and cookies...")
                self.driver.delete_all_cookies()
                self.driver.execute_script("window.localStorage.clear();")
                self.driver.execute_script("window.sessionStorage.clear();")
        except Exception as e:
            print(f"Error during cleanup: {e}")

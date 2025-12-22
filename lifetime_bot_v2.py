import os
import time
import re
import datetime
import smtplib
import requests
import warnings
import pytz
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Clear cached env vars
for key in list(os.environ.keys()):
    del os.environ[key]

load_dotenv(override=True)

# ==============================
# TIME CONFIG
# ==============================

CST = pytz.timezone("America/Chicago")

BOOKING_START_TIME = datetime.time(10, 1)    # 10:01 AM CST
BOOKING_CUTOFF_TIME = datetime.time(10, 15)  # 10:15 AM CST
RETRY_INTERVAL_SECONDS = 60
SUCCESS_FLAG_FILE = ".booking_success"


class LifetimeReservationBot:
    def __init__(self):
        self.setup_config()
        self.setup_email_config()
        self.setup_sms_config()
        self.setup_webdriver()

    def setup_config(self):
        self.RUN_ON_SCHEDULE = os.getenv("RUN_ON_SCHEDULE", "false").lower() == "true"
        self.LOGIN_URL = "https://my.lifetime.life/login.html"
        self.USERNAME = os.getenv("LIFETIME_USERNAME")
        self.PASSWORD = os.getenv("LIFETIME_PASSWORD")
        self.TARGET_CLASS = os.getenv("TARGET_CLASS")
        self.TARGET_INSTRUCTOR = os.getenv("TARGET_INSTRUCTOR")
        self.TARGET_DATE = os.getenv("TARGET_DATE")
        self.START_TIME = os.getenv("START_TIME")
        self.END_TIME = os.getenv("END_TIME", "10:00 AM")
        self.LIFETIME_CLUB_NAME = os.getenv("LIFETIME_CLUB_NAME")
        self.LIFETIME_CLUB_STATE = os.getenv("LIFETIME_CLUB_STATE")
        self.NOTIFICATION_METHOD = os.getenv("NOTIFICATION_METHOD", "email").lower()
        self.SMS_CARRIER = os.getenv("SMS_CARRIER", "").lower()
        self.SMS_NUMBER = os.getenv("SMS_NUMBER", "")
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
        self.WHO_AM_I = os.getenv("WHO_AM_I")

    # ======================================================
    # VALID BOOKING DAYS (BOOKING DAYS, NOT CLASS DAYS)
    # Sunday, Monday, Wednesday, Thursday
    # ======================================================

    def is_valid_booking_day(self):
        # Python: Monday=0 ... Sunday=6
        return datetime.datetime.now(CST).weekday() in [6, 0, 2, 3]

    # ==============================
    # NOTIFICATIONS (UNCHANGED LOGIC)
    # ==============================

    def send_telegram(self, message):
        try:
            if not self.TELEGRAM_TOKEN or not self.TELEGRAM_CHAT_ID:
                return
            url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": self.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }
            requests.post(url, data=payload, timeout=10)
        except Exception:
            pass

    def setup_email_config(self):
        self.EMAIL_SENDER = os.getenv("EMAIL_SENDER")
        self.EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
        self.EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
        self.SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

    def setup_sms_config(self):
        self.SMS_GATEWAYS = {
            "att": "mms.att.net",
            "tmobile": "tmomail.net",
            "verizon": "vtext.com",
        }

    def send_notification(self, subject, message):
        if self.NOTIFICATION_METHOD == "telegram":
            self.send_telegram(f"<b>{subject}</b>\n{message}")
        else:
            self.send_email(subject, message)

    def send_email(self, subject, message):
        msg = MIMEMultipart()
        msg["From"] = self.EMAIL_SENDER
        msg["To"] = self.EMAIL_RECEIVER
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
            server.starttls()
            server.login(self.EMAIL_SENDER, self.EMAIL_PASSWORD)
            server.send_message(msg)

    # ==============================
    # SELENIUM
    # ==============================

    def setup_webdriver(self):
    options = webdriver.ChromeOptions()

    # REQUIRED for GitHub Actions
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # Reduce crash risk
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-software-rasterizer")

    # Use ChromeDriver provided by setup-chrome
    self.driver = webdriver.Chrome(options=options)
    self.wait = WebDriverWait(self.driver, 30)

    # ==============================
    # BOOKING
    # ==============================

    def reserve_class(self):
        if os.path.exists(SUCCESS_FLAG_FILE):
            print("🔒 Booking already completed.")
            return True

        if not self.is_valid_booking_day():
            print("❌ Not a valid booking day. Exiting.")
            return True

        try:
            self.login()
            self.navigate_to_schedule(self.get_target_date())
            class_link = self.find_target_class()

            if not class_link:
                raise Exception("Target class not found")

            self.driver.get(class_link.get_attribute("href"))
            time.sleep(5)

            if self._complete_reservation():
                with open(SUCCESS_FLAG_FILE, "w") as f:
                    f.write("success")

                self.send_notification(
                    "Lifetime Bot - Success",
                    "✅ Your class was successfully booked!"
                )
                return True

            return False
        finally:
            self.driver.quit()

    # ======================================================
    # YOUR EXISTING METHODS (UNCHANGED BELOW THIS POINT)
    # login(), navigate_to_schedule(), find_target_class(),
    # _complete_reservation(), etc.
    # ======================================================


# ==============================
# WAIT UNTIL 10:01 CST
# ==============================

def wait_until_booking_window():
    now = datetime.datetime.now(CST)

    start = now.replace(
        hour=BOOKING_START_TIME.hour,
        minute=BOOKING_START_TIME.minute,
        second=0,
        microsecond=0
    )

    if now < start:
        sleep_seconds = (start - now).total_seconds()
        print(f"⏳ Waiting {int(sleep_seconds)} seconds until 10:01 AM CST")
        time.sleep(sleep_seconds)


# ==============================
# MAIN LOOP
# ==============================

def main():
    wait_until_booking_window()

    while True:
        now = datetime.datetime.now(CST)

        cutoff = now.replace(
            hour=BOOKING_CUTOFF_TIME.hour,
            minute=BOOKING_CUTOFF_TIME.minute,
            second=0,
            microsecond=0
        )

        if now >= cutoff:
            bot = LifetimeReservationBot()
            bot.send_notification(
                "Lifetime Bot - Failed",
                "❌ Failed to book class by 10:15 AM CST"
            )
            return

        try:
            bot = LifetimeReservationBot()
            if bot.reserve_class():
                return
        except Exception as e:
            print(f"⚠️ Booking attempt failed: {e}")

        print("🔁 Retrying in 60 seconds...")
        time.sleep(RETRY_INTERVAL_SECONDS)


# ==============================
# ENTRYPOINT
# ==============================

if __name__ == "__main__":
    main()

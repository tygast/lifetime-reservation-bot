import os
import time
import re
import datetime
import smtplib
import requests
import warnings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Suppress all warnings before importing selenium and other libraries
warnings.filterwarnings("ignore")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Clear any cached environment variables
for key in list(os.environ.keys()):
    del os.environ[key]

# Now load from .env file
load_dotenv(override=True)


class LifetimeReservationBot:
    def __init__(self):
        self.setup_config()
        self.setup_email_config()
        self.setup_sms_config()
        self.setup_webdriver()
        
    def setup_config(self):
        """Initialize configuration from environment variables"""
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
        if not self.LIFETIME_CLUB_NAME or not self.LIFETIME_CLUB_STATE:
            raise ValueError("LIFETIME_CLUB_NAME and LIFETIME_CLUB_STATE environment variables are required")

    def send_telegram(self, message):
        """Send notification via Telegram"""
        try:
            # Use the token and chat ID from environment variables
            token = os.getenv("TELEGRAM_TOKEN") 
            chat_id = os.getenv("TELEGRAM_CHAT_ID") 

            if not token or not chat_id:
                print("⚠️ Telegram Token or Chat ID missing from .env")
                return

            # FIX: Remove "bot" prefix if it was included in the .env by mistake
            # This prevents the URL from becoming /botbot123... which causes a 404
            clean_token = str(token).replace("bot", "").strip()
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, data=payload)
            if response.status_code == 200:
                print("📱 Telegram notification sent!")
            else:
                print(f"❌ Telegram failed: {response.text}")
        except Exception as e:
            print(f"❌ Error sending Telegram: {e}")
        
    def setup_email_config(self):
        """Initialize email configuration"""
        self.EMAIL_SENDER = os.getenv("EMAIL_SENDER")
        self.EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
        self.EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
        self.SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
        
    def setup_sms_config(self):
        """Initialize SMS configuration using email-to-SMS gateways"""
        self.SMS_GATEWAYS = {
            "att": "mms.att.net",
            "tmobile": "tmomail.net",
            "verizon": "vtext.com",
            "sprint": "messaging.sprintpcs.com",
            "boost": "sms.myboostmobile.com",
            "cricket": "sms.cricketwireless.net",
            "metro": "mymetropcs.com",
            "uscellular": "email.uscc.net",
            "virgin": "vmobl.com",
            "xfinity": "vtext.com",
            "googlefi": "msg.fi.google.com",
        }
        
    def setup_webdriver(self):
        """Initialize Selenium WebDriver"""
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        if os.getenv("HEADLESS") == "true":
            options.add_argument("--headless=new")
            
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, 30)
        
    def send_notification(self, subject, message):
        """Send notification based on configured method"""
        if self.NOTIFICATION_METHOD == "email":
            self.send_email(subject, message)
            print(f"📧 Notification sent via email: {subject}")

        elif self.NOTIFICATION_METHOD == "sms":
            self.send_sms(subject, message)
            print(f"📱 Notification sent via SMS: {subject}")

        elif self.NOTIFICATION_METHOD == "telegram":
            self.send_telegram(f"<b>{subject}</b>\n{message}")
            print(f"📡 Notification sent via Telegram: {subject}")

        elif self.NOTIFICATION_METHOD == "both":
            # For "both", we need to ensure both methods are called regardless of errors
            email_success = False
            sms_success = False
            
            try:
                self.send_email(subject, message)
                email_success = True
                print(f"📧 Notification sent via email: {subject}")
            except Exception as e:
                print(f"❌ Failed to send email notification: {e}")
                
            try:
                self.send_sms(subject, message)
                sms_success = True
                print(f"📱 Notification sent via SMS: {subject}")
            except Exception as e:
                print(f"❌ Failed to send SMS notification: {e}")

            try:
                self.send_telegram(f"<b>{subject}</b>\n{message}")
                print(f"📡 Telegram sent: {subject}")
            except: 
                pass
                
            if not email_success and not sms_success:
                print("⚠️ All notification methods failed")
        else:
            print(f"⚠️ Unknown notification method: {self.NOTIFICATION_METHOD}, defaulting to email")
            self.send_email(subject, message)
        
    def send_email(self, subject, message):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.EMAIL_SENDER
            msg['To'] = self.EMAIL_RECEIVER
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))

            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
                server.starttls()
                server.login(self.EMAIL_SENDER, self.EMAIL_PASSWORD)
                server.send_message(msg)
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
            
    def send_sms(self, subject, message):
        """Send SMS notification using email-to-SMS gateway"""
        try:
            if not self.SMS_NUMBER or not self.SMS_CARRIER:
                error_msg = "❌ SMS configuration incomplete. Check SMS_NUMBER and SMS_CARRIER environment variables."
                print(error_msg)
                raise ValueError(error_msg)
                
            if self.SMS_CARRIER not in self.SMS_GATEWAYS:
                error_msg = f"❌ Unknown carrier: {self.SMS_CARRIER}. Supported carriers: {', '.join(self.SMS_GATEWAYS.keys())}"
                print(error_msg)
                raise ValueError(error_msg)
                
            # Format the SMS message
            sms_message = f"{subject}: {message}"
            
            # Create the email-to-SMS address
            sms_email = f"{self.SMS_NUMBER}@{self.SMS_GATEWAYS[self.SMS_CARRIER]}"
            
            # Use the existing email functionality to send the SMS
            msg = MIMEMultipart()
            msg['From'] = self.EMAIL_SENDER
            msg['To'] = sms_email
            msg['Subject'] = "LT Bot" 
            
            # Plain text only
            msg.attach(MIMEText(sms_message, 'plain'))

            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
                server.starttls()
                server.login(self.EMAIL_SENDER, self.EMAIL_PASSWORD)
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"❌ Failed to send SMS: {e}")
            raise

    def get_target_date(self):
        """Calculate target date for class reservation"""
        if self.RUN_ON_SCHEDULE:
            target_date = (datetime.datetime.now() + 
                          datetime.timedelta(days=8)).strftime("%Y-%m-%d")
        else:
            target_date = self.TARGET_DATE
        return target_date

    def is_valid_day(self):
        """Check if current day is valid for scheduling"""
        return datetime.datetime.today().weekday() in [0, 1, 2, 3, 6]

    def login(self):
        """Log into Lifetime Fitness website"""
        self.driver.get(self.LOGIN_URL)
        self.wait.until(EC.presence_of_element_located(
            (By.NAME, "username"))).send_keys(self.USERNAME)
        self.wait.until(EC.presence_of_element_located(
            (By.NAME, "password"))).send_keys(self.PASSWORD + Keys.RETURN)
        time.sleep(3)
        print("✅ Logged in successfully.")

    def _format_club_url_segment(self, club_name):
        """Convert club name to URL-friendly format"""
        # Remove 'Life Time' or variations from the name
        name = club_name.replace('Life Time', '').replace('LifeTime', '').strip()
        name = name.strip(' -')  # Remove leading/trailing dashes and spaces
        
        # Replace spaces and special characters
        name = name.replace(' at ', '-').replace(' - ', '-')
        
        # Convert to lowercase and replace spaces with hyphens
        name = name.lower().replace(' ', '-')
        
        # Remove any special characters except hyphens
        name = ''.join(c for c in name if c.isalnum() or c == '-')
        
        return name

    def navigate_to_schedule(self, target_date):
        """Navigate to the class schedule page"""
        club_name = self.LIFETIME_CLUB_NAME
        club_state = self.LIFETIME_CLUB_STATE.lower()
        if not club_name or not club_state:
            raise Exception("LIFETIME_CLUB_NAME and LIFETIME_CLUB_STATE environment variables are not set")
        
        url_segment = self._format_club_url_segment(club_name)
        url_param = club_name.replace(' ', '+')
        
        schedule_url = (
            f"https://my.lifetime.life/clubs/{club_state}/{url_segment}/classes.html?"
            f"teamMemberView=true&selectedDate={target_date}&mode=day&"
            f"location={url_param}"
        )
        self.driver.get(schedule_url)
        print(f"🔄 Navigated to schedules page for {target_date}.")
        
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CLASS_NAME, "planner-entry")))
            print("✅ Schedule loaded successfully.")
            return True
        except Exception as e:
            print(f"❌ Schedule did not load: {e}")
            return False

    def find_target_class(self):
        """Find and return the target class element"""
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        class_elements = self.wait.until(EC.presence_of_all_elements_located(
            (By.XPATH, "//div[contains(@class, 'planner-entry')]")))
        
        print(f"🔍 Found {len(class_elements)} classes on the page.")
        
        for element in class_elements:
            if self._is_matching_class(element):
                # Fix the backslash issue by using a raw string or double backslashes
                class_text = element.text.replace('\n', ' ').strip()
                print(f"✅ Found matching class: {class_text[:50]}...")
                return element.find_element(By.TAG_NAME, "a")
        
        print("❌ No matching class found on this page")
        return None

    def _is_matching_class(self, element):
        """Check if class element matches target criteria"""
        class_text = element.text.replace("\n", " ").strip()
        time_match = re.search(
            r"(\d{1,2}:\d{2})\s?to\s?(\d{1,2}:\d{2})\s?(AM|PM)",
            class_text,
            re.IGNORECASE
        )
        
        if not time_match:
            return False
            
        start_time = f"{time_match.group(1)} {time_match.group(3)}"
        end_time = f"{time_match.group(2)} {time_match.group(3)}"
        
        return (
            self.TARGET_CLASS.lower().strip() in class_text.lower().strip() and
            start_time.strip() == self.START_TIME.strip() and
            end_time.strip() == self.END_TIME.strip() and
            self.TARGET_INSTRUCTOR.lower().strip() in class_text.lower().strip()
        )

    def reserve_class(self):
        """Main method to handle class reservation process"""
        try:
            target_date = self.get_target_date()
            
            # Create email details string
            class_details = (
                f"Class: {self.TARGET_CLASS}\n"
                f"Instructor: {self.TARGET_INSTRUCTOR}\n"
                f"Date: {target_date}\n"
                f"Time: {self.START_TIME} - {self.END_TIME}"
            )
            
            # Login and navigate
            self.login()
            if not self.navigate_to_schedule(target_date):
                raise Exception("Failed to load schedule")
                
            # Find and click target class
            class_link = self.find_target_class()
            if not class_link:
                raise Exception("Target class not found")
                
            class_url = class_link.get_attribute("href")
            self.driver.get(class_url)
            time.sleep(5)
            
            # Complete reservation
            reservation_result = self._complete_reservation()
            if reservation_result:
                # Only send success notification if it wasn't already reserved
                if not hasattr(self, 'already_reserved'):
                    self.send_notification(
                        "Lifetime Bot - Success",
                        f"Your class was successfully reserved!\n\n{class_details}"
                    )
                return True  # Return True to indicate success
            else:
                raise Exception("Reservation process failed")
                
        except Exception as e:
            print(f"❌ Reservation failed: {e}")
            self.send_notification(
                "Lifetime Bot - Failure",
                f"Failed to reserve class:\n\n{class_details}\n\nError: {str(e)}"
            )
            raise  # Re-raise the exception to be caught by the main function
        finally:
            self.driver.quit()

    def _complete_reservation(self):
        """Complete the reservation process after finding the class"""
        try:
            # Click reserve button - if returns False, class was already reserved
            if not self._click_reserve_button():
                return True  # Return True because this is a success case
            
            # Handle waiver if needed
            if "pickleball" in self.TARGET_CLASS.lower():
                self._handle_waiver()
                
            # Click finish and verify
            self._click_finish()
            return self._verify_confirmation()
            
        except Exception as e:
            print(f"❌ Error completing reservation: {e}")
            return False

    def _click_reserve_button(self):
        """Click the reserve or waitlist button, or handle if already reserved"""
        wait = WebDriverWait(self.driver, 15)
        time.sleep(3)
        
        buttons = self.driver.find_elements(
            By.CSS_SELECTOR,
            "button[data-test-id='reserveButton']"
        ) or self.driver.find_elements(
            By.XPATH,
            "//button[contains(text(), 'Reserve')] | "
            "//button[contains(text(), 'Add to Waitlist')] | "
            "//button[contains(text(), 'Cancel')] | "
            "//button[contains(text(), 'Leave Waitlist')]"
        )
        
        if not buttons:
            raise Exception("No reserve/waitlist/cancel button found")
            
        for button in buttons:
            if "Cancel" in button.text or "Leave Waitlist" in button.text:
                print("✅ Class is already reserved or on waitlist!")
                self.already_reserved = True  # Set flag for already reserved
                class_details = (
                    f"Class: {self.TARGET_CLASS}\n"
                    f"Instructor: {self.TARGET_INSTRUCTOR}\n"
                    f"Date: {self.get_target_date()}\n"
                    f"Time: {self.START_TIME} - {self.END_TIME}"
                )
                self.send_notification(
                    "Lifetime Bot - Already Reserved",
                    f"The class was already reserved or waitlisted. No action needed.\n\n{class_details}"
                )
                return False
            elif "Reserve" in button.text or "Add to Waitlist" in button.text:
                self.driver.execute_script("arguments[0].scrollIntoView();", button)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", button)
                return True
                
        raise Exception("Could not click reserve/waitlist button")

    def _handle_waiver(self):
        """Handle the waiver checkbox for pickleball classes"""
        checkbox_label = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//label[@for='acceptwaiver']"))
        )
        checkbox_label.click()
        time.sleep(1)
        
        checkbox = self.driver.find_element(By.ID, "acceptwaiver")
        if not checkbox.is_selected():
            checkbox_label.click()
            time.sleep(1)

    def _click_finish(self):
        """Click the finish button"""
        finish_button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Finish')]"))
        )
        finish_button.click()

    def _verify_confirmation(self):
        """Verify the reservation confirmation"""
        try:
            self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//h1[contains(text(), 'Your reservation is complete')]")
                )
            )
            return True
        except Exception:
            return False

def wait_until_utc(target_utc_time: str):
    """
    Waits until the given target UTC time in HH:MM:SS format, then executes `main()`.
    If the current time is already past the target, it runs `main()` immediately.
    """
    # Check if RUN_ON_SCHEDULE is false
    if os.getenv("RUN_ON_SCHEDULE", "false").lower() == "false":
        print("RUN_ON_SCHEDULE is false, running main() immediately.")
        main()
        return  
    
    now = datetime.datetime.now(datetime.timezone.utc)
    target = datetime.datetime.strptime(target_utc_time, "%H:%M:%S").time()
    target_datetime = datetime.datetime.combine(now.date(), target).replace(tzinfo=datetime.timezone.utc)

    if now >= target_datetime:
        print(f"Current time ({now.strftime('%H:%M:%S')} UTC) is past {target_utc_time}, running main() immediately.")
        main()
        return  

    sleep_seconds = (target_datetime - now).total_seconds()
    print(f"Sleeping for {sleep_seconds:.2f} seconds...")
    time.sleep(sleep_seconds)

    print(f"Reached target UTC time: {target_datetime.strftime('%H:%M:%S')} UTC")
    main()  

def main():
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        bot = None
        try:
            print(f"Attempt {retry_count + 1}/{max_retries} to reserve class")
            bot = LifetimeReservationBot()
            success = bot.reserve_class()
            if success:
                print("✅ Class reservation completed successfully!")
                break
        except Exception as e:
            retry_count += 1
            print(f"❌ Attempt {retry_count}/{max_retries} failed with error: {str(e)}")
            
            try:
                if bot and hasattr(bot, 'driver') and bot.driver:
                    print("🧹 Clearing browser cache and cookies...")
                    bot.driver.delete_all_cookies()
                    bot.driver.execute_script("window.localStorage.clear();")
                    bot.driver.execute_script("window.sessionStorage.clear();")
            except Exception as cleanup_error:
                print(f"⚠️ Error during cleanup: {cleanup_error}")
            
            if retry_count >= max_retries:
                try:
                    if bot and hasattr(bot, 'send_notification'):
                        bot.send_notification(
                            "Lifetime Bot - All Attempts Failed",
                            f"Failed to reserve class after {max_retries} attempts. Last error: {str(e)}"
                        )
                except Exception as notify_error:
                    print(f"❌ Could not send failure notification: {notify_error}")
            else:
                retry_delay = 30  
                print(f"⏳ Waiting {retry_delay} seconds before retry {retry_count + 1}/{max_retries}...")
                time.sleep(retry_delay)

if __name__ == "__main__":
    target_time = os.getenv("TARGET_UTC_TIME", "16:00:00")
    wait_until_utc(target_time)

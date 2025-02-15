import os
import time
import re
import datetime
import schedule
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class LifetimeReservationBot:
    def __init__(self):
        load_dotenv()
        self.setup_config()
        self.setup_email_config()
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
        
    def setup_email_config(self):
        """Initialize email configuration"""
        self.EMAIL_SENDER = os.getenv("EMAIL_SENDER")
        self.EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
        self.EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
        self.SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
        
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
            print(f"📧 Email sent: {subject}")
        except Exception as e:
            print(f"❌ Failed to send email: {e}")

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

    def navigate_to_schedule(self, target_date):
        """Navigate to the class schedule page"""
        schedule_url = (
            f"https://my.lifetime.life/clubs/tx/san-antonio-281/classes.html?"
            f"teamMemberView=true&selectedDate={target_date}&mode=day&"
            f"location=San+Antonio+281"
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
                return element.find_element(By.TAG_NAME, "a")
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
            if self._complete_reservation():
                self.send_email(
                    "Lifetime Bot - Success",
                    f"Your class on {target_date} was successfully reserved."
                )
            else:
                raise Exception("Reservation process failed")
                
        except Exception as e:
            print(f"❌ Reservation failed: {e}")
            self.send_email(
                "Lifetime Bot - Failure",
                f"Failed to reserve class on {target_date}: {str(e)}"
            )
        finally:
            self.driver.quit()

    def _complete_reservation(self):
        """Complete the reservation process after finding the class"""
        try:
            # Click reserve button
            self._click_reserve_button()
            
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
        """Click the reserve or waitlist button"""
        wait = WebDriverWait(self.driver, 15)
        time.sleep(3)
        
        buttons = self.driver.find_elements(
            By.CSS_SELECTOR,
            "button[data-test-id='reserveButton']"
        ) or self.driver.find_elements(
            By.XPATH,
            "//button[contains(text(), 'Reserve')] | "
            "//button[contains(text(), 'Add to Waitlist')]"
        )
        
        if not buttons:
            raise Exception("No reserve/waitlist button found")
            
        for button in buttons:
            if "Reserve" in button.text or "Add to Waitlist" in button.text:
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

def main():
    bot = LifetimeReservationBot()
    
    end_time = datetime.datetime.strptime(bot.END_TIME, '%I:%M %p')
    tomorrow = datetime.datetime.now().date() + datetime.timedelta(days=1)

    if bot.RUN_ON_SCHEDULE:
        scheduled_time = (datetime.datetime.combine(tomorrow, end_time.time()) + 
                          datetime.timedelta(hours=1)).strftime("%H:%M")
        print(f"🕒 Scheduling script to run daily at {scheduled_time}")
        schedule.every().day.at(scheduled_time).do(bot.reserve_class)
        
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        bot.reserve_class()

if __name__ == "__main__":
    main()

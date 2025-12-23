# Lifetime Fitness Reservation Bot v2 (Iterated from Tyler's Original)

An automated bot that helps you reserve classes at Life Time Fitness clubs. The bot can be scheduled to run at specific times to secure your spot in popular classes as soon as they become available.

This version is time-window aware, CI-safe, retry-capable, and includes Telegram startup + result notifications so you always know what the bot is doing.

⸻

🚀 Key Features
	•	Automatically logs into your Life Time Fitness account
	•	Navigates directly to your club’s class schedule
	•	Finds a target class by:
	•	Class name
	•	Instructor
	•	Start & end time
	•	Reserves or waitlists the class
	•	Retries every 60 seconds if the class isn’t immediately available
	•	Hard cutoff time to avoid infinite retries
	•	Prevents duplicate bookings using a success flag
	•	Sends notifications via:
	•	Telegram
	•	Email (optional)
	•	Sends a startup Telegram notification when the script initializes and begins waiting
	•	Fully compatible with GitHub Actions (headless Chrome)

⸻

🕒 Booking Logic (Important)

Life Time classes open 8 days before the class date at 10:00 AM local club time.

This bot:
	•	Begins attempting bookings at 10:01 AM CST
	•	Retries every 60 seconds
	•	Stops trying at 10:15 AM CST
	•	Runs only on booking-relevant days:
	•	Sunday
	•	Monday
	•	Wednesday
	•	Thursday

This correctly books:
	•	Monday
	•	Tuesday
	•	Thursday
	•	Friday classes

⸻

📦 Requirements
	•	Python 3.9+
	•	Google Chrome (provided automatically in GitHub Actions)
	•	A Life Time Fitness account
	•	Telegram bot (for notifications)
	•	GitHub repository with Actions enabled

⸻

📥 Installation (Local Development)

Clone the repository:

git clone https://github.com/yourusername/lifetime-reservation-bot.git
cd lifetime-reservation-bot

Create and activate a virtual environment:

python -m venv .venv

Windows:
.venv\Scripts\activate

macOS / Linux:
source .venv/bin/activate

Install dependencies:

pip install -r requirements.txt

⸻

🔐 Configuration (.env)

Create a .env file locally or via GitHub Actions secrets.

⸻

🔑 Required Credentials

LIFETIME_USERNAME=your_lifetime_email
LIFETIME_PASSWORD=your_lifetime_password

⸻

🏋️ Club & Class Configuration

LIFETIME_CLUB_NAME=San Antonio 281
LIFETIME_CLUB_STATE=TX

TARGET_CLASS=Alpha
TARGET_INSTRUCTOR=Zack W
START_TIME=8:00 AM
END_TIME=9:00 AM

⚠️ Exact string matching matters.

⸻

📅 Target Date

TARGET_DATE=YYYY-MM-DD

In GitHub Actions, this is automatically set to today + 8 days.

⸻

📲 Notification Configuration

Telegram (Recommended)
NOTIFICATION_METHOD=telegram
TELEGRAM_TOKEN=123456789:ABCDEF_your_bot_token
TELEGRAM_CHAT_ID=123456789

The bot sends:
	•	Startup notification
	•	Success notification
	•	Already-reserved notification
	•	Final failure notification (after cutoff)

⸻

Email (Optional)
NOTIFICATION_METHOD=email

EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=your_email@gmail.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

1. Use a Gmail account
2. Enable 2-Step Verification in your Google Account
3. Generate an App Password:
   - Go to Google Account Settings → Security
   - Under "2-Step Verification", scroll to "App passwords"
   - Generate a new app password
   - Use this password for EMAIL_PASSWORD in your .env file

⸻

⚙️ Runtime Flags

RUN_ON_SCHEDULE=true

⸻

⏱️ Constant Time Configuration (Defined in Code)

These values live directly in lifetime_bot.py and must be defined with precise syntax:

BOOKING_START_TIME = datetime.time(10, 1)
BOOKING_CUTOFF_TIME = datetime.time(10, 15)
RETRY_INTERVAL_SECONDS = 60
SUCCESS_FLAG_FILE = “.booking_success”

⚠️ Syntax Rules (Important)
	•	Use datetime.time(HOUR, MINUTE)
	•	No leading zeros (01 is invalid, 1 is correct)
	•	Uses a 24-hour clock internally

Examples:

datetime.time(10, 1)   → 10:01 AM
datetime.time(11, 15)  → 11:15 AM
datetime.time(16, 0)   → 4:00 PM

⸻

⏳ Script Lifecycle
	1.	GitHub Actions starts the job
	2.	Script initializes
	3.	Startup Telegram notification is sent
	4.	Script waits until booking window opens
	5.	Booking attempts begin
	6.	Retries every 60 seconds if needed
	7.	On success:
	•	Writes .booking_success
	•	Sends success notification
	8.	On cutoff:
	•	Sends failure notification
	•	Exits cleanly

⸻

🧠 GitHub Actions Scheduling

The workflow runs before the booking window and lets the script handle timing.

Runs on:
	•	Sunday
	•	Monday
	•	Wednesday
	•	Thursday

Example cron (UTC):

30-59/5 15 * * 0,1,3,4
0-5/5 16 * * 0,1,3,4

⸻

🧪 Testing Tips

To test without waiting until 10:01 AM:

Temporarily change in code:

BOOKING_START_TIME = datetime.time(10, 35)
BOOKING_CUTOFF_TIME = datetime.time(10, 40)

Revert these values before production runs.

⸻

🛠️ Troubleshooting

Common Issues

Telegram not sending:
	•	Verify bot token and chat ID
	•	Ensure the bot can message the chat

Class not found:
	•	Verify spelling, spacing, and time format
	•	Confirm instructor name matches exactly

Chrome fails in GitHub Actions:
	•	Script is CI-safe
	•	webdriver-manager is not used
	•	Ensure browser-actions/setup-chrome@v1 is present

⸻

🔒 Security Notes
	•	Never commit .env
	•	Use GitHub Secrets for credentials
	•	Rotate credentials periodically
	•	Treat Telegram tokens like passwords

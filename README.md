# Lifetime Fitness Reservation Bot

An automated bot that helps you reserve classes at Life Time Fitness clubs. The bot can be scheduled to run at specific times to secure your spot in popular classes as soon as they become available.

## Features

- Automatically logs into your Life Time Fitness account
- Navigates to the class schedule for your preferred club
- Finds and reserves your target class based on class name, instructor, and time
- Handles waitlist scenarios automatically
- Special handling for classes requiring waivers (e.g., Pickleball)
- Sends notifications via email and/or SMS about reservation status
- Configurable retry logic (up to 3 attempts)
- Can be scheduled to run at specific local times with automatic DST handling
- Runs automatically via GitHub Actions or locally

## Project Structure

```
lifetime-reservation-bot/
├── src/
│   └── lifetime_bot/
│       ├── __init__.py          # Package exports
│       ├── __main__.py          # CLI entry point with retry logic
│       ├── bot.py               # Main LifetimeReservationBot class
│       ├── config.py            # Configuration dataclasses
│       ├── notifications/
│       │   ├── __init__.py
│       │   ├── base.py          # Abstract notification service
│       │   ├── email.py         # Email notification service
│       │   └── sms.py           # SMS notification service (via Twilio)
│       ├── utils/
│       │   ├── __init__.py
│       │   └── timing.py        # Timing and scheduling utilities
│       └── webdriver/
│           ├── __init__.py
│           └── driver.py        # Selenium WebDriver setup
├── archive/
│   └── lifetime_bot.py          # Legacy monolithic version (deprecated)
├── .github/
│   └── workflows/
│       ├── bot.yml              # GitHub Actions workflow
│       └── keepalive.yml        # Prevents workflow disabling after 60 days
├── pyproject.toml               # Python project configuration
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules
└── README.md                    # This file
```

## Requirements

- Python 3.9 or higher
- Chrome browser (for Selenium WebDriver)
- Gmail account (or other SMTP provider) for sending notifications

## Installation

### Option 1: Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer.

```bash
# Clone the repository
git clone https://github.com/yourusername/lifetime-reservation-bot.git
cd lifetime-reservation-bot

# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the package
uv pip install -e .
```

### Option 2: Using pip

```bash
# Clone the repository
git clone https://github.com/yourusername/lifetime-reservation-bot.git
cd lifetime-reservation-bot

# Create and activate a virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate

# Install the package in development mode
pip install -e .
```

### Option 3: Using pip with dependencies only

```bash
# Install dependencies directly from pyproject.toml
pip install python-dotenv selenium webdriver-manager
```

## Configuration

### Step 1: Create Environment File

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

### Step 2: Configure Environment Variables

Edit the `.env` file with your settings:

```ini
# ===========================================
# LIFETIME FITNESS CREDENTIALS
# ===========================================
LIFETIME_USERNAME=your_lifetime_email@example.com
LIFETIME_PASSWORD=your_lifetime_password

# Your Life Time club name
# Find your club name at: https://my.lifetime.life/view-all-clubs.html
# Examples:
#   San Antonio 281
#   Flower Mound
#   Plano
LIFETIME_CLUB_NAME=San Antonio 281

# Two-letter state abbreviation in ALL CAPS
# Examples: TX, CA, NY, FL, CO
LIFETIME_CLUB_STATE=TX

# ===========================================
# TARGET CLASS CONFIGURATION
# ===========================================
# Find all these values on your club's class schedule page:
#   https://my.lifetime.life/clubs/{state}/{club-name}/classes.html
#
# Example for San Antonio 281 (TX):
#   https://my.lifetime.life/clubs/tx/san-antonio-281/classes.html
#
# Example for Flower Mound (TX):
#   https://my.lifetime.life/clubs/tx/flower-mound/classes.html
#
# Note: The URL uses lowercase state and hyphenated club name

# Class name - partial match is supported (see "How Class Matching Works" below)
TARGET_CLASS=Pickleball

# Instructor's name as shown (typically "FirstName L" format, no period after initial)
TARGET_INSTRUCTOR=John D

# Target date in YYYY-MM-DD format
# Note: If RUN_ON_SCHEDULE=true, this is ignored and calculated as today + 8 days
TARGET_DATE=2025-01-15

# Class start and end times EXACTLY as shown on the schedule
# Format is typically "H:MM AM" or "HH:MM AM"
START_TIME=9:00 AM
END_TIME=10:00 AM

# ===========================================
# NOTIFICATION SETTINGS
# ===========================================
# Options: "email", "sms", or "both"
NOTIFICATION_METHOD=email

# ===========================================
# EMAIL CONFIGURATION
# Required for email notifications
# ===========================================
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_16_character_app_password
EMAIL_RECEIVER=recipient@example.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# ===========================================
# SMS CONFIGURATION (Optional - requires Twilio account)
# Only required if NOTIFICATION_METHOD is "sms" or "both"
# ===========================================
# Sign up at: https://www.twilio.com/try-twilio
# Requires A2P 10DLC registration for US numbers

# Your Twilio credentials (from https://console.twilio.com)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here

# Your Twilio phone number (format: +1XXXXXXXXXX)
TWILIO_FROM_NUMBER=+15551234567

# Your personal phone number to receive SMS (format: +1XXXXXXXXXX)
SMS_NUMBER=+15559876543

# ===========================================
# BOT BEHAVIOR
# ===========================================
# Run browser without GUI (set to "false" for debugging)
HEADLESS=true

# If "true", calculates TARGET_DATE as today + 8 days
# If "false", uses the TARGET_DATE value specified above
RUN_ON_SCHEDULE=false

# Target time configuration (only used when RUN_ON_SCHEDULE=true)
# Use local time + timezone - DST is handled automatically
TARGET_LOCAL_TIME=10:00:00
TIMEZONE=America/Chicago
```

## Email Setup (Gmail)

To send notifications via Gmail, you need to create an App Password:

1. **Enable 2-Step Verification** (required for App Passwords):
   - Go to [Google Account Security](https://myaccount.google.com/security)
   - Click on "2-Step Verification"
   - Follow the prompts to enable it

2. **Generate an App Password**:
   - Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
   - Select "Mail" as the app
   - Select your device type
   - Click "Generate"
   - Copy the 16-character password (no spaces)

3. **Use the App Password**:
   - Set `EMAIL_PASSWORD` in your `.env` file to the 16-character App Password
   - Do NOT use your regular Gmail password

## SMS Notification Setup (Optional)

SMS notifications require a [Twilio](https://www.twilio.com) account. If you don't want to set up Twilio, simply use `NOTIFICATION_METHOD=email` and skip this section.

### Twilio Setup

1. **Create a Twilio account** at https://www.twilio.com/try-twilio

2. **Complete A2P 10DLC registration** (required for US numbers):
   - Go to **Messaging** → **Senders** → **Brands** → Register as Sole Proprietor
   - Create a Campaign and associate your phone number
   - Note: Registration may take a few days for approval

3. **Get your credentials** from https://console.twilio.com:
   - Account SID (starts with `AC`)
   - Auth Token
   - Purchase a local phone number with SMS capability

4. **Configure environment variables**:
   ```ini
   NOTIFICATION_METHOD=sms  # or "both" for email + SMS
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token_here
   TWILIO_FROM_NUMBER=+15551234567
   SMS_NUMBER=+15559876543
   ```

### Twilio Costs

- ~$1.15/month for a local phone number
- ~$0.0079 per SMS message
- ~$4 one-time brand registration fee
- A2P campaign fees may apply

## Usage

### Running Locally

After installation and configuration:

```bash
# Run the bot
python -m lifetime_bot

# Or use the console script (if installed with pip install -e .)
lifetime-bot
```

### Running with Specific Settings

You can override environment variables at runtime:

```bash
# Run in non-headless mode (see browser actions)
HEADLESS=false python -m lifetime_bot

# Override target date
TARGET_DATE=2025-02-01 python -m lifetime_bot

# Run immediately without waiting for scheduled time
RUN_ON_SCHEDULE=false python -m lifetime_bot
```

### What the Bot Does

1. **Waits for target time** (if `RUN_ON_SCHEDULE=true`): Converts `TARGET_LOCAL_TIME` to UTC (handling DST automatically) and sleeps until that time
2. **Logs into Life Time**: Uses Selenium to authenticate with your credentials
3. **Navigates to schedule**: Opens the class schedule for your club and target date
4. **Finds target class**: Searches for the class matching your criteria (name, instructor, time)
5. **Reserves the class**: Clicks the Reserve button (or Add to Waitlist if full)
6. **Handles waivers**: For classes like Pickleball, accepts the waiver automatically
7. **Sends notification**: Emails/texts you the result (success, failure, or already reserved)
8. **Retries on failure**: Attempts up to 3 times with 30-second delays between retries

## GitHub Actions (Automated Scheduling)

The bot can run automatically using GitHub Actions.

### Workflow Schedule

The default schedule in `.github/workflows/bot.yml`:
- **When**: 15:30 UTC (9:30 AM CST) Sunday through Thursday
- **Cron**: `30 15 * * 0-4`

This timing is designed to reserve classes 8 days in advance when registration opens.

### Setting Up GitHub Actions

1. **Fork or push this repository to GitHub**

2. **Add Repository Secrets** (Settings → Secrets and variables → Actions → Secrets):

   | Secret Name | Description |
   |-------------|-------------|
   | `EMAIL_SENDER` | Your Gmail address |
   | `EMAIL_PASSWORD` | Your Gmail App Password |
   | `EMAIL_RECEIVER` | Email to receive notifications |
   | `SMTP_SERVER` | SMTP server (default: smtp.gmail.com) |
   | `SMTP_PORT` | SMTP port (default: 587) |
   | `LIFETIME_USERNAME` | Your Life Time email |
   | `LIFETIME_PASSWORD` | Your Life Time password |
   | `TWILIO_ACCOUNT_SID` | Twilio Account SID (optional, for SMS) |
   | `TWILIO_AUTH_TOKEN` | Twilio Auth Token (optional, for SMS) |
   | `TWILIO_FROM_NUMBER` | Twilio phone number (optional, for SMS) |
   | `SMS_NUMBER` | Your phone number (optional, for SMS) |

3. **Add Repository Variables** (Settings → Secrets and variables → Actions → Variables):

   | Variable Name | Description |
   |---------------|-------------|
   | `LIFETIME_CLUB_NAME` | Your club name |
   | `LIFETIME_CLUB_STATE` | Two-letter state code |
   | `TARGET_CLASS` | Class name |
   | `TARGET_INSTRUCTOR` | Instructor name |
   | `TARGET_DATE` | Target date (if not using schedule) |
   | `START_TIME` | Class start time |
   | `END_TIME` | Class end time |
   | `HEADLESS` | `true` (always for CI) |
   | `RUN_ON_SCHEDULE` | `true` for automatic date calculation |
   | `NOTIFICATION_METHOD` | `email`, `sms`, or `both` |
   | `TARGET_LOCAL_TIME` | Local time to run (e.g., `10:00:00`) |
   | `TIMEZONE` | IANA timezone (e.g., `America/Chicago`) |

4. **Create Environments** (Settings → Environments):
   - Create `dev` environment for testing
   - Create `prod` environment for scheduled runs
   - Each environment can have different variable values

### Manual Trigger

You can manually run the workflow:
1. Go to Actions → Lifetime Bot Automation
2. Click "Run workflow"
3. Select the environment (`dev` or `prod`)
4. Click "Run workflow"

## How Class Matching Works

The bot matches classes using these criteria (ALL must match):

1. **Class Name**: The `TARGET_CLASS` must be **contained** in the class title (case-insensitive)
2. **Instructor**: The `TARGET_INSTRUCTOR` must be **contained** in the class info (case-insensitive)
3. **Start Time**: Must exactly match `START_TIME` (e.g., "9:00 AM")
4. **End Time**: Must exactly match `END_TIME` (e.g., "10:00 AM")

### Partial Class Name Matching

`TARGET_CLASS` does **not** need to be the full class title. The bot checks if your value is contained within the actual class name. This allows flexibility:

| TARGET_CLASS | Matches |
|--------------|---------|
| `Pickleball` | "Pickleball Open Play", "Pickleball Skills & Drills" |
| `ALPHA CONDITIONING` | "ALPHA CONDITIONING: HINGE + PRESS", "ALPHA CONDITIONING: SQUAT + LUNGE" |
| `ALPHA STRENGTH` | "ALPHA STRENGTH: HINGE + PRESS", "ALPHA STRENGTH: SQUAT + LUNGE" |
| `GTX` | "GTX: HINGE + PRESS", "GTX: SQUAT + LUNGE" |
| `Yoga` | "Yoga Flow", "Power Yoga", "Yoga Sculpt" |

**Important**: Be specific enough to avoid matching the wrong class. For example:
- `ALPHA` alone would match both "ALPHA CONDITIONING" and "ALPHA STRENGTH" classes
- `ALPHA CONDITIONING` specifically targets only conditioning classes

### Finding Your Club Name

1. Go to the [Life Time Club Directory](https://my.lifetime.life/view-all-clubs.html)
2. Find your club in the list
3. Set `LIFETIME_CLUB_NAME` to the club name (e.g., `San Antonio 281`)
4. Set `LIFETIME_CLUB_STATE` to the two-letter state code in ALL CAPS (e.g., `TX`)

### Finding Class Details

1. Go to your club's class schedule page:
   ```
   https://my.lifetime.life/clubs/{state}/{club-name}/classes.html
   ```
   - `{state}` = lowercase state abbreviation (e.g., `tx`, `ca`, `ny`)
   - `{club-name}` = club name in lowercase with hyphens (e.g., `san-antonio-281`, `flower-mound`)

2. Example URLs:
   - San Antonio 281: `https://my.lifetime.life/clubs/tx/san-antonio-281/classes.html`
   - Flower Mound: `https://my.lifetime.life/clubs/tx/flower-mound/classes.html`
   - Plano: `https://my.lifetime.life/clubs/tx/plano/classes.html`

3. Find your target class on the schedule and note:
   - **Class name** exactly as shown (e.g., "Pickleball", "Yoga Flow", "HIIT")
   - **Instructor name** without the period after the initial (e.g., "John D" not "John D.")
   - **Start time** exactly as shown (e.g., "9:00 AM", "10:30 AM")
   - **End time** exactly as shown (e.g., "10:00 AM", "11:30 AM")

## Notification Messages

The bot sends different notifications based on the outcome:

| Subject | When |
|---------|------|
| `Lifetime Bot - Success` | Class successfully reserved |
| `Lifetime Bot - Already Reserved` | Class was already reserved or on waitlist |
| `Lifetime Bot - Failure` | Failed to reserve (includes error details) |
| `Lifetime Bot - All Attempts Failed` | Failed after 3 retry attempts |

Each notification includes:
- Class name
- Instructor
- Date
- Time
- Error message (if applicable)

## Troubleshooting

### Common Issues

**Login Failures**
- Verify your Life Time credentials are correct
- Check if your account requires captcha or 2FA
- Try logging in manually on the website first

**Class Not Found**
- Verify the class name, instructor, and time match EXACTLY
- Check that the class exists on the target date
- Ensure `LIFETIME_CLUB_NAME` and `LIFETIME_CLUB_STATE` are correct

**Email Notification Failures**
- Use a Gmail App Password, not your regular password
- Verify `EMAIL_SENDER` and `EMAIL_RECEIVER` are valid emails
- Check that 2-Step Verification is enabled on your Google account

**SMS Notification Failures**
- Verify your Twilio credentials are correct
- Ensure A2P 10DLC registration is complete and approved
- Check Twilio console logs for error codes
- Verify phone numbers use E.164 format (+1XXXXXXXXXX)

**WebDriver Errors**
- Ensure Chrome is installed on your system
- The `webdriver-manager` package handles ChromeDriver automatically
- Try running with `HEADLESS=false` to see what's happening

### Debugging Tips

1. **Run with visible browser**:
   ```bash
   HEADLESS=false python -m lifetime_bot
   ```

2. **Check GitHub Actions logs**:
   - Go to Actions → Select workflow run → Click on job → View logs

3. **Test notifications separately**:
   ```python
   from lifetime_bot.config import BotConfig, EmailConfig
   from lifetime_bot.notifications import EmailNotificationService

   config = EmailConfig.from_env()
   service = EmailNotificationService(config)
   service.send("Test Subject", "Test message body")
   ```

## Development

### Installing Development Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- `ruff` - Linting and formatting
- `pytest` - Testing
- `pytest-cov` - Test coverage

### Running the Linter

```bash
python -m ruff check src/
python -m ruff format src/
```

### Project Architecture

The codebase follows a modular architecture:

- **`config.py`**: Dataclasses for configuration (`BotConfig`, `EmailConfig`, `SMSConfig`, `ClassConfig`, `ClubConfig`)
- **`bot.py`**: Main `LifetimeReservationBot` class with all reservation logic
- **`notifications/`**: Abstract `NotificationService` with email and SMS implementations
- **`webdriver/`**: Selenium WebDriver factory function
- **`utils/timing.py`**: UTC time waiting and date calculation utilities
- **`__main__.py`**: CLI entry point with retry logic

## Security Notes

- **Never commit your `.env` file** - It contains sensitive credentials
- **Use GitHub Secrets** for CI/CD - Never put passwords in workflow files
- **Rotate credentials regularly** - Especially email App Passwords
- **Review the code** - Understand what automation you're running on your accounts

## License

MIT License

# Lifetime Fitness Class Reservation Bot

A Python-based automation bot that reserves classes at Lifetime Fitness, running on GitHub Actions.

## Overview
This bot automatically reserves classes at Lifetime Fitness by:
- Logging in to your Lifetime account
- Navigating to the class schedule
- Finding and reserving your specified class
- Sending email confirmations of success/failure
- Running on a schedule via GitHub Actions

## Setup

### 1. Fork this Repository

### 2. Configure GitHub Secrets
Add the following secrets to your repository (Settings → Secrets and variables → Actions):

```ini
# Lifetime Credentials
LIFETIME_USERNAME=your_lifetime_email
LIFETIME_PASSWORD=your_lifetime_password

# Class Details
TARGET_CLASS=Pickleball
TARGET_INSTRUCTOR=Instructor Name
TARGET_DATE=YYYY-MM-DD
START_TIME=8:30 PM
END_TIME=10:00 PM

# Email Configuration
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_specific_password
EMAIL_RECEIVER=your_email@gmail.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# Bot Configuration
HEADLESS=true
RUN_ON_SCHEDULE=true
```

### 3. Email Setup
1. Use a Gmail account
2. Enable 2-Step Verification in your Google Account
3. Generate an App Password:
   - Go to Google Account Settings → Security
   - Under "2-Step Verification", scroll to "App passwords"
   - Generate a new app password
   - Use this password for EMAIL_PASSWORD in GitHub Secrets

## Scheduling
The bot runs automatically via GitHub Actions:
- Schedule: 10:00 UTC Sunday through Thursday (`0 10 * * 0-4`)
- Can also be triggered manually through GitHub Actions interface

## Local Development

### Requirements
- Python 3.9+
- Chrome browser
- Required packages: `selenium`, `python-dotenv`, `webdriver-manager`

### Local Setup
1. Clone the repository
2. Create a `.env` file with the same variables as GitHub Secrets
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run locally:
   ```bash
   python lifetime_bot.py
   ```

## Troubleshooting
- Check GitHub Actions logs for execution details
- Email notifications will be sent for both successful and failed reservations
- For local testing, set `HEADLESS=false` to watch the automation in action

## Security Note
- Never commit your `.env` file
- Always use GitHub Secrets for sensitive information
- Regularly rotate your email app password

## License
MIT License

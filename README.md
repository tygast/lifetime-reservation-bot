# Lifetime Fitness Reservation Bot

An automated bot that helps you reserve classes at Life Time Fitness clubs. The bot can be scheduled to run at specific times to secure your spot in popular classes as soon as they become available.

## Features

- Automatically logs into your Life Time Fitness account
- Navigates to the class schedule for your preferred club
- Finds and reserves your target class based on class name, instructor, and time
- Handles waitlist scenarios
- Sends notifications via email and/or SMS about reservation status
- Can be scheduled to run at specific times (e.g., when registration opens)

## Requirements

- Python 3.7+
- Chrome browser
- Selenium WebDriver
- Gmail account (or other email provider) for sending notifications

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/lifetime-bot.git
   cd lifetime-bot
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv .venv
   
   # On Windows:
   .venv\Scripts\activate
   
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project directory with your configuration (see Configuration section below)

## Configuration

Create a `.env` file with the following variables:

```ini
# Lifetime Credentials
LIFETIME_USERNAME=your_lifetime_email
LIFETIME_PASSWORD=your_lifetime_password
LIFETIME_CLUB_NAME=your_club_name
LIFETIME_CLUB_STATE=your_club_state

# Class Details
TARGET_CLASS=your_class_name
TARGET_INSTRUCTOR=your_instructor_name
TARGET_DATE=YYYY-MM-DD
START_TIME=your_start_time
END_TIME=your_end_time

# Notification Method
# Options: "email", "sms", or "both"
NOTIFICATION_METHOD=email

# Email Configuration
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_specific_password
EMAIL_RECEIVER=your_email@gmail.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# SMS Configuration (for carrier gateway)
SMS_NUMBER=1234567890  # Your phone number without any formatting
SMS_CARRIER=verizon    # Your carrier from the supported list

# Bot Configuration
HEADLESS=true
RUN_ON_SCHEDULE=true
```

## Email Setup

1. Use a Gmail account
2. Enable 2-Step Verification in your Google Account
3. Generate an App Password:
   - Go to Google Account Settings → Security
   - Under "2-Step Verification", scroll to "App passwords"
   - Generate a new app password
   - Use this password for EMAIL_PASSWORD in your `.env` file

## SMS Notification Setup

The bot uses email-to-SMS gateways provided by mobile carriers to send text messages. No additional accounts or services are required beyond your existing email setup.

### Supported SMS Carriers

The following carriers are supported for SMS notifications:

- `att` - AT&T
- `tmobile` - T-Mobile
- `verizon` - Verizon
- `sprint` - Sprint
- `boost` - Boost Mobile
- `cricket` - Cricket Wireless
- `metro` - Metro by T-Mobile
- `uscellular` - US Cellular
- `virgin` - Virgin Mobile
- `xfinity` - Xfinity Mobile
- `googlefi` - Google Fi

To use SMS notifications:
1. Set `NOTIFICATION_METHOD` to either `sms` or `both` in your `.env` file
2. Set `SMS_NUMBER` to your phone number (digits only, no formatting)
3. Set `SMS_CARRIER` to your carrier from the supported list

## Scheduling
The bot runs automatically via GitHub Actions:
- Schedule: 10:00 UTC Sunday through Thursday (`0 10 * * 0-4`)
- Can also be triggered manually through GitHub Actions interface

### Running at a Specific UTC Time

The bot includes functionality to wait until a specific UTC time before running. This is useful for ensuring the bot runs exactly when class registration opens.

The default time is set to 16:00:00 UTC. You can modify this in the `lifetime_bot.py` file:

```python
if __name__ == "__main__":
    wait_until_utc("16:00:00")  # Change this to your desired UTC time
```

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

### Common Issues

1. **Login Failures**: Ensure your Life Time Fitness credentials are correct in the `.env` file.

2. **Class Not Found**: Verify the class name, instructor, and time match exactly what's shown on the Life Time website.

3. **Email Notification Failures**: 
   - For Gmail, you need to use an App Password instead of your regular password
   - Enable "Less secure app access" or use 2FA with app passwords

4. **SMS Notification Failures**:
   - Verify your phone number is entered correctly without any formatting
   - Ensure you've selected the correct carrier

- Check GitHub Actions logs for execution details
- Email/SMS notifications will be sent for both successful and failed reservations
- For local testing, set `HEADLESS=false` to watch the automation in action

## Security Note
- Never commit your `.env` file
- Always use GitHub Secrets for sensitive information
- Regularly rotate your email app password

## License
MIT License

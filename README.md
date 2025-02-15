# Lifetime Class Reservation Bot

## Overview
This bot automates the reservation of fitness classes at Lifetime Fitness using Selenium. It logs into the Lifetime website, navigates to the class schedule, finds the desired class based on time and instructor, and completes the reservation process.

## Features
- Logs into Lifetime Fitness using credentials from a `.env` file.
- Searches for a specified class by name, time, and instructor.
- Clicks the "Reserve" or "Add to Waitlist" button.
- Selects the waiver agreement (if required) and clicks "Finish" to confirm the reservation.
- Runs on a schedule if `RUN_ON_SCHEDULE=true`.
- Sends an email notification upon success or failure of the reservation.

## Requirements
- Python 3.x
- Google Chrome
- ChromeDriver

## Installation
1. Clone this repository:
   ```bash
   git clone https://github.com/your-repo/lifetime-bot.git
   cd lifetime-bot
   ```

2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root and add the following variables:
   ```ini
   LIFETIME_USERNAME=your_username
   LIFETIME_PASSWORD=your_password
   CLASS_SCHEDULE=Pickleball Open Play: All Levels
   START_TIME=8:30 PM
   END_TIME=10:00 PM
   TARGET_DATE=YYYY-MM-DD
   TARGET_INSTRUCTOR=Ashlyn M.
   RUN_ON_SCHEDULE=true  # Set to false if you don't want scheduled execution
   EMAIL_SENDER=your_email@example.com
   EMAIL_RECEIVER=your_email@example.com
   EMAIL_PASSWORD=your_email_password
   ```

## Usage
To run the bot manually:
```bash
python lifetime_reservation.py
```

### Running in Headless Mode
To run the script in headless mode (no browser window):
1. Open `lifetime_reservation.py`
2. Locate the `options` configuration for `webdriver.ChromeOptions()`
3. Add the following line:
   ```python
   options.add_argument("--headless")
   ```
4. Save and run the script.

### Scheduled Execution
If `RUN_ON_SCHEDULE=true`, the bot will:
- Run **only on Sunday through Thursday**.
- Look for a class **8 days from the current date**.
- Run exactly **1 hour after the `END_TIME`**.

### Email Notifications
The bot sends an email upon success or failure of a class reservation.

## Troubleshooting
- If the bot fails to find a class, check `schedule_page.html` for debugging.
- If elements are not clickable, ensure the webpage has fully loaded.
- If running in headless mode, try without `--headless` to see any UI-related issues.

## Contributing
Feel free to submit issues or pull requests to improve this bot.

## License
This project is licensed under the MIT License.
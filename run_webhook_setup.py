import asyncio
import os
import sys # Import sys to allow graceful exit

# For quick local test, replace with your actual values temporarily
# (These should be loaded from your system's environment variables in a real setup,
# but for this one-time script, direct assignment is fine if you're careful)
# Make sure these match the ones you set on Render!
os.environ['TELEGRAM_BOT_TOKEN'] = '7681834277:AAGHULOuNagEvMtUwzKgAzKDjvV3PrUIzRk' # REPLACE THIS
os.environ['WEBHOOK_URL'] = 'https://starsexchangrbot.onrender.com' # REPLACE WITH YOUR ACTUAL RENDER URL

# Import the function from your Stars.py
try:
    from Stars import set_telegram_webhook
except ImportError:
    print("Error: Could not import set_telegram_webhook from Stars.py. Make sure Stars.py is in the same directory.")
    sys.exit(1)


if __name__ == "__main__":
    print("Attempting to set webhook...")
    asyncio.run(set_telegram_webhook())
    print("Webhook setup script finished.")
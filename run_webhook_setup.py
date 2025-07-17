import asyncio
import os
import sys

# Ensure these environment variables are set for the script to run
# On Render, these come from your service's environment variables.
# Locally, you might set them directly here or use a .env file.
if 'TELEGRAM_BOT_TOKEN' not in os.environ:
    print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
    sys.exit(1)
if 'WEBHOOK_URL' not in os.environ:
    print("Error: WEBHOOK_URL environment variable not set.")
    sys.exit(1)

# Import the function from your Stars.py
try:
    from Stars import set_telegram_webhook_command # Corrected import
except ImportError:
    print("Error: Could not import set_telegram_webhook_command from Stars.py. Make sure Stars.py is in the same directory.")
    sys.exit(1)

if __name__ == "__main__":
    print("Attempting to set webhook...")
    asyncio.run(set_telegram_webhook_command()) # Corrected function call
    print("Webhook setup script finished.")
import asyncio
import os
from dotenv import load_dotenv
from telegram.ext import Application
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from your local .env file
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RENDER_APP_URL = "https://starsexchangrbot.onrender.com" # Your Render app's primary URL

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is not set. Please check your local .env file.")
    exit(1)

# Construct the full webhook URL
WEBHOOK_URL_FOR_TELEGRAM = f"{RENDER_APP_URL}/telegram-webhook"

async def set_telegram_webhook():
    """Sets the Telegram webhook for the bot."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    try:
        logger.info(f"Attempting to set Telegram webhook to: {WEBHOOK_URL_FOR_TELEGRAM}")
        await app.bot.set_webhook(url=WEBHOOK_URL_FOR_TELEGRAM)
        logger.info("Telegram webhook has been successfully set!")
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")

if __name__ == "__main__":
    asyncio.run(set_telegram_webhook())
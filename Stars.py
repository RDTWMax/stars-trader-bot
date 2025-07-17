# Stars.py

import os
import asyncio
import sys
import logging
from flask import Flask, request, abort

# Import necessary components from python-telegram-bot
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes, # Ensure ContextTypes is imported for type hinting
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import configuration variables
try:
    from config import (
        TELEGRAM_BOT_TOKEN,
        FRAGMENTS_USERNAME,
        FRAGMENTS_PASSWORD,
        IPN_SECRET_KEY,
        WEBHOOK_URL, # This will be Render's URL in production
    )
except ImportError:
    logger.critical("Error: config.py not found or missing necessary variables.")
    logger.critical("Please ensure config.py is in the same directory and all required environment variables are set.")
    sys.exit(1)

# States for ConversationHandler (keep if you have it from your original bot logic)
SELECTING_ACTION, BUY_STARS_AMOUNT, GET_PAYMENT_METHOD, SELL_STARS_AMOUNT, SELL_GET_PAYOUT_METHOD, GET_WALLET_ADDRESS = range(6)


# --- Global Bot Application Setup ---
# 1. Build the Application object globally.
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# 2. Define your bot's command and message handlers (ensure these are 'async def' functions)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    # Your specific welcome message
    await update.message.reply_html(
        f"Hi {user.mention_html()}! Welcome to the Stars Trader Bot. 🤖"
        "\n\nI can help you buy and sell stars. What would you like to do?"
        # Example of how to add a simple reply keyboard if needed:
        # reply_markup=ReplyKeyboardMarkup([["Buy Stars", "Sell Stars"]], one_time_keyboard=True)
    )

async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echos the user's message. (Example handler, replace with your actual text message logic)"""
    logger.info(f"Received message from {update.effective_user.first_name}: {update.message.text}")
    await update.message.reply_text(f"I received your message: '{update.message.text}'")


# 3. Add handlers to the application object
application.add_handler(CommandHandler("start", start_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))

# If you have a ConversationHandler or other handlers, you would define them
# and add them to 'application' here, similar to how start_command is added.
# For example:
# conversation_handler = ConversationHandler(...) # Define your ConversationHandler
# application.add_handler(conversation_handler) # Add it to the application


# --- Initialize the Telegram Bot Application ---
# This part ensures the bot application is initialized.
# It runs once when the module is imported by Gunicorn.
try:
    asyncio.run(application.initialize())
    logger.info("Telegram bot application initialized globally and handlers loaded.")
except Exception as e:
    logger.critical(f"Failed to initialize Telegram bot application globally: {e}")
    logger.critical("This is crucial for the bot's operation. Exiting.")
    sys.exit(1)


# --- Flask App Setup ---
flask_app = Flask(__name__)

# Basic root path for Render health checks
@flask_app.route("/")
def index():
    logger.info("Accessed root path / (Health Check)")
    return "StarsExchangrBot is running!"

# Telegram Webhook Route - This is where Telegram sends updates
@flask_app.route("/telegram-webhook", methods=["POST"])
async def telegram_webhook():
    """Handle incoming Telegram updates from the webhook."""
    # This check is a safeguard; application should be initialized by now
    if not application.was_initialized:
        logger.error("Application not initialized when webhook received a request!")
        # Return a server error code, perhaps with a retry hint
        return "error: bot not ready", 503

    json_data = request.get_json()
    if not json_data:
        logger.warning("Received empty JSON data on webhook. Ignoring.")
        return "ok" # Telegram sometimes sends empty data/bad requests

    try:
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update) # This should now work!
        logger.info("Telegram webhook processed successfully.")
        return "ok"
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}", exc_info=True)
        return "error", 500

# --- IMPORTANT: REMOVED OLD main() AND if __name__ == "__main__": BLOCK ---
# The previous `main()` function and the `if __name__ == "__main__":` block
# are no longer needed because:
# 1. `application` is initialized globally.
# 2. Webhook setup is done by `run_webhook_setup.py`.
# 3. Gunicorn directly runs `flask_app`.
# Removing them prevents re-initialization conflicts and simplifies the deployment.
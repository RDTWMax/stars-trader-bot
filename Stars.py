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

# Add a debug print to confirm file import by Gunicorn
print("DEBUG: Stars.py is being imported by Gunicorn and running!")

# --- ENVIRONMENT VARIABLES: IMPORTANT CHANGE HERE ---
# Variables MUST be loaded from os.getenv() for Render deployment.
# You will set these in your Render dashboard under the Environment tab for your service.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FRAGMENTS_USERNAME = os.getenv("FRAGMENTS_USERNAME")
FRAGMENTS_PASSWORD = os.getenv("FRAGMENTS_PASSWORD")
IPN_SECRET_KEY = os.getenv("IPN_SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # This will be Render's URL + /telegram-webhook

# --- Check for missing essential environment variables ---
if not TELEGRAM_BOT_TOKEN:
    logger.critical("Error: TELEGRAM_BOT_TOKEN is not set in environment variables. Bot cannot function.")
    # Do NOT sys.exit(1) here if this file is imported by Gunicorn, as it will crash the web server.
    # Instead, the application will just not be initialized.
    # sys.exit(1) # Removed sys.exit(1) for Gunicorn compatibility

if not all([FRAGMENTS_USERNAME, FRAGMENTS_PASSWORD]):
    logger.warning("Fragments credentials (FRAGMENTS_USERNAME or FRAGMENTS_PASSWORD) are not set. Fragments automation will not work.")

if not IPN_SECRET_KEY:
    logger.critical("Error: IPN_SECRET_KEY is not set. NOWPayments IPN verification will be insecure.")
    # sys.exit(1) # Removed sys.exit(1) for Gunicorn compatibility

if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL is not set. Webhook configuration will be skipped if set via script.")


# States for ConversationHandler (keep if you have it from your original bot logic)
SELECTING_ACTION, BUY_STARS_AMOUNT, GET_PAYMENT_METHOD, SELL_STARS_AMOUNT, SELL_GET_PAYOUT_METHOD, GET_WALLET_ADDRESS = range(6)


# --- Global Bot Application Setup ---
# Build the Application object globally.
# It will be initialized later.
application = None # Initialize as None, set in initialize_bot_application

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


# --- Initialize the Telegram Bot Application Function ---
# This function initializes the Telegram bot Application and adds handlers.
# It should be called when the module is loaded by Gunicorn.
async def initialize_bot_application():
    global application
    if application is None: # Ensures it's only initialized once
        if not TELEGRAM_BOT_TOKEN:
            logger.critical("!!! TELEGRAM_BOT_TOKEN is not set. Bot cannot initialize. !!!")
            return None

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Add handlers to the application object
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))

        # IMPORTANT: Re-add your ConversationHandler and other specific handlers here!
        # Example:
        # application.add_handler(
        #     ConversationHandler(
        #         entry_points=[CommandHandler("buy", buy_stars_entry), CommandHandler("sell", sell_stars_entry)],
        #         states={
        #             # ... your states and handlers for buying/selling ...
        #         },
        #         fallbacks=[CommandHandler("cancel", cancel_command)],
        #     )
        # )
        # application.add_handler(CommandHandler("anothercommand", another_command_handler))

        await application.initialize() # Initialize the application
        logger.info("Telegram bot application initialized globally and handlers loaded.")
    return application

# Call initialize_bot_application when the module is loaded by Gunicorn
# This will run in a separate asyncio loop managed by Gunicorn for async Flask views
# We need to ensure this is called, but not directly in the global scope if it's an async func.
# Gunicorn's ASGI/WSGI server will handle the async context.
# For now, we'll rely on the webhook route to trigger initialization if needed,
# or ensure it's initialized via a sync wrapper if truly needed before first request.
# Let's simplify and let the webhook route handle the `was_initialized` check.

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
    global application
    # Ensure application is initialized before processing updates
    if application is None:
        logger.info("Telegram Application not yet initialized. Initializing now...")
        await initialize_bot_application() # Initialize if not already

    # This check is a safeguard; application should be initialized by now
    if not application._initialized: # Corrected attribute name
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

# --- Webhook Setup Function (for the build command) ---
async def set_telegram_webhook_command():
    """
    Sets the Telegram webhook to the deployed Render URL.
    This function is designed to be called by the Render build command.
    """
    current_application = await initialize_bot_application() # Ensure application is initialized
    if current_application is None:
        logger.critical("Bot application failed to initialize for webhook setup. Cannot set webhook.")
        sys.exit(1) # Exit build if this critical step fails

    if WEBHOOK_URL: # This WEBHOOK_URL will be provided by Render
        full_webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
        logger.info(f"Attempting to set Telegram webhook to: {full_webhook_url}")
        try:
            await current_application.bot.set_webhook(url=full_webhook_url)
            logger.info("Telegram webhook command sent successfully.")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}", exc_info=True)
            sys.exit(1) # Fail build if webhook can't be set
    else:
        logger.warning("WEBHOOK_URL environment variable is not set. Cannot configure webhook.")
        sys.exit(1) # Fail build if WEBHOOK_URL is missing for webhook setup

# --- Local Development/Webhook Setup Execution (for your local machine, or if called directly) ---
if __name__ == "__main__":
    # This block is primarily for local testing or manual webhook setup.
    # When deployed with Gunicorn, this block is typically NOT executed.

    logger.info("Running Stars.py in __main__ block. Attempting to set webhook for local test/manual setup.")
    asyncio.run(set_telegram_webhook_command())
    logger.info("Webhook setup attempt finished.")

    # Note: For local development with polling, you would add application.run_polling() here.
    # However, for Render, we use webhooks, so polling is not used.
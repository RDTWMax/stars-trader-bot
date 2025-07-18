# Stars.py
import os
import asyncio
import sys
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes, # Ensure ContextTypes is imported for type hinting
)

# Import configuration from config.py
import config

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Add a debug print to confirm file import by Gunicorn
print("DEBUG: Stars.py is being imported by Gunicorn and running!")

# --- Check for missing essential environment variables ---
# The checks are now implicitly handled by config.py, but we can add explicit checks here for clarity at startup.
if not config.TELEGRAM_BOT_TOKEN:
    logger.critical("Error: TELEGRAM_BOT_TOKEN is not set in environment variables. Bot cannot function.")

if not all([config.FRAGMENTS_USERNAME, config.FRAGMENTS_PASSWORD]):
    logger.warning("Fragments credentials (FRAGMENTS_USERNAME or FRAGMENTS_PASSWORD) are not set. Fragments automation will not work.")

if not config.IPN_SECRET_KEY:
    logger.critical("Error: IPN_SECRET_KEY is not set. NOWPayments IPN verification will be insecure.")

if not config.WEBHOOK_URL:
    logger.warning("WEBHOOK_URL is not set. Webhook configuration will be skipped if set via script.")

# --- Global Bot Application & Flask App ---
# `application` will be initialized once by the web server workers.
# `flask_app` is the entry point for Gunicorn on Render.
application: Application | None = None
flask_app = Flask(__name__)

# --- Telegram Bot Handlers ---
# (These are placeholders for your bot's logic)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    await update.message.reply_text("Hello! I am your bot. Ready to go!")

async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echoes the user's message."""
    await update.message.reply_text(f"You said: {update.message.text}")

# --- Core Application Logic ---

async def initialize_bot_application():
    """Initializes the global bot application object safely."""
    global application
    if application is None: # Ensures it's only initialized once
        if not config.TELEGRAM_BOT_TOKEN:
            logger.critical("!!! TELEGRAM_BOT_TOKEN is not set. Bot cannot initialize. !!!")
            return None
        
        try:
            app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

            # Add handlers to the application object
            app.add_handler(CommandHandler("start", start_command))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))
            # IMPORTANT: Add your ConversationHandler and other handlers here!

            await app.initialize() # Initialize the application
            application = app # Assign to global only on success
            logger.info("Telegram bot application initialized globally and handlers loaded.")
        except Exception as e:
            logger.critical(f"Failed to initialize bot application: {e}", exc_info=True)
            application = None # Ensure it remains None on failure
    return application

# Call initialize_bot_application when the module is loaded by Gunicorn.
# This ensures the bot is ready before the first request comes in.
asyncio.run(initialize_bot_application())

# --- Webhook Routes ---

@flask_app.route("/")
def index():
    """A simple health check endpoint for Render, as defined in render.yaml."""
    return "Bot is running!", 200

@flask_app.route("/telegram-webhook", methods=["POST"])
async def telegram_webhook():
    """Handle incoming Telegram updates from the webhook."""
    global application
    if application is None:
        logger.error("Application is not initialized. Cannot process webhook request.")
        return "error: bot not ready", 503

    try:
        json_data = request.get_json()
        if not json_data:
            logger.warning("Received empty/invalid JSON on webhook. Ignoring.")
            return "ok", 200

        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return "ok", 200
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}", exc_info=True)
        return "error", 500

# --- Webhook Setup Command (for Render build) ---

async def set_telegram_webhook_command():
    """
    A command-line function to set the Telegram webhook.
    This is executed by the `buildCommand` in render.yaml.
    """
    logger.info("Running webhook setup command...")
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is not set. Cannot set webhook.")
        sys.exit(1)

    # Use a temporary application object for this setup task.
    temp_app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    if config.WEBHOOK_URL:
        full_webhook_url = f"{config.WEBHOOK_URL}/telegram-webhook"
        logger.info(f"Attempting to set Telegram webhook to: {full_webhook_url}")
        try:
            await temp_app.bot.set_webhook(url=full_webhook_url, allowed_updates=Update.ALL_TYPES)
            logger.info("Telegram webhook has been successfully set!")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}", exc_info=True)
            sys.exit(1) # Exit build if this critical step fails
    else:
        logger.warning("WEBHOOK_URL is not set. Skipping webhook setup.")

# This block is for local testing and will not run on Gunicorn
if __name__ == "__main__":
    logger.info("Running bot in local polling mode for testing...")
    if application:
        logger.info("Starting bot with polling...")
        application.run_polling()
    else:
        logger.critical("Application could not be initialized. Cannot start polling.")

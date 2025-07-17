# Stars.py - CLEANED FOR RENDER DEPLOYMENT

import os
import threading
import asyncio
import hmac
import hashlib
import sys
import logging
from flask import Flask, request, abort

# waitress is no longer needed for Render deployment, Gunicorn will be used.
# --- SELENIUM IMPORTS REMOVED ---
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Import necessary components from python-telegram-bot
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO, # Changed to INFO, you can set to DEBUG for more verbose logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
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
    sys.exit(1) # Exit immediately if critical variable is missing

if not all([FRAGMENTS_USERNAME, FRAGMENTS_PASSWORD]):
    logger.warning("Fragments credentials (FRAGMENTS_USERNAME or FRAGMENTS_PASSWORD) are not set. Fragments automation will not work.")

if not IPN_SECRET_KEY:
    logger.critical("Error: IPN_SECRET_KEY is not set. NOWPayments IPN verification will be insecure. Exiting.")
    sys.exit(1)

if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL is not set. Webhook configuration will be skipped if set via script.")

# States for ConversationHandler
SELECTING_ACTION, BUY_STARS_AMOUNT, GET_PAYMENT_METHOD, SELL_STARS_AMOUNT, SELL_GET_PAYOUT_METHOD, GET_WALLET_ADDRESS = range(6)

# Flask app setup - This variable 'flask_app' will be served by Gunicorn
flask_app = Flask(__name__)

# Global variable for the Telegram Application instance
# This will be initialized by initialize_bot_application()
application = None

# --- Flask Routes ---
@flask_app.route('/')
def home():
    """Health check endpoint for Render."""
    logger.info("Accessed root path / (Health Check)")
    return "Bot service is running!", 200

@flask_app.route("/nowpayments-ipn", methods=["POST"])
def nowpayments_ipn():
    """
    Receives the webhook from NOWPayments.
    Schedules a job with the bot's job_queue.
    """
    if 'x-nowpayments-sig' not in request.headers:
        logger.warning("NOWPayments IPN: Missing X-Nowpayments-Sig header.")
        abort(400) # Bad Request

    try:
        signature = hmac.new(key=IPN_SECRET_KEY.encode('utf-8'), msg=request.data, digestmod=hashlib.sha512).hexdigest()
        if signature != request.headers['x-nowpayments-sig']:
            logger.warning(f"NOWPayments IPN: Signature mismatch. Expected: {signature}, Received: {request.headers['x-nowpayments-sig']}")
            abort(401) # Unauthorized

        data = request.get_json()
        if not data:
            logger.warning("NOWPayments IPN: Received POST with no JSON data or invalid JSON.")
            abort(400)

        logger.info(f"Received validated NOWPayments IPN: {data}")
        payment_status = data.get("payment_status")
        order_id = data.get('order_id')
        pay_address = data.get('pay_address') # Example of other data you might need

        # Ensure 'application' is initialized before trying to use its job_queue
        if application:
            if payment_status == 'finished':
                # Use application.loop.call_soon_threadsafe to schedule async function from sync context
                application.loop.call_soon_threadsafe(
                    application.job_queue.run_once, process_paid_notification, 0, data={'order_id': order_id, 'payment_data': data}
                )
                logger.info(f"Scheduled process_paid_notification for order ID: {order_id}")
            else:
                logger.info(f"NOWPayments IPN: Payment status '{payment_status}' received for order ID: {order_id}. Not 'finished', so not processing notification.")
        else:
            logger.error("Telegram bot 'application' not initialized when NOWPayments webhook received. Cannot schedule job.")
            abort(500, description="Bot not ready to process IPN.")
    except Exception as e:
        logger.error(f"Error processing NOWPayments IPN webhook: {e}", exc_info=True)
        abort(500, description="Internal server error processing IPN.")
    return "OK"

# --- SELENIUM-DEPENDENT FUNCTION REMOVED ---
# The 'purchase_stars_on_fragments' function has been removed
# because it relied on Selenium. If this functionality is critical,
# you will need to find an alternative method that does not involve
# browser automation, such as using an API if Fragments offers one,
# or reconsidering the bot's capabilities.
#
# def purchase_stars_on_fragments(...)
#    ... (selenium code was here) ...


async def process_paid_notification(context):
    """
    Process a paid notification from NOWPayments.
    This function should handle the logic after a payment is confirmed.
    Currently, it just logs the order ID.
    You will need to add your Stars fulfillment logic here,
    replacing the previous Selenium part with an alternative.
    """
    data = context.job.data
    order_id = data.get('order_id')
    payment_data = data.get('payment_data', {})
    logger.info(f"Processing paid notification for order ID: {order_id}. Payment data: {payment_data}")

    # --- IMPORTANT: Your Stars Fulfillment Logic Goes Here ---
    # This is where you'd typically:
    # 1. Update your database with the payment status.
    # 2. Trigger the actual delivery of Stars to the user.
    #    Since Selenium was removed, you'll need an alternative for Fragments automation.
    #    If there's a Fragments API, use it. Otherwise, this feature might need re-evaluation.
    # 3. Notify the user in Telegram that their payment is confirmed and Stars are being sent.
    # Example:
    # user_telegram_id = get_user_id_from_order_id(order_id) # You'd need a function for this
    # if user_telegram_id:
    #     await context.bot.send_message(chat_id=user_telegram_id, text=f"Payment for order {order_id} confirmed! Stars are on the way!")
    # else:
    #     logger.warning(f"Could not find Telegram user for order ID {order_id}.")

# --- Telegram bot handlers (mostly unchanged) ---
async def start(update: Update, context):
    reply_keyboard = [["Buy Stars ⭐", "Sell Stars 💸"], ["Help ❓"]]
    await update.message.reply_html(
        rf"Hi {update.effective_user.mention_html()}! Welcome to the Stars Trader Bot. 🤖",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return SELECTING_ACTION

async def help_command(update: Update, context):
    await update.message.reply_text("This is a fully automated bot for buying and selling Telegram Stars.\n\nFor support, please contact the administrator.")

async def buy_stars_start(update: Update, context):
    await update.message.reply_text("How many Stars ⭐ would you like to purchase?", reply_markup=ReplyKeyboardRemove())
    return BUY_STARS_AMOUNT

async def get_payment_method(update: Update, context):
    try:
        context.user_data["stars_amount"] = int(update.message.text)
        if context.user_data["stars_amount"] <= 0:
            await update.message.reply_text("Please enter a positive number of Stars.")
            return BUY_STARS_AMOUNT # Stay in the same state to re-ask
    except ValueError:
        await update.message.reply_text("That doesn't look like a valid number. Please enter how many Stars ⭐ you'd like to purchase (e.g., 100).")
        return BUY_STARS_AMOUNT # Stay in the same state to re-ask

    # NOTE: You'll need to integrate your NOWPayments invoice generation here
    # after the user selects a payment method.
    await update.message.reply_text("Please provide your payment method (e.g., 'NOWPayments', 'USDT').")
    return GET_PAYMENT_METHOD

async def sell_stars_start(update: Update, context):
    await update.message.reply_text("How many Stars ⭐ would you like to sell?")
    return SELL_STARS_AMOUNT

async def get_payout_method(update: Update, context):
    try:
        context.user_data['stars_amount'] = int(update.message.text)
        if context.user_data["stars_amount"] <= 0:
            await update.message.reply_text("Please enter a positive number of Stars.")
            return SELL_STARS_AMOUNT # Stay in the same state to re-ask
    except ValueError:
        await update.message.reply_text("That doesn't look like a valid number. Please enter how many Stars ⭐ you'd like to sell (e.g., 50).")
        return SELL_STARS_AMOUNT # Stay in the same state to re-ask

    await update.message.reply_text("Please provide your payout method (e.g., 'Bank Transfer', 'USDT Wallet').")
    return SELL_GET_PAYOUT_METHOD

async def get_wallet_address(update: Update, context):
    context.user_data['payout_method'] = update.message.text
    await update.message.reply_text("Please provide your wallet address or bank details for payout.")
    return GET_WALLET_ADDRESS

async def confirm_transaction(update: Update, context):
    context.user_data["final_input"] = update.message.text
    
    if "stars_amount" in context.user_data and "payment_method" not in context.user_data:
        # This branch handles 'Buy Stars' flow
        context.user_data["payment_method"] = context.user_data["final_input"]
        stars_amount = context.user_data["stars_amount"]
        recipient_username = update.effective_user.username
        
        await update.message.reply_text(
            f"You want to buy {stars_amount} Stars using {context.user_data['payment_method']}. "
            f"Stars will be sent to your Telegram account (@{recipient_username}).\n\n"
            "Confirm to proceed with payment generation. (Type 'Confirm' or 'Cancel')"
        )
        
        # --- IMPORTANT: Your Payment Generation (NOWPayments) Logic Goes Here ---
        # This is where you would typically:
        # 1. Generate a NOWPayments invoice (using their API).
        # 2. Store the order details in your database (linking user, amount, payment method, order ID from NOWPayments).
        # 3. Send the NOWPayments payment URL/QR code to the user.
        # 4. Await the IPN callback to process the payment (process_paid_notification).
        # The direct call to purchase_stars_on_fragments is removed.
        #
        # For now, this part of the flow will not actually generate a payment or fulfill Stars.
        # You'll need to re-implement this.
        
        await update.message.reply_text("Purchase flow initiated! (Note: Actual payment processing and Stars fulfillment logic needs to be re-implemented here after Selenium removal).")
        
        context.user_data.clear()
        return ConversationHandler.END

    elif "stars_amount" in context.user_data and "payout_method" in context.user_data and "wallet_address" not in context.user_data:
        # This branch handles 'Sell Stars' flow
        context.user_data["wallet_address"] = context.user_data["final_input"]

        stars_amount = context.user_data["stars_amount"]
        payout_method = context.user_data["payout_method"]
        wallet_address = context.user_data["wallet_address"]

        await update.message.reply_text(
            f"You want to sell {stars_amount} Stars. "
            f"Payout will be sent via {payout_method} to {wallet_address}.\n\n"
            "Please confirm this information. (Type 'Confirm' or 'Cancel')"
        )
        
        # --- IMPORTANT: Your Stars Receiving and Payout Logic Goes Here ---
        # This is where you'd typically:
        # 1. Provide your designated Telegram Stars address to the user.
        # 2. Monitor for incoming Stars.
        # 3. Once Stars are received, process the payout to the user's provided wallet/bank.
        
        await update.message.reply_text("Thank you for confirming! Please send the Stars to our designated address. Once received, your payout will be processed. (Note: Actual Stars receiving and payout logic needs to be implemented).")
        
        context.user_data.clear()
        return ConversationHandler.END

    else:
        logger.warning("An error occurred or missing information in confirm_transaction. User data cleared.")
        await update.message.reply_text("An error occurred or missing information. Please start again with /start.")
        context.user_data.clear()
        return ConversationHandler.END

# This function initializes the Telegram bot Application.
# It should be called when the module is loaded.
def initialize_bot_application():
    global application
    if application is None: # Ensures it's only initialized once
        if not TELEGRAM_BOT_TOKEN:
            logger.critical("!!! TELEGRAM_BOT_TOKEN is not set. Bot cannot initialize. !!!")
            return None

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                SELECTING_ACTION: [
                    MessageHandler(filters.Regex("^Buy Stars ⭐$"), buy_stars_start),
                    MessageHandler(filters.Regex("^Sell Stars 💸$"), sell_stars_start),
                    MessageHandler(filters.Regex("^Help \❓$"), help_command),
                ],
                BUY_STARS_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_payment_method)
                ],
                GET_PAYMENT_METHOD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_transaction)
                ],
                SELL_STARS_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_payout_method)
                ],
                SELL_GET_PAYOUT_METHOD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_wallet_address)
                ],
                GET_WALLET_ADDRESS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_transaction)
                ],
            },
            fallbacks=[CommandHandler("cancel", help_command)], # Changed to help_command as no explicit cancel handler was given
        )
        application.add_handler(conv_handler)
        logger.info("Telegram bot application initialized.")
    return application

# Call initialize_bot_application when the module is loaded.
# This ensures 'application' (the Telegram bot instance) is ready when Flask routes are called.
initialize_bot_application()

# Flask route for Telegram webhooks
@flask_app.route("/telegram-webhook", methods=["POST"])
async def telegram_webhook():
    if application is None:
        logger.error("Telegram bot 'application' not initialized for webhook processing. Aborting.")
        abort(500, description="Bot not ready for webhook.")
    
    try:
        # Get JSON update from request and convert to python-telegram-bot Update object
        update = Update.de_json(request.get_json(force=True), application.bot)
        # Process the update asynchronously
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}", exc_info=True)
        abort(500, description="Internal server error processing webhook.")
    return "OK"


# --- Webhook Setup Function (to be run ONCE manually after deployment) ---
async def set_telegram_webhook():
    """
    Sets the Telegram webhook to the deployed Render URL.
    This function should be run once after deployment, not as part of the Gunicorn start command.
    """
    current_application = initialize_bot_application()
    if current_application is None:
        logger.critical("Bot application failed to initialize for webhook setup. Exiting.")
        return

    if WEBHOOK_URL: # This WEBHOOK_URL will be provided by Render
        full_webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
        logger.info(f"Attempting to set Telegram webhook to: {full_webhook_url}")
        try:
            await current_application.bot.set_webhook(url=full_webhook_url)
            logger.info("Telegram webhook command sent successfully.")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}", exc_info=True)
    else:
        logger.warning("WEBHOOK_URL environment variable is not set. Cannot configure webhook.")


# --- Local Development/Webhook Setup Execution (for your local machine) ---
if __name__ == "__main__":
    # This block is for local development and one-time webhook setup.
    # When deployed with Gunicorn, this block is typically NOT executed.

    # Option 1: To set the webhook manually after deployment
    # You would typically run this as a separate Python script locally, or through a build hook on Render
    # if you want it automated, but for initial setup, manual is better.
    # Example: python -c "import asyncio; from Stars import set_telegram_webhook; asyncio.run(set_telegram_webhook())"
    
    # For initial local testing, if you wanted to test Flask app directly (without webhook):
    # flask_app.run(debug=True, port=5000)

    # For running the webhook setup locally for a fresh deployment
    logger.info("Running Stars.py in __main__ block. Attempting to set webhook for local test/manual setup.")
    asyncio.run(set_telegram_webhook())
    logger.info("Webhook setup attempt finished. If running on Render, Gunicorn serves the Flask app.")

    # Note: For local development with polling, you would re-introduce the bot.run_polling() logic here.
    # However, for Render, we use webhooks, so polling is not used.
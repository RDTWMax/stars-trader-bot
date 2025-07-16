# Stars.py

import os
import threading
import asyncio
import hmac
import hashlib
import sys
import logging
from flask import Flask, request, abort
# waitress is no longer needed for Render deployment, Gunicorn will be used.
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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

# States for ConversationHandler
SELECTING_ACTION, BUY_STARS_AMOUNT, GET_PAYMENT_METHOD, SELL_STARS_AMOUNT, SELL_GET_PAYOUT_METHOD, GET_WALLET_ADDRESS = range(6)

# Flask app setup - This variable 'flask_app' will be served by Gunicorn
flask_app = Flask(__name__)

# Global variable for the Telegram Application instance
# This will be initialized by initialize_bot_application()
application = None
# Add this simple test route
@flask_app.route('/')
def home():
    return "Bot service is running!"
@flask_app.route("/nowpayments-ipn", methods=["POST"])
def nowpayments_ipn():
    """
    Receives the webhook from NOWPayments.
    Schedules a job with the bot's job_queue.
    """
    if 'x-nowpayments-sig' not in request.headers:
        abort(400)
    try:
        signature = hmac.new(key=IPN_SECRET_KEY.encode(), msg=request.data, digestmod=hashlib.sha512).hexdigest()
        if signature != request.headers['x-nowpayments-sig']:
            logger.warning("Webhook signature mismatch.")
            abort(401)
        data = request.get_json()
        logger.info(f"Received webhook: {data}")
        payment_status = data.get("payment_status")
        order_id = data.get('order_id')

        # Ensure 'application' is initialized before trying to use its job_queue
        if payment_status == 'finished' and application:
            # Use application.loop.call_soon_threadsafe to schedule async function from sync context
            application.loop.call_soon_threadsafe(
                application.job_queue.run_once, process_paid_notification, 0, data={'order_id': order_id}
            )
        elif not application:
            logger.error("Telegram bot 'application' not initialized when webhook received.")
            abort(500)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        abort(500)
    return "OK"

def purchase_stars_on_fragments(stars_amount: int, recipient_username: str) -> bool:
    if not FRAGMENTS_USERNAME or not FRAGMENTS_PASSWORD:
        logger.error("Fragments credentials not set. Skipping purchase.")
        return False

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu") # Recommended for headless on Linux
    options.add_argument("--window-size=1920,1080") # Set a default window size

    # On Render, you will likely need to specify the path to chromedriver
    # or rely on a buildpack that provides it.
    # For local testing, you might use ChromeDriverManager:
    # from webdriver_manager.chrome import ChromeDriverManager
    # driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    
    # For Render, assume chromedriver is in PATH or specify it if necessary
    # Render's default environment often has Chrome/Chromedriver pre-installed
    driver = webdriver.Chrome(options=options)

    try:
        logger.info(f"Starting Fragments purchase for {stars_amount} stars...")
        driver.get("https://fragment.com/stars")
        wait = WebDriverWait(driver, 20)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Buy Stars')]"))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Log in by password')]"))).click()
        wait.until(EC.visibility_of_element_located((By.NAME, "username"))).send_keys(FRAGMENTS_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(FRAGMENTS_PASSWORD)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        logger.info("Logged into Fragments.")
        amount_input = wait.until(
            EC.visibility_of_element_located((By.ID, "star-amount"))
        )
        recipient_input = driver.find_element(By.ID, "star-recipient")
        amount_input.clear()
        amount_input.send_keys(str(stars_amount))
        recipient_input.clear()
        recipient_input.send_keys(recipient_username)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Confirm Purchase')]"))).click()
        logger.info("Purchase confirmed on Fragments.")
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[@class='modal-dialog']")))
        logger.info(f"Purchase modal closed, assuming success for {recipient_username}.")
        return True
    except (TimeoutException, NoSuchElementException) as e:
        logger.error(
            f"A Selenium error occurred during Fragments automation: {e.__class__.__name__}"
        )
        driver.save_screenshot("fragments_error.png") # This will save to the current working directory
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during Fragments automation: {e}")
        driver.save_screenshot("fragments_error.png")
        return False
    finally:
        driver.quit()


async def process_paid_notification(context):
    """
    Process a paid notification from NOWPayments.
    This function should handle the logic after a payment is confirmed.
    Currently, it just logs the order ID.
    """
    data = context.job.data
    order_id = data.get('order_id')
    logger.info(f"Processing paid notification for order ID: {order_id}")
    # Add your logic here to process the payment, e.g., fulfill the Stars order.

# Telegram bot handlers
async def start(update, context):
    reply_keyboard = [["Buy Stars ⭐", "Sell Stars 💸"], ["Help ❓"]]
    await update.message.reply_html(
        rf"Hi {update.effective_user.mention_html()}! Welcome to the Stars Trader Bot. 🤖",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    return SELECTING_ACTION


async def help_command(update, context):
    await update.message.reply_text("This is a fully automated bot for buying and selling Telegram Stars.\n\nFor support, please contact the administrator.")

async def buy_stars_start(update, context):
    await update.message.reply_text("How many Stars ⭐ would you like to purchase?", reply_markup=ReplyKeyboardRemove())
    return BUY_STARS_AMOUNT

async def get_payment_method(update, context):
    try:
        context.user_data["stars_amount"] = int(update.message.text)
        if context.user_data["stars_amount"] <= 0:
            await update.message.reply_text("Please enter a positive number of Stars.")
            return BUY_STARS_AMOUNT # Stay in the same state to re-ask
    except ValueError:
        await update.message.reply_text("That doesn't look like a valid number. Please enter how many Stars ⭐ you'd like to purchase (e.g., 100).")
        return BUY_STARS_AMOUNT # Stay in the same state to re-ask

    await update.message.reply_text("Please provide your payment method (e.g., 'NOWPayments', 'USDT').")
    return GET_PAYMENT_METHOD


async def sell_stars_start(update, context):
    await update.message.reply_text("How many Stars ⭐ would you like to sell?")
    return SELL_STARS_AMOUNT

async def get_payout_method(update, context):
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

async def get_wallet_address(update, context):
    context.user_data['payout_method'] = update.message.text
    await update.message.reply_text("Please provide your wallet address or bank details for payout.")
    return GET_WALLET_ADDRESS


async def confirm_transaction(update, context):
    context.user_data["final_input"] = update.message.text
    
    if "stars_amount" in context.user_data and "payment_method" not in context.user_data:
        context.user_data["payment_method"] = context.user_data["final_input"]
        stars_amount = context.user_data["stars_amount"]
        recipient_username = update.effective_user.username
        
        await update.message.reply_text(
            f"You want to buy {stars_amount} Stars using {context.user_data['payment_method']}. "
            f"Stars will be sent to your Telegram account (@{recipient_username}).\n\n"
            "Confirm to proceed with payment generation. (Type 'Confirm' or 'Cancel')"
        )
        
        # IMPORTANT: In a real payment flow, you would generate a NOWPayments invoice here
        # and wait for the IPN callback to confirm payment BEFORE calling purchase_stars_on_fragments.
        # This direct call is for demonstration/testing purposes where you simulate immediate fulfillment.
        success = purchase_stars_on_fragments(stars_amount, recipient_username)
        if success:
            await update.message.reply_text("Purchase initiated! Your Stars should be sent shortly. (Note: Actual payment processing would occur here.)")
        else:
            await update.message.reply_text("Purchase failed on Fragments. Please try again later.")
        
        context.user_data.clear()
        return ConversationHandler.END

    elif "stars_amount" in context.user_data and "payout_method" in context.user_data and "wallet_address" not in context.user_data:
        context.user_data["wallet_address"] = context.user_data["final_input"]

        stars_amount = context.user_data["stars_amount"]
        payout_method = context.user_data["payout_method"]
        wallet_address = context.user_data["wallet_address"]

        await update.message.reply_text(
            f"You want to sell {stars_amount} Stars. "
            f"Payout will be sent via {payout_method} to {wallet_address}.\n\n"
            "Please confirm this information. (Type 'Confirm' or 'Cancel')"
        )
        
        await update.message.reply_text("Thank you for confirming! Please send the Stars to our designated address. Once received, your payout will be processed.")
        
        context.user_data.clear()
        return ConversationHandler.END

    else:
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
            fallbacks=[CommandHandler("cancel", help_command)],
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
        logger.error("Telegram bot 'application' not initialized for webhook processing.")
        abort(500)
    
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        abort(500)
    return "OK"


# The main function is now primarily for one-time webhook setup on deployment.
# For local development, you might run the Flask app directly.
async def main():
    """
    Handles startup logic for the bot.
    - Sets the webhook if WEBHOOK_URL is provided.
    """
    current_application = initialize_bot_application()
    if current_application is None:
        logger.critical("Bot application failed to initialize. Exiting.")
        sys.exit(1)

    if WEBHOOK_URL: # This WEBHOOK_URL will be provided by Render
        logger.info(f"Setting Telegram webhook for deployment to: {WEBHOOK_URL}/telegram-webhook")
        await current_application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram-webhook")
        logger.info("Telegram webhook command sent. The Flask app is now responsible for handling updates.")
    else:
        logger.warning("WEBHOOK_URL not set. Webhook will not be configured. This is expected if running locally without ngrok or similar.")

# This block is for local testing.
# When deployed with Gunicorn, this block is not executed.
if __name__ == "__main__":
    # For local development, you can run the Flask app directly.
    # If you want to test the webhook setup locally, you'd need ngrok or similar.
    # The main() function (for setting webhook) should be run separately or integrated carefully.
    
    # Option 1: Run Flask app for local testing (without setting webhook)
    # flask_app.run(debug=True, port=5000)

    # Option 2: Run main() to set webhook (e.g., in a separate script or once)
    # This is what Render's build process might do, or you run it manually.
    asyncio.run(main())

    # Note: For a combined local development experience with polling,
    # you would re-introduce the polling logic from your original Stars.py here
    # if WEBHOOK_URL is not set. For Render, polling is not used.
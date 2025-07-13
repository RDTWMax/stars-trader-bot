import logging
import requests
import os
import uuid
import sqlite3
import threading
import time
import hmac
import hashlib
import asyncio
from decimal import Decimal, getcontext
from dotenv import load_dotenv
from flask import Flask, request, abort
from telegram import Update, Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "YOUR_NOWPAYMENTS_API_KEY")
IPN_SECRET_KEY = os.getenv("IPN_SECRET_KEY", "YOUR_IPN_SECRET_KEY")  # Crucial for verifying webhooks
DB_FILE = os.getenv("DB_FILE", "stars_trader.db")

# --- Webhook Server Configuration ---
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-webhook-url.com")

# --- Fragments.com Scraper Configuration ---
FRAGMENTS_USERNAME = os.getenv("FRAGMENTS_USERNAME", "YOUR_FRAGMENTS_USERNAME")
FRAGMENTS_PASSWORD = os.getenv("FRAGMENTS_PASSWORD", "YOUR_FRAGMENTS_PASSWORD")

# Set precision for decimal calculations
getcontext().prec = 18

# --- Bot States for Conversation Flow ---
(
    SELECTING_ACTION,
    BUY_STARS_AMOUNT,
    SELL_STARS_AMOUNT,
    GET_PAYMENT_METHOD,
    SELL_GET_PAYOUT_METHOD,
    GET_WALLET_ADDRESS,
) = range(6)

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Database Handler ---
local_storage = threading.local()

def get_db_conn():
    if not hasattr(local_storage, 'db_conn'):
        local_storage.db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        local_storage.db_conn.row_factory = sqlite3.Row
    return local_storage.db_conn

def setup_database():
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            recipient_username TEXT,
            invoice_id TEXT,
            buy_amount INTEGER,
            fulfilled_amount INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    logger.info("Database setup complete.")

def add_transaction(order_id, user_id, invoice_id, buy_amount, status='pending'):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transactions (order_id, user_id, invoice_id, buy_amount, status) VALUES (?, ?, ?, ?, ?)", (order_id, user_id, invoice_id, buy_amount, status))
    conn.commit()
    logger.info(f"Added transaction {order_id} for user {user_id} with status 'pending'.")

def get_transaction_by_order_id(order_id):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE order_id = ?", (order_id,))
    return cursor.fetchone()

def get_latest_paid_transaction(user_id):
    """Gets the most recent transaction with 'paid' status for a user."""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE user_id = ? AND status = 'paid' ORDER BY created_at DESC LIMIT 1", (user_id,))
    return cursor.fetchone()

def update_transaction_status(order_id, status):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE transactions SET status = ? WHERE order_id = ?", (status, order_id))
    conn.commit()
    logger.info(f"Updated transaction {order_id} to status '{status}'.")

def update_transaction_fulfillment(order_id, username, fulfilled_amount, new_status):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE transactions SET recipient_username = ?, fulfilled_amount = ?, status = ? WHERE order_id = ?", (username, fulfilled_amount, new_status, order_id))
    conn.commit()
    logger.info(f"Fulfilled {fulfilled_amount} for transaction {order_id}. New status: {new_status}")


# --- Risk Management & Fragments Handler ---
def calculate_available_stars_to_buy() -> int:
    """
    SIMULATED RISK MANAGEMENT.
    In a real application, this function would check your actual TON balance via an API,
    calculate how many stars you can afford, and return that number.
    For now, we return a large number to simulate having enough funds.
    """
    return 1_000_000

def purchase_stars_on_fragments(stars_amount: int, recipient_username: str) -> bool:
    if "YOUR" in FRAGMENTS_USERNAME or "YOUR" in FRAGMENTS_PASSWORD:
        logger.error("Fragments credentials not set. Skipping purchase.")
        return False
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=service, options=options)
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
        amount_input = wait.until(EC.visibility_of_element_located((By.ID, "star-amount")))
        recipient_input = driver.find_element(By.ID, "star-recipient")
        amount_input.clear()
        amount_input.send_keys(str(stars_amount))
        recipient_input.clear()
        recipient_input.send_keys(recipient_username)
        logger.info(f"Entered {stars_amount} stars for @{recipient_username}")
        time.sleep(1)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='modal-dialog']//button[contains(text(), 'Buy Stars')]"))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='modal-dialog']//button[contains(text(), 'Confirm')]"))).click()
        logger.info("Purchase confirmed on Fragments.")
        time.sleep(5)
        return True
    except Exception as e:
        logger.error(f"An error occurred during Fragments automation: {e}")
        driver.save_screenshot('fragments_error.png')
        return False
    finally:
        driver.quit()

# --- Helper Functions & Live Data ---
def get_live_star_price_from_fragments(): return Decimal("0.01")
def get_live_crypto_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "the-open-network,solana,tether", "vs_currencies": "usd"}
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {"TON": Decimal(data["the-open-network"]["usd"]), "SOL": Decimal(data["solana"]["usd"]), "USDT": Decimal(data["tether"]["usd"])}
    except requests.exceptions.RequestException: return None
async def create_payment_invoice(price: Decimal, currency: str, order_id: str) -> dict | None:
    if "YOUR" in NOWPAYMENTS_API_KEY: return None
    api_url = "https://api.nowpayments.io/v1/invoice"
    currency_map = {"TON": "TON", "USDT": "usdttrc20", "SOL": "SOL"}
    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}
    payload = {"price_amount": float(price), "price_currency": "usd", "pay_currency": currency_map.get(currency, currency.lower()), "order_id": order_id, "ipn_callback_url": f"{WEBHOOK_URL}/nowpayments-ipn"}
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException: return None

# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = [["Buy Stars ⭐", "Sell Stars 💸"], ["Help & Support ❓"]]
    await update.message.reply_html(rf"Hi {update.effective_user.mention_html()}! Welcome to the Stars Trader Bot. 🤖", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return SELECTING_ACTION
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("This is a fully automated bot for buying and selling Telegram Stars.\n\nFor support, please contact the administrator.")

# --- Buy Stars Flow ---
async def buy_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("How many Stars ⭐ would you like to purchase?", reply_markup=ReplyKeyboardRemove())
    return BUY_STARS_AMOUNT
async def buy_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data["buy_amount"] = amount
    except (ValueError, TypeError):
        await update.message.reply_text("Please enter a positive whole number.")
        return BUY_STARS_AMOUNT
    crypto_prices_usd = get_live_crypto_prices()
    if not crypto_prices_usd:
        await update.message.reply_text("Sorry, I couldn't fetch live prices. Please try again later.")
        return await end_conversation(update, context)
    total_usd = (get_live_star_price_from_fragments() * amount * Decimal("1.05")) * crypto_prices_usd["TON"]
    context.user_data["price_usd"] = total_usd
    price_summary = f"Okay, you want to buy *{amount} Stars* for *${total_usd:.2f} USD*.\nPlease select your payment method."
    keyboard = [[InlineKeyboardButton(f"Pay with TON", callback_data="pay_TON"), InlineKeyboardButton(f"Pay with USDT", callback_data="pay_USDT"), InlineKeyboardButton(f"Pay with SOL", callback_data="pay_SOL")], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
    await update.message.reply_text(price_summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return GET_PAYMENT_METHOD
async def get_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    payment_method = query.data.split('_')[1]
    order_id = str(uuid.uuid4())
    await query.edit_message_text(text="Creating your secure payment invoice...")
    invoice = await create_payment_invoice(context.user_data["price_usd"], payment_method, order_id)
    if not invoice:
        await query.message.reply_text("Sorry, I couldn't create a payment invoice. Please try again later.")
        return await end_conversation(update, context)
    add_transaction(order_id, update.effective_user.id, invoice.get("invoice_id"), context.user_data["buy_amount"], 'pending')
    await query.edit_message_text(text=f"Your invoice is ready! Please send:\n`{invoice.get('pay_amount')} {invoice.get('pay_currency').upper()}`\nTo:\n`{invoice.get('pay_address')}`\n\nI will notify you here once payment is confirmed.\n\n⚠️ *This is a simulation.* Do not send real funds.", parse_mode='Markdown')
    return ConversationHandler.END

async def get_recipient_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles messages from users, checking if they have a paid transaction waiting for a username."""
    user_id = update.effective_user.id
    transaction = get_latest_paid_transaction(user_id)
    
    # If no paid transaction is found for this user, do nothing.
    if not transaction:
        logger.info(f"User {user_id} sent a message, but no paid transaction was found.")
        # Optionally, you could send a message like: "I'm not currently waiting for a username from you."
        # For now, we'll just ignore it to not spam users.
        return

    recipient_username = update.message.text.lstrip('@')
    order_id = transaction['order_id']
    
    # Immediately update status to prevent double-processing
    update_transaction_status(order_id, 'processing')
    
    await update.message.reply_text(f"Thank you. Processing your order. This may take a moment...")
    
    # --- Execute Risk Management and Purchase ---
    available_stars = calculate_available_stars_to_buy()
    stars_to_buy = min(transaction['buy_amount'], available_stars)
    
    success = purchase_stars_on_fragments(stars_to_buy, recipient_username)
    
    if success:
        if stars_to_buy < transaction['buy_amount']:
            # Partial fulfillment
            new_status = 'partially_completed'
            await update.message.reply_text(f"✅ Your order has been partially fulfilled with {stars_to_buy} Stars. Please contact support for the remaining amount, providing Order ID: {order_id}")
        else:
            # Full fulfillment
            new_status = 'completed'
            await update.message.reply_text(f"✅ Success! Your order for {stars_to_buy} Stars is complete. Thank you for your business!")
        
        update_transaction_fulfillment(order_id, recipient_username, stars_to_buy, new_status)
    else:
        # Purchase failed
        update_transaction_status(order_id, 'failed')
        await update.message.reply_text(f"❌ An error occurred while processing your order. Please contact support and provide this Order ID: {order_id}")

# --- Sell Stars Flow ---
async def sell_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("How many Stars ⭐ are you looking to sell?", reply_markup=ReplyKeyboardRemove())
    return SELL_STARS_AMOUNT
async def sell_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data["sell_amount"] = amount
    except (ValueError, TypeError):
        await update.message.reply_text("Please enter a positive whole number.")
        return SELL_STARS_AMOUNT
    crypto_prices_usd = get_live_crypto_prices()
    if not crypto_prices_usd:
        await update.message.reply_text("Sorry, I couldn't fetch live prices. Please try again later.")
        return await end_conversation(update, context)
    total_ton = (get_live_star_price_from_fragments() * amount * Decimal("0.95")) * crypto_prices_usd["TON"]
    total_usdt = total_ton * crypto_prices_usd["TON"] / crypto_prices_usd["USDT"]
    total_sol = total_ton * crypto_prices_usd["TON"] / crypto_prices_usd["SOL"]
    context.user_data["payouts"] = {"TON": total_ton, "USDT": total_usdt, "SOL": total_sol}
    payout_summary = (f"Okay, you want to sell *{amount} Stars*.\n\nI can offer you:\n"
                      f"🔹 *{total_ton:.8f} TON*\n🔹 *{total_usdt:.8f} USDT*\n🔹 *{total_sol:.8f} SOL*\n\n"
                      "Please select your payout currency.")
    keyboard = [[InlineKeyboardButton(f"Receive TON", callback_data="payout_TON"), InlineKeyboardButton(f"Receive USDT", callback_data="payout_USDT"), InlineKeyboardButton(f"Receive SOL", callback_data="payout_SOL")], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
    await update.message.reply_text(payout_summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return SELL_GET_PAYOUT_METHOD
async def sell_get_payout_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    payout_method = query.data.split('_')[1]
    context.user_data['payout_method'] = payout_method
    await query.edit_message_text(f"You've selected to receive {payout_method}.\nPlease reply with your {payout_method} wallet address.")
    return GET_WALLET_ADDRESS
async def get_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wallet_address = update.message.text
    payout_method = context.user_data['payout_method']
    payout_amount = context.user_data['payouts'][payout_method]
    await update.message.reply_text(f"Thank you. Your wallet address is:\n`{wallet_address}`\n\nTo complete the sale, please transfer {context.user_data['sell_amount']} Stars to me now.\n\n"
                                    f"⚠️ *This is a simulation.* I will now process your payout of *{payout_amount:.8f} {payout_method}*.", parse_mode='Markdown')
    await update.message.reply_text("✅ Payout sent! The funds should arrive in your wallet shortly. Thank you!")
    return await end_conversation(update, context)

# --- General Handlers ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operation cancelled.")
    else:
        await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return await end_conversation(update, context)

async def end_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Gracefully ends the conversation. Clears user data and offers the main menu.
    This function is safe to call from both text message handlers and callback query handlers.
    """
    context.user_data.clear()
    logger.info(f"Ending conversation for user {update.effective_user.id}")
    reply_keyboard = [["Buy Stars ⭐", "Sell Stars 💸"], ["Help & Support ❓"]]
    await context.bot.send_message(chat_id=update.effective_chat.id, text="\nWhat would you like to do next?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return ConversationHandler.END

# --- Flask Webhook Server ---
flask_app = Flask(__name__)

async def send_payment_notification(user_id: int):
    """
    Creates a temporary bot instance to send a one-off message.
    This is suitable for stateless environments like a WSGI server on PythonAnywhere.
    """
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=user_id,
        text="✅ Payment confirmed!\n\nTo deliver your Stars, please reply with your Telegram @username."
    )

@flask_app.route("/nowpayments-ipn", methods=["POST"])
def nowpayments_ipn():
    if 'x-nowpayments-sig' not in request.headers: abort(400)
    try:
        signature = hmac.new(key=IPN_SECRET_KEY.encode(), msg=request.data, digestmod=hashlib.sha512).hexdigest()
        if signature != request.headers['x-nowpayments-sig']:
            logger.warning("Webhook signature mismatch.")
            abort(401)
        data = request.get_json()
        logger.info(f"Received webhook: {data}")
        payment_status = data.get('payment_status')
        order_id = data.get('order_id')
        if payment_status == 'finished':
            transaction = get_transaction_by_order_id(order_id)
            if transaction and transaction['status'] == 'pending':
                update_transaction_status(order_id, 'paid')
                user_id = transaction['user_id']
                # Directly send the message without relying on a shared application or job queue
                asyncio.run(send_payment_notification(user_id))
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        abort(500)
    return "OK"

def main() -> None:
    """Run the bot."""
    if "YOUR" in TELEGRAM_BOT_TOKEN or "YOUR" in NOWPAYMENTS_API_KEY:
        print("!!! PLEASE SET YOUR TOKENS AND API KEYS IN THE SCRIPT !!!")
        return

    setup_database()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Main conversation handler for buying and selling flows
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.Regex("^Buy Stars ⭐$"), buy_stars_start), MessageHandler(filters.Regex("^Sell Stars 💸$"), sell_stars_start)],
        states={
            SELECTING_ACTION: [MessageHandler(filters.Regex("^Buy Stars ⭐$"), buy_stars_start), MessageHandler(filters.Regex("^Sell Stars 💸$"), sell_stars_start), MessageHandler(filters.Regex("^Help & Support ❓$"), help_command)],
            BUY_STARS_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_stars_amount)],
            GET_PAYMENT_METHOD: [CallbackQueryHandler(get_payment_method, pattern="^pay_")],
            SELL_STARS_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_stars_amount)],
            SELL_GET_PAYOUT_METHOD: [CallbackQueryHandler(sell_get_payout_method, pattern="^payout_")],
            GET_WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_wallet_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Standalone handler for receiving the username after a webhook notification
    username_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient_username)

    application.add_handler(conv_handler)
    application.add_handler(username_handler, group=1) # Use a different group to ensure it's checked after the conversation
    application.add_handler(CommandHandler("help", help_command))

    print("Bot is running... Press Ctrl-C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()

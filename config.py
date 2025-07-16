# config.py

import os
from decimal import getcontext
from dotenv import load_dotenv

# Load environment variables from .env file for local development
# Render will provide these directly in production
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
IPN_SECRET_KEY = os.getenv("IPN_SECRET_KEY") # Ensure this env var is set on Render
DB_FILE = os.getenv("DB_FILE", "stars_trader.db") # For local SQLite, consider a cloud DB for production

# --- Webhook Server Configuration ---
# This will be set by Render's environment, or your Render app's URL for Telegram
# For local development, you might use a tool like ngrok to expose your local server
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Render will inject its own URL here

# --- Fragments.com Scraper Configuration ---
FRAGMENTS_USERNAME = os.getenv("FRAGMENTS_USERNAME")
FRAGMENTS_PASSWORD = os.getenv("FRAGMENTS_PASSWORD")

# Set precision for decimal calculations
getcontext().prec = 18

# --- Bot States for Conversation Flow (No change, but included for completeness) ---
(
    SELECTING_ACTION,
    BUY_STARS_AMOUNT,
    SELL_STARS_AMOUNT,
    GET_PAYMENT_METHOD,
    SELL_GET_PAYOUT_METHOD,
    GET_WALLET_ADDRESS,
) = range(6)

# Basic validation (optional, but good practice)
if not all([TELEGRAM_BOT_TOKEN, NOWPAYMENTS_API_KEY, IPN_SECRET_KEY, FRAGMENTS_USERNAME, FRAGMENTS_PASSWORD]):
    print("WARNING: One or more critical environment variables are not set. Check .env or Render config.")
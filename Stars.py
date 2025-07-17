# Stars.py - Minimal version for debugging

import os
from flask import Flask, request, abort
import logging

# Setup logging to see output in Render logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Initializing Flask application...")
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    logger.info("Accessed root path /")
    return "Bot service is running - Minimal Flask App!"

@flask_app.route('/test-route')
def test_route():
    logger.info("Accessed test path /test-route")
    return "This is a test route!"

@flask_app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    logger.info("Received POST to /telegram-webhook (minimal app)")
    # In this minimal version, we just acknowledge receipt
    return "OK"

logger.info("Flask routes registered.")
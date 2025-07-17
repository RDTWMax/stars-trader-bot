# Stars.py - Minimal version for debugging

# ADD THIS PRINT STATEMENT AT THE VERY TOP
print("DEBUG: Stars.py is being imported by Gunicorn!")

import os
from flask import Flask, request, abort
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Initializing Flask application...")
flask_app = Flask(__name__)

# ADD THIS PRINT STATEMENT HERE, after flask_app is created
print(f"DEBUG: Flask app created. Routes: {flask_app.url_map}")


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
    return "OK"

logger.info("Flask routes registered.")
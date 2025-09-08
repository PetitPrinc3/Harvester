import os
import asyncio
import logging
from telethon.sync import TelegramClient
from dotenv import load_dotenv

import logger_setup

# --- Initialization ---
load_dotenv()
log = logging.getLogger(__name__)

# --- Telegram Bot Setup ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_GROUP_CHAT_ID')

async def _send_message_async(message):
    if not all([API_ID, API_HASH, BOT_TOKEN, CHAT_ID]):
        log.warning("Telegram credentials not fully configured. Skipping notification.")
        return

    # Using a file for the session is required by Telethon
    async with TelegramClient('bot_session', API_ID, API_HASH) as client:
        await client.start(bot_token=BOT_TOKEN)
        # The chat_id needs to be an integer for Telethon
        await client.send_message(int(CHAT_ID), message)

def send_notification(message):
    """Synchronous wrapper for the async send_message function."""
    log.info(f"Sending Telegram notification: {message[:35]}")
    try:
        # Create a new event loop to run the async function
        # This is a simple way to call async from a sync thread
        asyncio.run(_send_message_async(message))
        log.info("Successfully sent Telegram notification.")
    except Exception as e:
        log.error(f"Failed to send Telegram notification: {e}", exc_info=True)

if __name__ == '__main__':
    # This allows for testing the notifier directly
    logger_setup.setup_logging()
    log.info("--- Telegram Notifier Test ---")
    log.info(f"API_ID: {'*' * 5 if API_ID else 'Not Set'}")
    log.info(f"API_HASH: {'*' * 5 if API_HASH else 'Not Set'}")
    log.info(f"BOT_TOKEN: {'*' * 5 if BOT_TOKEN else 'Not Set'}")
    log.info(f"CHAT_ID: {CHAT_ID if CHAT_ID else 'Not Set'}")
    log.info("Sending a test notification...")
    send_notification("Hello from Harvester! This is a test notification.")
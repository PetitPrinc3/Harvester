import os
import asyncio
from telethon.sync import TelegramClient
from dotenv import load_dotenv

load_dotenv()

# Load credentials from environment variables
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_GROUP_CHAT_ID')

async def _send_message_async(message):
    if not all([API_ID, API_HASH, BOT_TOKEN, CHAT_ID]):
        print("WARNING: Telegram credentials not fully configured. Skipping notification.")
        return

    # Using a file for the session is required by Telethon
    async with TelegramClient('bot_session', API_ID, API_HASH) as client:
        await client.start(bot_token=BOT_TOKEN)
        # The chat_id needs to be an integer for Telethon
        await client.send_message(int(CHAT_ID), message)

def send_notification(message):
    """Synchronous wrapper for the async send_message function."""
    print(f"Sending Telegram notification: {message}")
    try:
        # Create a new event loop to run the async function
        # This is a simple way to call async from a sync thread
        asyncio.run(_send_message_async(message))
        print("Successfully sent Telegram notification.")
    except Exception as e:
        print(f"ERROR: Failed to send Telegram notification: {e}")

if __name__ == '__main__':
    # This allows for testing the notifier directly
    print("API_ID:", API_ID)
    print("API_HASH:", API_HASH)
    print("BOT_TOKEN:", BOT_TOKEN)
    print("CHAT_ID:", CHAT_ID)
    print("Sending a test notification...")
    send_notification("Hello from Harvester! This is a test notification.")

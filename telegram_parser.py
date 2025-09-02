# This script requires 'Telethon' and 'python-dotenv'. Please install them using: pip install Telethon python-dotenv

import os
import re
import asyncio
import logging
from telethon.sync import TelegramClient
from dotenv import load_dotenv

log = logging.getLogger(__name__)

class TelegramParser:
    """A class to connect to Telegram and find specific links in channels."""

    def __init__(self, session_name='telegram_session'):
        load_dotenv()
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.session_name = session_name

        if not self.api_id or not self.api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in your .env file.")

    def setup_session(self):
        """Connects to the client to create a .session file, then disconnects."""
        with TelegramClient(self.session_name, self.api_id, self.api_hash) as client:
            if client.is_connected():
                log.info("Successfully connected and session file is created/updated.")
            else:
                log.error("Could not connect to Telegram during setup.")

    def find_latest_zt_link(self, channel_name='zt_officiel'):
        """
        Connects to Telegram in a thread-safe way and finds the latest link.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            with TelegramClient(self.session_name, self.api_id, self.api_hash, loop=loop) as client:
                log.info(f"Searching for links in '{channel_name}'...")
                
                for message in client.iter_messages(channel_name, limit=200):
                    if message.text:
                        urls = re.findall(r'https?://[\w\-./?=&%#]+', message.text)
                        for url in urls:
                            if re.search(r'https://.*\.zone-telechargement\.', url, re.IGNORECASE):
                                log.info(f"Found matching URL: {url}")
                                return url

            log.warning("No matching URL found in the last 200 messages.")
            return None

        except Exception as e:
            log.error(f"An error occurred while connecting or fetching messages: {e}", exc_info=True)
            return None

if __name__ == '__main__':
    # This block is for testing or direct setup, not for library use.
    import logger_setup
    logger_setup.setup_logging()
    log.info("This script is a library. To perform the one-time setup, run: python setup.py")

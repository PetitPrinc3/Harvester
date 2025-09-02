# This script requires 'Telethon' and 'python-dotenv'. Please install them using: pip install Telethon python-dotenv

import os
import re
from telethon.sync import TelegramClient
from dotenv import load_dotenv

class TelegramParser:
    """A class to connect to Telegram and find specific links in channels."""

    def __init__(self, session_name='telegram_session'):
        load_dotenv() # Load variables from .env file
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.session_name = session_name

        if not self.api_id or not self.api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in your .env file.")

    def find_latest_zt_link(self, channel_name='zt_officiel'):
        """
        Connects to Telegram and finds the last message in a given channel
        containing a URL that matches the 'zone-telechargement' pattern.
        """
        # The 'with' statement ensures the client is disconnected properly.
        # On first run, this will prompt for phone, code, and 2FA password.
        try:
            with TelegramClient(self.session_name, self.api_id, self.api_hash) as client:
                print(f"Successfully connected to Telegram. Searching for links in '{channel_name}'...")
                
                for message in client.iter_messages(channel_name, limit=200):
                    if message.text:
                        urls = re.findall(r'https?://[\w\-./?=&%#]+', message.text)
                        for url in urls:
                            if re.search(r'https://.*\.zone-telechargement\.', url, re.IGNORECASE):
                                print(f"Found matching URL: {url}")
                                return url

            print("No matching URL found in the last 200 messages.")
            return None

        except Exception as e:
            print(f"An error occurred while connecting or fetching messages: {e}")
            return None

if __name__ == '__main__':
    print("Attempting to find the latest Zone-Telechargement link...")
    parser = TelegramParser()
    latest_link = parser.find_latest_zt_link()
    if latest_link:
        print(f"\nProcess finished. Latest link found: {latest_link}")
    else:
        print("\nProcess finished. No link was found.")
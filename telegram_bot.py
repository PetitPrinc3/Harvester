import os
import re
import logging
import asyncio
import threading
from telethon import TelegramClient, events
from dotenv import load_dotenv

import database
from file_parser import parse_filename
from fichier_dl import get_filename_from_url

# --- Initialization ---
load_dotenv()
log = logging.getLogger(__name__)

# --- Telegram Bot Setup ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = int(os.getenv('TELEGRAM_GROUP_CHAT_ID'))

async def process_link(link, loop):
    """Processes a single 1fichier link."""
    try:
        filename = await loop.run_in_executor(None, get_filename_from_url, link)
        if not filename:
            log.error(f"Could not determine filename for link: {link}")
            return None, f"- {link} (Could not get filename)"

        if database.is_link_already_added(link):
            log.warning(f"Link {link} is already in the database. Skipping.")
            return None, f"- {link} (Already in queue)"

        media_info = parse_filename(filename)
        title = media_info.get('title', filename)

        if media_info.get('type') == 'tv_show' and media_info.get('season') is not None:
            title = f"{title} S{media_info['season']:02d}E{media_info['episode']:02d}"

        request_id = database.add_request(
            media_info.get('title', 'Unknown Title'),
            media_info.get('type', 'unknown'),
            media_info.get('season')
        )

        with database.get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO downloads (request_id, episode_number, quality, language, fichier_link, status) VALUES (?, ?, ?, ?, ?, ?)",
                (request_id, media_info.get('episode'), media_info.get('quality'), media_info.get('language'), link, 'queued')
            )
            conn.commit()
        
        log.info(f"Successfully added '{title}' to the download queue via Telegram.")
        return title, None

    except Exception as e:
        log.error(f"An error occurred while processing link {link}: {e}", exc_info=True)
        return None, f"- {link} (An unexpected error occurred)"

def construct_reply_message(success_titles, failure_links):
    """Constructs a single, consolidated reply message."""
    reply_message = ""
    if success_titles:
        reply_message += "✅ The following titles have been added to the queue:\n" + "\n".join(f"- {title}" for title in success_titles)
    
    if failure_links:
        if reply_message:
            reply_message += "\n\n"
        reply_message += "❌ Could not add the following links:\n" + "\n".join(failure_links)
    
    return reply_message

async def handle_new_message(event):
    """Listens for new messages, processes unique 1fichier links, and sends a single summary reply."""
    # Use a context manager to show a "typing" status in the chat
    async with event.client.action(event.chat_id, 'typing'):
        message_text = event.message.message
        
        # --- Start CPU-bound work immediately to feel more responsive ---
        links = re.findall(r'https?://1fichier\.com/\?[a-z0-9]+', message_text)
        unique_links = sorted(list(set(links)))

        # --- Now, get sender details for logging ---
        sender = await event.get_sender()
        sender_name = sender.username if sender.username else sender.first_name
        log.info(f"Received message from '{sender_name}': {message_text[:30]}...")

        if not unique_links:
            log.info("No unique 1fichier links found in the message.")
            return

        success_titles = []
        failure_links = []
        loop = asyncio.get_running_loop()

        for link in unique_links:
            log.info(f"Processing unique link: {link}")
            title, error = await process_link(link, loop)
            if title:
                success_titles.append(title)
            if error:
                failure_links.append(error)

        reply_message = construct_reply_message(success_titles, failure_links)
        if reply_message:
            await event.reply(reply_message)


def start_bot():
    """Initializes and runs the Telethon client in the current thread."""
    log.info("[Bot]: Initializing Telegram bot...")
    
    # Set thread name for emoji logging
    threading.current_thread().name = 'TelegramBot'
    
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Initialize the database for this thread/process
    database.init_db()

    bot = TelegramClient('bot', API_ID, API_HASH, loop=loop)
    bot.add_event_handler(handle_new_message, events.NewMessage(chats=CHAT_ID))

    try:
        log.info("[Bot]: Starting bot...")
        bot.start(bot_token=BOT_TOKEN)
        bot.run_until_disconnected()
    finally:
        log.info("[Bot]: Bot stopped.")
        bot.disconnect()

if __name__ == '__main__':
    # This allows running the bot directly for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    start_bot()

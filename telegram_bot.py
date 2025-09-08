import os
import re
import logging
import asyncio
import threading
import json
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from dotenv import load_dotenv

import database
from file_parser import parse_filename
from fichier_dl import get_filename_from_url
from zt_parser import ZTParser, select_best_movie, select_best_show

# --- Initialization ---
load_dotenv()
log = logging.getLogger(__name__)

# --- Telegram Bot Setup ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = int(os.getenv('TELEGRAM_GROUP_CHAT_ID'))
ZT_BASE_URL = os.getenv('ZT_BASE_URL', "https://www.zone-telechargement.diy")

def parse_search_query(query_text):
    """Parses a search query to extract title, season, and episode, regardless of order."""
    if not query_text:
        return None, None, None

    title = query_text
    season, episode = None, None

    # Find and extract season number (e.g., "season 3", "saison 3", "s03")
    season_match = re.search(r'(?:saison|season|s)\s*(\d{1,2})', title, re.IGNORECASE)
    if season_match:
        season = int(season_match.group(1))
        title = title.replace(season_match.group(0), '')

    # Find and extract episode number (e.g., "episode 2", "épisode 2", "ep2", "e02")
    episode_match = re.search(r'(?:épisode|episode|ep|e)\s*(\d{1,2})', title, re.IGNORECASE)
    if episode_match:
        episode = int(episode_match.group(1))
        title = title.replace(episode_match.group(0), '')

    # Clean up the title by removing extra spaces
    title = re.sub(r'\s+', ' ', title).strip()

    # If the title is empty after extraction, the query was likely just "season 3"
    if not title and (season is not None or episode is not None):
        return query_text, None, None

    return title, season, episode

# --- New Search Command Handler ---
@events.register(events.NewMessage(pattern=re.compile(r"/search(?:$|\s+(.*))"), chats=CHAT_ID))
async def search_command_handler(event):
    """Handles the /search command, parsing complex queries and using conversations for missing info."""
    loop = asyncio.get_running_loop()
    chat = await event.get_chat()
    sender = await event.get_sender()
    sender_name = sender.username if sender.username else sender.first_name
    
    raw_query = event.pattern_match.group(1)
    
    # --- Parse Initial Query ---
    requested_title, requested_season, requested_episode = parse_search_query(raw_query)
    media_type_choice = 'tv_show' if requested_season is not None else None

    log.info(
        f"[Bot]: New search by '{sender_name}'. "
        f"Query: '{raw_query or 'None'}'. "
        f"Parsed: [T='{requested_title}', S={requested_season}, E={requested_episode}]"
    )

    try:
        async with event.client.conversation(chat, timeout=180) as conv:
            # --- Get Title (if not provided) ---
            if not requested_title:
                await conv.send_message("What title are you looking for?")
                title_response = await conv.get_response()
                if title_response.text == '/cancel':
                    await conv.send_message("Search cancelled.")
                    return
                requested_title = title_response.text

            # --- Get Media Type (if not deduced) ---
            if not media_type_choice:
                type_message = await conv.send_message(
                    f"Searching for **{requested_title}**. Is it a Movie or a TV Show?",
                    buttons=[
                        [Button.inline("Movie", b'movie'), Button.inline("TV Show", b'tv_show')],
                        [Button.inline("Cancel", b'cancel')]
                    ]
                )
                press = await conv.wait_event(events.CallbackQuery)
                media_type_choice = press.data.decode('utf-8')
                await type_message.delete()

                if media_type_choice == 'cancel':
                    await conv.send_message("Search cancelled.")
                    return

            # --- Get Season/Episode (for TV Shows, if not provided) ---
            if media_type_choice == 'tv_show':
                if requested_season is None:
                    await conv.send_message(f"Which season of **{requested_title}**?")
                    season_response = await conv.get_response()
                    if season_response.text == '/cancel':
                        await conv.send_message("Search cancelled.")
                        return
                    if not season_response.text.isdigit():
                        await conv.send_message("Invalid season number. Search cancelled.")
                        return
                    requested_season = int(season_response.text)
                
                if requested_episode is None:
                    episode_message = await conv.send_message(
                        f"Looking for a specific episode of Season {requested_season}?",
                        buttons=[Button.inline("Yes, let me specify", b'yes'), Button.inline("No, show all", b'no')]
                    )
                    press = await conv.wait_event(events.CallbackQuery)
                    choice = press.data.decode('utf-8')
                    await episode_message.delete()
                    
                    if choice == 'yes':
                        await conv.send_message("Which episode number?")
                        episode_response = await conv.get_response()
                        if episode_response.text.isdigit():
                            requested_episode = int(episode_response.text)
                        else:
                            await conv.send_message("Invalid episode number. Showing all for the season.")

            # --- Perform Search ---
            status_msg = await event.respond("🔎 Searching, please wait...")
            parser = ZTParser(base_url=ZT_BASE_URL)
            
            if media_type_choice == 'movie':
                search_type = 'films'
                search_term = requested_title
                log.info(f"Searching for movie '{search_term}'...")
                results = await loop.run_in_executor(None, parser.search, search_term, search_type)
                best_result = await loop.run_in_executor(None, select_best_movie, parser, results, search_term)
            else: # tv_show
                search_type = 'series'
                log.info(f"Searching for show '{requested_title}' Season {requested_season}...")
                results = await loop.run_in_executor(None, parser.search, requested_title, search_type)
                best_result = await loop.run_in_executor(None, select_best_show, parser, results, requested_title, requested_season)

            await status_msg.delete()

            # --- Display Results ---
            if not best_result:
                await event.respond("😕 No results found.")
                return

            if media_type_choice == 'movie':
                reply = (
                    f"🎬 **{best_result['title']}**\n\n"
                    f"- **Quality:** {best_result['quality']}\n"
                    f"- **Language:** {best_result['language']}\n"
                    f"- **Score:** {best_result['rating_score']}\n\n"
                    f"🔗 **Link:** `{best_result['dl_protect_link']}`"
                )
                await event.respond(reply)
            else: # tv_show
                if requested_episode is not None:
                    episode_found = next((ep for ep in best_result['episode_data'] if ep['episode_number'] == requested_episode), None)
                    if episode_found:
                        best_result['episode_data'] = [episode_found]
                    else:
                        await event.respond(f"😕 Could not find Episode {requested_episode} for this season, but found the season pack.")
                
                episodes_text = "\n".join(f"- Episode {ep['episode_number']}: `{ep['dl_protect_link']}`" for ep in best_result['episode_data'])
                reply = (
                    f"📺 **{best_result['title']} - Season {best_result['season']}**\n\n"
                    f"- **Quality:** {best_result['quality']}\n"
                    f"- **Language:** {best_result['language']}\n"
                    f"- **Score:** {best_result['rating_score']}\n\n"
                    f"**Episodes:**\n{episodes_text}"
                )
                if len(reply) > 4096:
                    header = (
                        f"📺 **{best_result['title']} - Season {best_result['season']}**\n\n"
                        f"- **Quality:** {best_result['quality']}\n"
                        f"- **Language:** {best_result['language']}\n"
                        f"- **Score:** {best_result['rating_score']}\n\n"
                        f"**Episodes (Part 1):**\n"
                    )
                    part1 = header
                    part2 = f"**Episodes (Part 2):**\n"
                    
                    for ep in best_result['episode_data']:
                        line = f"- Episode {ep['episode_number']}: `{ep['dl_protect_link']}`\n"
                        if len(part1) + len(line) < 4096:
                            part1 += line
                        else:
                            part2 += line
                    await event.respond(part1)
                    await event.respond(part2)
                else:
                    await event.respond(reply)

    except asyncio.TimeoutError:
        log.warning(f"Search conversation with '{sender_name}' timed out.")
        await event.respond("Search cancelled due to inactivity.")
    except Exception as e:
        log.error(f"An error occurred during the search conversation: {e}", exc_info=True)
        await event.respond("An unexpected error occurred. Please try again later.")


# --- New Queue Command Handler ---
@events.register(events.NewMessage(pattern='/queue', chats=CHAT_ID))
async def queue_command_handler(event):
    """Handles the /queue command to display the current download queue."""
    log.info("[Bot]: Received /queue command.")
    
    try:
        queue_items = database.get_active_queue()

        if not queue_items:
            await event.respond("✅ The download queue is currently empty.")
            return

        reply_message = "📋 **Current Download Queue**\n\n"
        for item in queue_items:
            # Format title (e.g., "Title S01E02" or just "Title")
            title = item['title']
            if item['season'] is not None and item['episode_number'] is not None:
                title = f"{title} S{item['season']:02d}E{item['episode_number']:02d}"
            
            # Format status and progress
            status = item['status'].replace('_', ' ').title()
            progress = ""
            if item['status'] == 'downloading' and item['download_progress'] is not None:
                progress = f" ({item['download_progress']:.1f}%)"
            
            reply_message += f"- **{title}**\n  • Status: `{status}{progress}`\n"

        await event.respond(reply_message)

    except Exception as e:
        log.error(f"An error occurred while fetching the queue: {e}", exc_info=True)
        await event.respond("An error occurred while fetching the queue.")


# --- Existing Link Processing ---
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
    # --- Prevent Bot from processing its own messages ---
    if event.message.out:
        return
        
    # Ignore commands
    if event.raw_text.startswith('/'):
        return
        
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
    
    # Register all event handlers
    bot.add_event_handler(search_command_handler)
    bot.add_event_handler(queue_command_handler)
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

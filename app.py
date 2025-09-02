import threading
import time
import collections
import traceback
import logging
from flask import Flask, request, jsonify
import database
import logger_setup
from telegram_parser import TelegramParser
from zt_parser import ZTParser, select_best_movie, select_best_show
from fichier_dl import FichierDownloader

# --- App Initialization ---
logger_setup.setup_logging()
log = logging.getLogger(__name__)

app = Flask(__name__)
database.init_db()

# In-memory queue for download tasks
download_queue = collections.deque()

# --- Background Tasks --- #

def process_request_task(request_id, request_data):
    """Background task with robust error logging."""
    try:
        log.info(f"[Task {request_id}]: Starting background processing.")
        database.update_request_status(request_id, 'searching')
        
        log.info(f"[Task {request_id}]: Fetching website URL from Telegram...")
        tg_parser = TelegramParser()
        base_url = tg_parser.find_latest_zt_link()
        if not base_url:
            log.error(f"[Task {request_id}]: Could not retrieve website URL. Aborting.")
            database.update_request_status(request_id, 'failed')
            return

        log.info(f"[Task {request_id}]: Searching for media...")
        zt_parser = ZTParser(base_url=base_url)
        search_results = zt_parser.search(request_data['title'], 'series' if request_data['type'] == 'tv_show' else 'films')
        
        best_media = None
        if request_data['type'] == 'tv_show':
            best_media = select_best_show(zt_parser, search_results, request_data['title'], request_data['season'])
        else:
            best_media = select_best_movie(zt_parser, search_results, request_data['title'])

        if not best_media:
            log.error(f"[Task {request_id}]: Could not find a suitable media version. Aborting.")
            database.update_request_status(request_id, 'failed')
            return

        log.info(f"[Task {request_id}]: Found best media. Adding download links to database.")
        database.add_download_links(request_id, best_media)
        database.update_request_status(request_id, 'emitted')
        log.info(f"[Task {request_id}]: Processing complete. Waiting for user to submit links.")

    except Exception as e:
        log.error(f"[Task {request_id}]: An unhandled exception occurred in the background task!", exc_info=True)
        database.update_request_status(request_id, 'failed')

def download_worker():
    """Background worker that uses a persistent browser session."""
    log.info("[Worker]: Download worker thread started.")
    downloader = FichierDownloader()
    downloader.start_session()

    try:
        while True:
            try:
                download_id = download_queue.popleft()
            except IndexError:
                time.sleep(5)
                continue

            download_job = database.get_download_by_id(download_id)
            if not download_job or not download_job['fichier_link']:
                continue

            def status_callback(status, progress=None):
                # Only log significant status changes, not every progress update
                if status != 'downloading' or progress == 0:
                    log.info(f"[Job {download_id}]: Status -> {status}")
                database.update_download_status(download_id, status, progress)

            log.info(f"[Worker]: Starting job {download_id}...")
            downloader.download_file(download_job['fichier_link'], status_callback)
            log.info(f"[Worker]: Finished processing job {download_id}.")
    finally:
        downloader.stop_session()

# --- API Endpoints ---

@app.route('/request', methods=['POST'])
def create_request():
    data = request.get_json()
    if not data or 'title' not in data or 'type' not in data:
        return jsonify({"error": "Invalid request. Must include 'title' and 'type'"}), 400
    
    media_type = data['type']
    if media_type not in ['movie', 'tv_show']:
        return jsonify({"error": "Invalid type. Must be 'movie' or 'tv_show'"}), 400
        
    if media_type == 'tv_show' and 'season' not in data:
        return jsonify({"error": "TV show requests must include a 'season' number"}), 400

    try:
        request_id = database.add_request(data['title'], data['type'], data.get('season'))
        log.info(f"New request created with ID: {request_id}")
        thread = threading.Thread(target=process_request_task, args=(request_id, data), name=f"Task-{request_id}")
        thread.start()
        return jsonify({"message": "Request received", "request_id": request_id}), 202
    except Exception as e:
        log.error("Error creating request in /request endpoint", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/submit', methods=['POST'])
def submit_links():
    data = request.get_json()
    if not data or 'downloads' not in data or not isinstance(data['downloads'], list):
        return jsonify({"error": "Invalid request. Body must be a JSON with a 'downloads' list."}), 400

    request_id = None
    for item in data['downloads']:
        if 'id' in item and 'fichier_link' in item:
            log.info(f"Queuing download for ID: {item['id']}")
            database.update_download_with_fichier_link(item['id'], item['fichier_link'])
            download_queue.append(item['id'])
            if not request_id:
                job = database.get_download_by_id(item['id'])
                if job:
                    request_id = job['request_id']
    
    if request_id:
        database.update_request_status(request_id, 'queued')

    return jsonify({"message": f"{len(data['downloads'])} links queued for download."}), 200

@app.route('/status/<int:request_id>', methods=['GET'])
def get_status(request_id):
    status_data = database.get_request_status(request_id)
    if not status_data:
        return jsonify({"error": "Request ID not found"}), 404
    return jsonify(status_data)

# --- Main Execution ---

if __name__ == '__main__':
    worker_thread = threading.Thread(target=download_worker, name="DownloadWorker")
    worker_thread.daemon = True
    worker_thread.start()

    log.info("Starting Flask application server...")
    app.run(host='0.0.0.0', port=5000, debug=False)
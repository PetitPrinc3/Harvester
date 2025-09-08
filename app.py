import logging
import time
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_bootstrap import Bootstrap4
from waitress import serve

import database
import logger_setup
from file_parser import parse_filename
from fichier_dl import FichierDownloader

# --- App Initialization ---
logger_setup.setup_logging()
log = logging.getLogger(__name__)

# --- Logging Filter ---
class ApiQueueLogFilter(logging.Filter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_ips = set()

    def filter(self, record):
        message = record.getMessage()
        if 'GET /api/queue' in message:
            try:
                ip = message.split(' - - ')[0]
                if ip in self.seen_ips:
                    return False  # Suppress log
                else:
                    self.seen_ips.add(ip)
                    # You can customize the log message for the first connection if you want
                    # For example: record.msg = f"New viewer connected from {ip}"
                    return True # Allow log for the first time
            except IndexError:
                return True # Log if format is unexpected
        return True # Allow all other logs

# Add the filter to the Werkzeug logger, which handles request logs
logging.getLogger("werkzeug").addFilter(ApiQueueLogFilter())


app = Flask(__name__)
Bootstrap4(app)

database.init_db()

# --- Web Pages ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/queue')
def queue():
    return render_template('queue.html')

# --- API Endpoints ---

@app.route('/submit', methods=['POST'])
def submit_links():
    links = request.form.get('links', '').strip().splitlines()
    if not links:
        return redirect(url_for('index'))

    for link in links:
        if '1fichier.com' not in link:
            continue
        
        filename = get_filename_from_url(link)

        if not filename:
            log.error(f"Could not determine filename for link using Selenium: {link}")
            continue

        media_info = parse_filename(filename)

        request_id = database.add_request(
            media_info.get('title', 'Unknown Title'), 
            media_info.get('type', 'unknown'), 
            media_info.get('season')
        )
        
        with database.get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO downloads (request_id, episode_number, quality, language, fichier_link, status) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    request_id, 
                    media_info.get('episode'), 
                    media_info.get('quality'), 
                    media_info.get('language'), 
                    link, 
                    'queued'
                )
            )
            conn.commit()

    return redirect(url_for('queue'))

@app.route('/api/queue', methods=['GET'])
def get_queue():
    downloads = database.get_all_downloads()
    return jsonify(downloads)

@app.route('/api/downloads/<int:download_id>/delete', methods=['POST'])
def delete_download_api(download_id):
    database.delete_download(download_id)
    log.info(f"Deleted download {download_id} via API.")
    return jsonify({"message": "Download deleted"})

@app.route('/api/downloads/<int:download_id>/priority', methods=['POST'])
def change_priority_api(download_id):
    data = request.get_json()
    direction = data.get('direction')

    if direction not in ['up', 'down']:
        return jsonify({"error": "Invalid direction"}), 400

    all_downloads = database.get_all_downloads()
    
    try:
        current_index = next(i for i, d in enumerate(all_downloads) if d['id'] == download_id)
    except StopIteration:
        return jsonify({"error": "Download not found"}), 404

    item_to_move = all_downloads[current_index]

    if direction == 'up':
        if current_index == 0:
            return jsonify({"message": "Already at top"})
        
        neighbor = all_downloads[current_index - 1]
        
        database.update_download_priority(neighbor['id'], item_to_move['priority'])
        database.update_download_priority(item_to_move['id'], neighbor['priority'])

    elif direction == 'down':
        if current_index == len(all_downloads) - 1:
            return jsonify({"message": "Already at bottom"})
            
        neighbor = all_downloads[current_index + 1]

        database.update_download_priority(neighbor['id'], item_to_move['priority'])
        database.update_download_priority(item_to_move['id'], neighbor['priority'])

    return jsonify({"message": "Priority updated"})

# --- Background Tasks --- #

def download_worker():
    log.info("[Worker]: Download worker thread started.")
    time.sleep(5)
    downloader = FichierDownloader()
    downloader.start_session()

    try:
        while True:
            pending_downloads = database.get_pending_downloads()
            if not pending_downloads:
                time.sleep(10)
                continue

            download_job = pending_downloads[0]
            
            if download_job['status'] != 'queued':
                continue

            log.info(f"[Worker]: Starting job {download_job['id']} for link: {download_job['fichier_link']}")

            def status_callback(status, progress=None):
                if status != 'downloading' or progress == 0 or progress == 100:
                    log.info(f"[Job {download_job['id']}]: Status -> {status}, Progress -> {progress}%")
                database.update_download_status(download_job['id'], status, progress)

            try:
                database.update_download_status(download_job['id'], 'processing')
                success = downloader.download_file(download_job['fichier_link'], status_callback)
                
                if success:
                    log.info(f"[Worker]: Finished processing job {download_job['id']}.")
                    database.update_download_status(download_job['id'], 'completed', 100)
                else:
                    log.warning(f"[Worker]: Job {download_job['id']} failed. Checking retry count.")
                    database.increment_retry_count(download_job['id'])
                    job_info = database.get_download_by_id(download_job['id'])
                    if job_info['retries'] > 1:
                        log.error(f"[Worker]: Job {download_job['id']} has exceeded max retries. Marking as failed.")
                        database.update_download_status(download_job['id'], 'failed')
                    else:
                        log.info(f"[Worker]: Job {download_job['id']} will be retried. Resetting status to queued.")
                        database.update_download_status(download_job['id'], 'queued')

            except Exception as e:
                log.error(f"[Worker]: An unexpected error occurred while processing job {download_job['id']}: {e}", exc_info=True)
                database.update_download_status(download_job['id'], 'failed')
                continue

    finally:
        downloader.stop_session()

# --- Main Execution ---

if __name__ == '__main__':
    database.reset_stale_downloads()

    worker_thread = threading.Thread(target=download_worker, name="DownloadWorker")
    worker_thread.daemon = True
    worker_thread.start()

    log.info("Starting production server on http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000)
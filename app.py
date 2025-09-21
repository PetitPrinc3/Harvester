import logging
import time
import threading
import requests
import os
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap4
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from wtforms import StringField, SubmitField, TextAreaField, PasswordField
from wtforms.validators import DataRequired
from waitress import serve
from dotenv import load_dotenv
from flask_login import login_user, logout_user, login_required, current_user

load_dotenv()

import database
import logger_setup
from file_parser import parse_filename
from fichier_dl import FichierDownloader, get_filename_from_url, DownloadCancelledError
from telegram_bot import start_bot
from auth import login_manager, User, authenticate_user

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
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
Bootstrap4(app)
csrf = CSRFProtect(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

csp = {
    'default-src': '\'self\'',
    'script-src': [
        '\'self\'',
        'cdn.jsdelivr.net',
        '\'unsafe-inline\''
    ],
    'style-src': [
        '\'self\'',
        'cdn.jsdelivr.net',
        '\'unsafe-inline\''
    ],
    'connect-src': [
        '\'self\'',
        'cdn.jsdelivr.net'
    ]
}
Talisman(app, content_security_policy=csp, force_https=False, session_cookie_secure=False)

database.init_db()

# --- Forms ---

class LinkSubmissionForm(FlaskForm):
    links = TextAreaField('Links', validators=[DataRequired()])
    submit = SubmitField('Submit')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# --- Web Pages ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        if authenticate_user(username, password):
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    form = LinkSubmissionForm()
    return render_template('index.html', form=form)

@app.route('/queue')
@login_required
def queue():
    return render_template('queue.html')

# --- API Endpoints ---

@app.route('/submit', methods=['POST'])
@login_required
def submit_links():
    form = LinkSubmissionForm()
    if form.validate_on_submit():
        links = form.links.data.strip().splitlines()
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
                    "INSERT INTO downloads (request_id, episode_number, quality, language, fichier_link, status, priority) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        request_id, 
                        media_info.get('episode'), 
                        media_info.get('quality'), 
                        media_info.get('language'), 
                        link, 
                        'queued',
                        time.time()
                    )
                )
                conn.commit()

    return redirect(url_for('queue'))

@app.route('/api/queue', methods=['GET'])
@login_required
def get_queue():
    downloads = database.get_all_downloads()
    return jsonify(downloads)

@app.route('/api/downloads/<int:download_id>/delete', methods=['POST'])
@login_required
def delete_download_api(download_id):
    database.delete_download(download_id)
    log.info(f"Deleted download {download_id} via API.")
    return jsonify({"message": "Download deleted"})

@app.route('/api/downloads/<int:download_id>/priority', methods=['POST'])
@login_required
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

    if direction == 'up':
        if current_index == 0:
            return jsonify({"message": "Already at top"})
        
        swap_with_index = current_index - 1
        
    elif direction == 'down':
        if current_index == len(all_downloads) - 1:
            return jsonify({"message": "Already at bottom"})
            
        swap_with_index = current_index + 1

    all_downloads.insert(swap_with_index, all_downloads.pop(current_index))
    
    download_ids = [d['id'] for d in all_downloads]
    database.update_priorities(download_ids)

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
            
            # --- Pre-download check ---
            # Verify that the job hasn't been deleted by the user since being queued.
            if not database.get_download_by_id(download_job['id']):
                log.warning(f"[Worker]: Job {download_job['id']} was deleted from the queue. Skipping.")
                continue

            if download_job['status'] != 'queued':
                continue

            log.info(f"[Worker]: Starting job {download_job['id']} for link: {download_job['fichier_link']}")

            def status_callback(status, progress=None):
                # To prevent errors if the job is deleted mid-process, check if it still exists.
                if database.get_download_by_id(download_job['id']):
                    # Log status changes, but not every single progress update for 'downloading'.
                    if status not in ['downloading', 'pending'] or progress in [0, 100]:
                        log.info(f"[Job {download_job['id']}]: Status -> {status}, Progress -> {progress if progress is not None else 'N/A'}%")
                    database.update_download_status(download_job['id'], status, progress)

            def cancellation_callback():
                """Returns True if the download job has been deleted."""
                return database.get_download_by_id(download_job['id']) is None

            try:
                success = downloader.download_file(
                    download_job['fichier_link'], 
                    status_callback,
                    cancellation_callback
                )
                
                if success:
                    log.info(f"[Worker]: Finished processing job {download_job['id']}.")
                    database.update_download_status(download_job['id'], 'completed', 100)
                else:
                    # If the job failed (but wasn't cancelled), it will still exist in the DB.
                    job_info = database.get_download_by_id(download_job['id'])
                    if job_info:
                        log.warning(f"[Worker]: Job {download_job['id']} failed. Checking retry count.")
                        database.increment_retry_count(download_job['id'])
                        # Re-fetch to get the updated retry count
                        job_info = database.get_download_by_id(download_job['id'])
                        if job_info['retries'] > 1:
                            log.error(f"[Worker]: Job {download_job['id']} has exceeded max retries. Marking as failed.")
                            database.update_download_status(download_job['id'], 'failed')
                        else:
                            log.info(f"[Worker]: Job {download_job['id']} will be retried. Resetting status to queued.")
                            database.update_download_status(download_job['id'], 'queued')
                    # If job_info is None, it was cancelled, and we just loop to the next job.

            except Exception as e:
                log.error(f"[Worker]: An unexpected error occurred while processing job {download_job['id']}: {e}", exc_info=True)
                # Check if job exists before updating its status to failed.
                if database.get_download_by_id(download_job['id']):
                    database.update_download_status(download_job['id'], 'failed')
                continue

    finally:
        downloader.stop_session()

# --- Main Execution ---

if __name__ == '__main__':
    database.reset_stale_downloads()

    # Start the Telegram bot in a background thread
    bot_thread = threading.Thread(target=start_bot, name="TelegramBot")
    bot_thread.daemon = True
    bot_thread.start()

    # Start the download worker in a background thread
    worker_thread = threading.Thread(target=download_worker, name="DownloadWorker")
    worker_thread.daemon = True
    worker_thread.start()

    log.info("Starting production server on http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000)
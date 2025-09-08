import sqlite3
import logging

log = logging.getLogger(__name__)
DB_PATH = 'harvester.db'

def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    log.info(f"Initializing database at '{DB_PATH}'...")
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                season INTEGER, 
                type TEXT NOT NULL, 
                status TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                episode_number INTEGER,
                quality TEXT,
                language TEXT,
                dl_protect_link TEXT,
                fichier_link TEXT,
                status TEXT NOT NULL,
                download_progress REAL DEFAULT 0,
                retries INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                FOREIGN KEY (request_id) REFERENCES requests (id)
            )
        ''')
        conn.commit()
    log.info("Database initialized successfully.")

def add_request(title, media_type, season=None):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO requests (title, season, type, status) VALUES (?, ?, ?, ?)",
            (title, season, media_type, 'analyzing')
        )
        conn.commit()
        return cursor.lastrowid

def update_request_status(request_id, status):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()

def add_download_links(request_id, media_data):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if media_data.get('episode_data'):
            for episode in media_data['episode_data']:
                cursor.execute(
                    "INSERT INTO downloads (request_id, episode_number, quality, language, dl_protect_link, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (request_id, episode['episode_number'], media_data['quality'], media_data['language'], episode['dl_protect_link'], 'pending_captcha')
                )
        else:
            cursor.execute(
                "INSERT INTO downloads (request_id, quality, language, dl_protect_link, status) VALUES (?, ?, ?, ?, ?)",
                (request_id, media_data['quality'], media_data['language'], media_data['dl_protect_link'], 'pending_captcha')
            )
        conn.commit()

def update_download_with_fichier_link(download_id, fichier_link):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE downloads SET fichier_link = ?, status = ? WHERE id = ?",
            (fichier_link, 'queued', download_id)
        )
        conn.commit()

def update_download_status(download_id, status, progress=None):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if progress is not None:
            cursor.execute("UPDATE downloads SET status = ?, download_progress = ? WHERE id = ?", (status, progress, download_id))
        else:
            cursor.execute("UPDATE downloads SET status = ? WHERE id = ?", (status, download_id))
        conn.commit()

def get_request_status(request_id):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM requests WHERE id = ?", (request_id,))
        request_info = cursor.fetchone()
        if not request_info:
            return None
        request_info = dict(request_info)
        cursor.execute("SELECT * FROM downloads WHERE request_id = ? ORDER BY episode_number", (request_id,))
        downloads_info = [dict(row) for row in cursor.fetchall()]
        request_info['downloads'] = downloads_info
        return request_info

def get_download_by_id(download_id):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM downloads WHERE id = ?", (download_id,))
        result = cursor.fetchone()
        return dict(result) if result else None

def get_all_requests():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM requests ORDER BY timestamp DESC")
        requests = [dict(row) for row in cursor.fetchall()]
        return requests

def get_downloads_for_request(request_id):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM downloads WHERE request_id = ?", (request_id,))
        downloads = [dict(row) for row in cursor.fetchall()]
        return downloads

def get_request_by_id(request_id):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM requests WHERE id = ?", (request_id,))
        result = cursor.fetchone()
        return dict(result) if result else None

def get_all_downloads():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, r.title, r.type as request_type, r.season
            FROM downloads d
            JOIN requests r ON d.request_id = r.id
            ORDER BY d.priority DESC, d.id ASC
        """)
        downloads = [dict(row) for row in cursor.fetchall()]
        return downloads

def get_active_queue():
    """Gets all downloads that are not completed."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.id, d.status, d.download_progress, r.title, r.season, d.episode_number
            FROM downloads d
            JOIN requests r ON d.request_id = r.id
            WHERE d.status != 'completed'
            ORDER BY d.priority DESC, r.timestamp ASC, d.id ASC
        """)
        queue = [dict(row) for row in cursor.fetchall()]
        return queue


def get_pending_downloads():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, r.title
            FROM downloads d
            JOIN requests r ON d.request_id = r.id
            WHERE d.status = 'queued' 
            ORDER BY d.priority DESC, d.id ASC
        """)
        downloads = [dict(row) for row in cursor.fetchall()]
        return downloads

def reset_stale_downloads():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE downloads SET status = 'queued', download_progress = 0 WHERE status IN ('downloading', 'processing', 'pending')")
        conn.commit()
        log.info(f"{cursor.rowcount} stale downloads have been reset to 'queued'.")

def update_download_priority(download_id, priority):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE downloads SET priority = ? WHERE id = ?", (priority, download_id))
        conn.commit()

def delete_download(download_id):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
        conn.commit()

def increment_retry_count(download_id):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE downloads SET retries = retries + 1 WHERE id = ?", (download_id,))
        conn.commit()

def is_link_already_added(fichier_link):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM downloads WHERE fichier_link = ?", (fichier_link,))
        return cursor.fetchone() is not None

if __name__ == '__main__':
    import logger_setup
    logger_setup.setup_logging()
    init_db()
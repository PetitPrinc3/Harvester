import logging
import sys
import os
from dotenv import load_dotenv
from tqdm import tqdm

class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=sys.stdout)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

class NoDownloadProgressFilter(logging.Filter):
    """A custom log filter to exclude download progress messages."""
    def filter(self, record):
        return "Progress" not in record.getMessage()

class EmojiFormatter(logging.Formatter):
    """A custom log formatter to add emojis to log messages."""
    
    EMOJI_MAP = {
        'DownloadWorker': '📥',
        'TelegramBot': '🤖',
        'Harvester': '🚜',
        'MainThread': '🚀',
        'telegram_notifier': '📢'
    }

    LEVEL_MAP = {
        logging.INFO: 'ℹ️',
        logging.WARNING: '⚠️',
        logging.ERROR: '❌',
        logging.CRITICAL: '🔥',
        logging.DEBUG: '🐛'
    }

    def format(self, record):
        # Get emoji for thread/module
        thread_emoji = self.EMOJI_MAP.get(record.threadName, '⚙️')

        # Get emoji for log level
        level_emoji = self.LEVEL_MAP.get(record.levelno, '📝')

        # Set the new record format
        record.threadName = thread_emoji
        record.levelname = f"{level_emoji} {record.levelname}"
        
        # Let the parent class do the actual formatting
        return super().format(record)

def setup_logging():
    """Configures the root logger for the application."""
    load_dotenv()
    log_filename = os.getenv('LOG_FILENAME', 'harvester.log')
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Use the custom EmojiFormatter
    formatter = EmojiFormatter(
        '%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )

    # Console handler (without download progress)
    stream_handler = TqdmLoggingHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(NoDownloadProgressFilter())

    # File handler (with all logs)
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

if __name__ == '__main__':
    setup_logging()
    logging.info("Logger has been set up. This is an info message.")
    logging.warning("This is a warning message.")
    logging.error("This is an error message.")
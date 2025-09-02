import logging
import sys
import os
from dotenv import load_dotenv

def setup_logging():
    """Configures the root logger for the application."""
    # Load environment variables from .env file
    load_dotenv()

    # Get the log filename from environment variable, with a default fallback
    log_filename = os.getenv('LOG_FILENAME', 'harvester.log')

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Create a formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )

    # Create a handler to write to the console (stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    # Create a handler to write to a file
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Add the handlers to the root logger if they haven't been added yet
    if not logger.handlers:
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

if __name__ == '__main__':
    setup_logging()
    logging.info("Logger has been set up. This is an info message.")
    logging.warning("This is a warning message.")
    logging.error("This is an error message.")
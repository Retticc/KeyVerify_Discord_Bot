import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta

def setup_logging(log_level_str):
    logging_level = getattr(logging, log_level_str.upper(), logging.INFO)

    # Ensure logs/ folder exists
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Use a consistent base log file name — no date here
    base_log_file = os.path.join(log_dir, "bot.log")

    # File handler with daily rotation, automatically suffixes with date
    handler = TimedRotatingFileHandler(
        base_log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=True  # Optional: use True if you're deploying globally
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Set up root logger safely
    logger = logging.getLogger()
    logger.setLevel(logging_level)

    # Avoid duplicate handlers
    if not any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers):
        logger.addHandler(handler)

    # Add console output (only once)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(console_handler)

    # Optional: Clean up old log files beyond backupCount
    delete_old_logs(log_dir, days=7)

def delete_old_logs(log_dir, days=7):
    now = datetime.now()
    for filename in os.listdir(log_dir):
        file_path = os.path.join(log_dir, filename)
        if os.path.isfile(file_path):
            try:
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if (now - file_time).days > days:
                    os.remove(file_path)
            except Exception as e:
                logging.warning(f"Could not delete log file {filename}: {e}")

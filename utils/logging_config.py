import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta

def setup_logging(log_level_str):
    logging_level = getattr(logging, log_level_str.upper(), logging.INFO)

    # Ensure logs/ folder exists
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # File name with today's date
    log_file = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".log")

    # File handler with daily rotation
    handler = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=7, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Set up root logger
    logger = logging.getLogger()
    logger.setLevel(logging_level)
    logger.addHandler(handler)

    # Console output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(console_handler)

    # Cleanup old log files
    delete_old_logs(log_dir, days=7)

def delete_old_logs(log_dir, days=7):
    now = datetime.now()
    for filename in os.listdir(log_dir):
        file_path = os.path.join(log_dir, filename)
        if os.path.isfile(file_path):
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if (now - file_time).days > days:
                os.remove(file_path)

import logging

def setup_logging(level):
    logging_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=logging_level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

import logging
import os
from logging.handlers import TimedRotatingFileHandler


LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "watcher.log"
LOG_BACKUP_PREFIX = LOG_FILE_NAME + "."
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_log_dir(base_dir: str = None) -> str:
    root = base_dir or os.getcwd()
    return os.path.join(root, LOG_DIR_NAME)


def setup_logging(base_dir: str = None) -> None:
    log_dir = get_log_dir(base_dir)
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, LOG_FILE_NAME),
        when="midnight",
        interval=1,
        backupCount=0,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

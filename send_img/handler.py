import logging
import os
import time
from datetime import datetime
from typing import Optional

from watchdog.events import FileSystemEventHandler

from send_img.delivery import ALLOWED_CHANNELS, try_send_with_retries


def build_processed_key(path: str) -> str:
    stat = os.stat(path)
    return f"{path}|{stat.st_mtime_ns}|{stat.st_size}"


def wait_for_stable_file(path: str, checks: int, interval: float) -> bool:
    """
    通过检测文件大小稳定来判断文件是否写完。
    """
    last = -1
    for _ in range(checks):
        try:
            size = os.path.getsize(path)
        except OSError:
            return False

        if size == last:
            return True

        last = size
        time.sleep(interval)

    return False


def handle_file_event(filepath: str, compiled_rules, store, general: dict, event_type: str) -> None:
    abs_path = os.path.abspath(filepath)

    store.rollover_if_needed()

    if general.get("ignore_office_temp", True) and os.path.basename(abs_path).startswith("~$"):
        return

    if not wait_for_stable_file(
        abs_path,
        int(general.get("stable_checks", 6)),
        float(general.get("stable_wait", 0.5)),
    ):
        logging.warning(f"File not stable: {abs_path}, skipping.")
        return

    try:
        processed_key = build_processed_key(abs_path)
    except OSError:
        logging.warning(f"Failed to stat file after stabilization: {abs_path}")
        return

    if store.contains(processed_key):
        logging.debug(f"Already processed {event_type} event: {processed_key}")
        return

    filename = os.path.basename(abs_path)
    logging.info(f"Detected {event_type} file event: {filename}")

    retry_count = int(general.get("retry_count", 3))
    retry_delay = float(general.get("retry_delay", 2))
    matched_rule = next((rule for rule, regex in compiled_rules if regex.match(filename)), None)

    if matched_rule:
        if _send_to_recipients(abs_path, matched_rule, general, retry_count, retry_delay):
            store.mark(processed_key)
            logging.info(f"Marked processed: {processed_key}")
        else:
            logging.warning(f"Send incomplete, processed key not marked: {processed_key}")
    else:
        logging.debug(f"No matching rule for {filename}")


def _send_to_recipients(
    filepath: str,
    rule: dict,
    general: dict,
    retry_count: int,
    retry_delay: float,
) -> bool:
    attempted = False
    all_succeeded = True

    for recipient in rule.get("recipients", []):
        user_id = recipient.get("user_id")
        for channel in recipient.get("channels", []):
            attempted = True
            if channel not in ALLOWED_CHANNELS:
                logging.error(f"Unknown channel '{channel}' for user:{user_id}; skipping")
                all_succeeded = False
                continue

            if not try_send_with_retries(filepath, channel, recipient, general, retry_count, retry_delay):
                all_succeeded = False

    return attempted and all_succeeded


def scan_existing_files(
    watch_dir: str,
    recursive: bool,
    compiled_rules,
    store,
    general: dict,
    modified_since: Optional[datetime] = None,
) -> None:
    if not os.path.exists(watch_dir):
        return

    if recursive:
        path_iter = (
            os.path.join(dirpath, name)
            for dirpath, _, filenames in os.walk(watch_dir)
            for name in filenames
        )
    else:
        path_iter = (
            os.path.join(watch_dir, name)
            for name in os.listdir(watch_dir)
            if os.path.isfile(os.path.join(watch_dir, name))
        )

    files_to_scan = []
    cutoff = modified_since.timestamp() if modified_since else None

    for path in path_iter:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue

        if cutoff is not None and mtime < cutoff:
            continue

        files_to_scan.append((mtime, path))

    for _, path in sorted(files_to_scan):
        handle_file_event(path, compiled_rules, store, general, "scan")


class FileHandler(FileSystemEventHandler):
    def __init__(self, compiled_rules, store, general: dict):
        self.compiled_rules = compiled_rules
        self.store = store
        self.general = general

    def _handle_event(self, event, event_type: str) -> None:
        if event.is_directory:
            return
        handle_file_event(event.src_path, self.compiled_rules, self.store, self.general, event_type)

    def on_created(self, event):
        self._handle_event(event, "created")

    def on_modified(self, event):
        self._handle_event(event, "modified")

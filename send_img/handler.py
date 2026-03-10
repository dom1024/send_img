import logging
import os
import time

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

    matched = False

    for rule, regex in compiled_rules:
        if regex.match(filename):
            matched = True

            for rec in rule.get("recipients", []):
                uid = rec.get("user_id")
                for ch in rec.get("channels", []):
                    if ch not in ALLOWED_CHANNELS:
                        logging.error(f"Unknown channel '{ch}' for user:{uid}; skipping")
                        continue

                    try_send_with_retries(abs_path, ch, uid, retry_count, retry_delay)

            break

    if matched:
        store.mark(processed_key)
        logging.info(f"Marked processed: {processed_key}")
    else:
        logging.debug(f"No matching rule for {filename}")


class FileHandler(FileSystemEventHandler):
    def __init__(self, compiled_rules, store, general: dict):
        self.compiled_rules = compiled_rules
        self.store = store
        self.general = general

    def on_created(self, event):
        if event.is_directory:
            return
        handle_file_event(
            event.src_path,
            self.compiled_rules,
            self.store,
            self.general,
            "created",
        )

    def on_modified(self, event):
        if event.is_directory:
            return
        handle_file_event(
            event.src_path,
            self.compiled_rules,
            self.store,
            self.general,
            "modified",
        )

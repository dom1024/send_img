import logging
import os
import time


def _iter_files(root: str, recursive: bool):
    if not os.path.exists(root):
        return

    if recursive:
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                yield os.path.join(dirpath, name)
        return

    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            yield path


def cleanup_old_watch_files(watch_dir: str, recursive: bool, retention_days: int) -> int:
    if retention_days <= 0:
        return 0

    cutoff = time.time() - retention_days * 24 * 60 * 60
    deleted = 0

    for path in _iter_files(watch_dir, recursive):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
                logging.info(f"Removed expired data file: {path}")
        except FileNotFoundError:
            continue
        except OSError as exc:
            logging.warning(f"Failed to remove expired data file {path}: {exc}")

    return deleted


def cleanup_old_processed_logs(processed_base: str, retention_days: int) -> int:
    if retention_days <= 0:
        return 0

    log_dir = os.path.dirname(processed_base) or "."
    prefix = os.path.basename(processed_base) + "_"
    cutoff = time.time() - retention_days * 24 * 60 * 60
    deleted = 0

    if not os.path.exists(log_dir):
        return 0

    for name in os.listdir(log_dir):
        path = os.path.join(log_dir, name)
        if not os.path.isfile(path):
            continue
        if not name.startswith(prefix) or not name.endswith(".txt"):
            continue

        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
                logging.info(f"Removed expired processed log: {path}")
        except FileNotFoundError:
            continue
        except OSError as exc:
            logging.warning(f"Failed to remove expired processed log {path}: {exc}")

    return deleted


def run_cleanup(general: dict) -> None:
    retention_days = int(general.get("retention_days", 30))
    watch_dir = general.get("watch_dir", "./incoming")
    recursive = bool(general.get("recursive", True))
    processed_base = general.get("processed_base", ".processed_files")

    deleted_data = cleanup_old_watch_files(watch_dir, recursive, retention_days)
    deleted_logs = cleanup_old_processed_logs(processed_base, retention_days)

    if deleted_data or deleted_logs:
        logging.info(
            "Cleanup finished: removed %s data files and %s processed logs.",
            deleted_data,
            deleted_logs,
        )

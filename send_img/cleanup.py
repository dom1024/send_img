import logging
import os
import time

from send_img.logging_utils import LOG_BACKUP_PREFIX, get_log_dir


SECONDS_PER_DAY = 24 * 60 * 60


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


def _remove_expired_files(paths, cutoff: float, label: str) -> int:
    deleted = 0

    for path in paths:
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
                logging.info(f"Removed expired {label}: {path}")
        except FileNotFoundError:
            continue
        except OSError as exc:
            logging.warning(f"Failed to remove expired {label} {path}: {exc}")

    return deleted


def _build_cutoff(retention_days: int) -> float:
    return time.time() - retention_days * SECONDS_PER_DAY


def _iter_processed_log_paths(processed_base: str):
    log_dir = os.path.dirname(processed_base) or "."
    prefix = os.path.basename(processed_base) + "_"

    if not os.path.exists(log_dir):
        return

    for name in os.listdir(log_dir):
        if name.startswith(prefix) and name.endswith(".txt"):
            yield os.path.join(log_dir, name)


def _load_all_processed_keys(processed_base: str) -> set:
    processed_keys = set()

    for path in _iter_processed_log_paths(processed_base) or ():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                processed_keys.update(line.strip() for line in handle if line.strip())
        except OSError as exc:
            logging.warning("Failed to read processed log %s: %s", path, exc)

    return processed_keys


def _build_processed_key(path: str) -> str:
    stat = os.stat(path)
    return f"{path}|{stat.st_mtime_ns}|{stat.st_size}"


def cleanup_old_watch_files(
    watch_dir: str,
    recursive: bool,
    retention_days: int,
    processed_base: str,
) -> int:
    if retention_days <= 0:
        return 0

    cutoff = _build_cutoff(retention_days)
    processed_keys = _load_all_processed_keys(processed_base)
    deleted = 0

    for path in _iter_files(watch_dir, recursive) or ():
        try:
            if os.path.getmtime(path) >= cutoff:
                continue

            processed_key = _build_processed_key(path)
            if processed_key not in processed_keys:
                logging.debug("Keeping expired but unprocessed data file: %s", path)
                continue

            os.remove(path)
            deleted += 1
            logging.info("Removed expired processed data file: %s", path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            logging.warning("Failed to remove expired data file %s: %s", path, exc)

    return deleted


def cleanup_old_processed_logs(processed_base: str, retention_days: int) -> int:
    if retention_days <= 0:
        return 0

    log_dir = os.path.dirname(processed_base) or "."
    prefix = os.path.basename(processed_base) + "_"

    if not os.path.exists(log_dir):
        return 0

    paths = (
        os.path.join(log_dir, name)
        for name in os.listdir(log_dir)
        if name.startswith(prefix) and name.endswith(".txt")
    )
    return _remove_expired_files(paths, _build_cutoff(retention_days), "processed log")


def cleanup_old_runtime_logs(retention_days: int, base_dir: str = None) -> int:
    if retention_days <= 0:
        return 0

    log_dir = get_log_dir(base_dir)
    if not os.path.exists(log_dir):
        return 0

    paths = (
        os.path.join(log_dir, name)
        for name in os.listdir(log_dir)
        if name.startswith(LOG_BACKUP_PREFIX)
    )
    return _remove_expired_files(paths, _build_cutoff(retention_days), "runtime log")


def run_cleanup(general: dict) -> None:
    retention_days = int(general.get("retention_days", 30))
    watch_dir = general.get("watch_dir", "./incoming")
    recursive = bool(general.get("recursive", True))
    processed_base = general.get("processed_base", ".processed_files")

    deleted_data = cleanup_old_watch_files(watch_dir, recursive, retention_days, processed_base)
    deleted_processed_logs = cleanup_old_processed_logs(processed_base, retention_days)
    deleted_runtime_logs = cleanup_old_runtime_logs(retention_days)

    if deleted_data or deleted_processed_logs or deleted_runtime_logs:
        logging.info(
            "Cleanup finished: removed %s data files, %s processed logs, and %s runtime logs.",
            deleted_data,
            deleted_processed_logs,
            deleted_runtime_logs,
        )

import logging
import os
import time
from datetime import date, datetime, time as dt_time, timedelta

from watchdog.observers import Observer

from send_img.cleanup import run_cleanup
from send_img.config import load_config
from send_img.handler import FileHandler, scan_existing_files
from send_img.rules import compile_rules
from send_img.store import ProcessedStore


def refresh_daily_state(config: dict, current_day: date, store: ProcessedStore, handler: FileHandler) -> None:
    store.rollover_if_needed()
    handler.compiled_rules = compile_rules(config, current_day)


def parse_clock(value: str, default: str) -> dt_time:
    raw = (value or default).strip()
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        logging.warning(f"Invalid clock value '{raw}', fallback to {default}")
        return datetime.strptime(default, "%H:%M").time()


def is_in_run_window(now: datetime, start_time: dt_time, stop_time: dt_time) -> bool:
    current = now.time().replace(second=0, microsecond=0)
    return start_time <= current < stop_time


def next_window_start(now: datetime, start_time: dt_time) -> datetime:
    candidate = datetime.combine(now.date(), start_time)
    if now < candidate:
        return candidate
    return candidate + timedelta(days=1)


def previous_window_stop(now: datetime, stop_time: dt_time) -> datetime:
    candidate = datetime.combine(now.date(), stop_time)
    if now >= candidate:
        return candidate
    return candidate - timedelta(days=1)


def sleep_until(target: datetime) -> None:
    while True:
        seconds = (target - datetime.now()).total_seconds()
        if seconds <= 0:
            return
        time.sleep(min(seconds, 30))


def start_observer(watch_dir: str, recursive: bool, handler: FileHandler) -> Observer:
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=recursive)
    observer.start()
    return observer


def stop_observer(observer: Observer) -> None:
    observer.stop()
    observer.join()


def main() -> None:
    config = load_config("config.yaml")
    general = config.get("general", {})

    today = date.today()
    compiled_rules = compile_rules(config, today)

    store = ProcessedStore(general.get("processed_base", ".processed_files"))

    watch_dir = general.get("watch_dir", "./incoming")
    recursive = bool(general.get("recursive", True))
    start_time = parse_clock(general.get("run_start", "06:00"), "06:00")
    stop_time = parse_clock(general.get("run_stop", "23:59"), "23:59")

    os.makedirs(watch_dir, exist_ok=True)
    handler = FileHandler(compiled_rules, store, general)
    observer = None
    active_day = None

    try:
        while True:
            now = datetime.now()
            current_day = now.date()
            in_window = is_in_run_window(now, start_time, stop_time)

            if in_window and observer is None:
                refresh_daily_state(config, current_day, store, handler)
                run_cleanup(general)
                scan_existing_files(
                    watch_dir,
                    recursive,
                    handler.compiled_rules,
                    store,
                    general,
                    modified_since=previous_window_stop(now, stop_time),
                )
                observer = start_observer(watch_dir, recursive, handler)
                active_day = current_day
                logging.info(
                    "Watcher active from %s to %s for %s",
                    start_time.strftime("%H:%M"),
                    stop_time.strftime("%H:%M"),
                    watch_dir,
                )
                continue

            if not in_window and observer is not None:
                logging.info("Run window ended at %s, watcher entering sleep.", stop_time.strftime("%H:%M"))
                stop_observer(observer)
                observer = None
                active_day = None
                continue

            if observer is None:
                wake_up = next_window_start(now, start_time)
                logging.info("Watcher sleeping until %s", wake_up.strftime("%Y-%m-%d %H:%M"))
                sleep_until(wake_up)
                continue

            if current_day != active_day:
                refresh_daily_state(config, current_day, store, handler)
                run_cleanup(general)
                active_day = current_day
                logging.info("Rolled to new day: rules & store refreshed.")

            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down watcher...")
        if observer is not None:
            stop_observer(observer)

import logging
import os
import time
from datetime import date

from watchdog.observers import Observer

from send_img.cleanup import run_cleanup
from send_img.config import load_config
from send_img.handler import FileHandler
from send_img.rules import compile_rules
from send_img.store import ProcessedStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main() -> None:
    config = load_config("config.yaml")
    general = config.get("general", {})

    today = date.today()
    compiled_rules = compile_rules(config, today)

    store = ProcessedStore(general.get("processed_base", ".processed_files"))

    watch_dir = general.get("watch_dir", "./incoming")
    os.makedirs(watch_dir, exist_ok=True)
    run_cleanup(general)

    observer = Observer()
    handler = FileHandler(compiled_rules, store, general)
    observer.schedule(
        handler,
        watch_dir,
        recursive=bool(general.get("recursive", True)),
    )
    observer.start()

    logging.info(f"Watching {watch_dir} recursively for new files...")

    try:
        current_day = date.today()
        while True:
            time.sleep(1)

            if date.today() != current_day:
                current_day = date.today()
                store.rollover_if_needed()
                handler.compiled_rules = compile_rules(config, current_day)
                run_cleanup(general)
                logging.info("Rolled to new day: rules & store refreshed.")
    except KeyboardInterrupt:
        logging.info("Shutting down watcher...")
        observer.stop()

    observer.join()

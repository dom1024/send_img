import logging
import os
from datetime import date


class ProcessedStore:
    """
    按自然日记录已处理的文件版本键，跨日自动切换文件并清空内存集合。
    文件名形如：{processed_base}_YYYYMMDD.txt
    """

    def __init__(self, base_name: str):
        self.base_name = base_name
        self.day = self._today_str()
        self.path = self._path_for(self.day)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._set = self._load(self.path)

    def _today_str(self) -> str:
        return date.today().strftime("%Y%m%d")

    def _path_for(self, day_str: str) -> str:
        return f"{self.base_name}_{day_str}.txt"

    def _load(self, path: str) -> set:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def contains(self, processed_key: str) -> bool:
        return processed_key in self._set

    def mark(self, processed_key: str) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(processed_key + "\n")
        self._set.add(processed_key)

    def rollover_if_needed(self) -> None:
        now_day = self._today_str()
        if now_day != self.day:
            logging.info("New day detected, resetting processed set...")
            self.day = now_day
            self.path = self._path_for(self.day)
            self._set = self._load(self.path)

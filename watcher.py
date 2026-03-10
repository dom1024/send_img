# watcher.py

import os
import re
import yaml
import time
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class ProcessedStore:
    """
    按自然日记录已处理的完整文件路径，跨日自动切换文件并清空内存集合。
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

    def contains(self, filepath: str) -> bool:
        return filepath in self._set

    def mark(self, filepath: str) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(filepath + "\n")
        self._set.add(filepath)

    def rollover_if_needed(self) -> None:
        now_day = self._today_str()
        if now_day != self.day:
            logging.info("New day detected, resetting processed set...")
            self.day = now_day
            self.path = self._path_for(self.day)
            self._set = self._load(self.path)


def parse_date_spec(spec: str, today: date) -> date:
    """
    支持:
    - T / T-0 / T+0
    - T-1 / T-7 ...
    - YYYY-MM-DD
    """
    if not spec:
        return today

    s = str(spec).strip().upper()

    if s in ("T", "T-0", "T+0"):
        return today

    if s.startswith("T-"):
        try:
            n = int(s[2:])
            return today - timedelta(days=n)
        except ValueError:
            logging.warning(f"Invalid date spec '{spec}', fallback to T")
            return today

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            logging.warning(f"Invalid absolute date '{spec}', fallback to T")
            return today

    logging.warning(f"Unknown date spec '{spec}', fallback to T")
    return today


def compute_params(
    today: date,
    general_params: Dict[str, Any],
    rule_params: Optional[Dict[str, Any]]
) -> Dict[str, str]:
    """
    先计算 general.params，再用 rule.params 覆盖。
    支持:
    - type: date/string/number
    - date: spec + format
    - string/number: value
    """
    result: Dict[str, str] = {}

    # 1) 全局参数
    for name, cfg in (general_params or {}).items():
        typ = (cfg.get("type") if isinstance(cfg, dict) else None) or "string"

        if typ == "date":
            spec = cfg.get("spec", "T")
            fmt = cfg.get("format", "%Y-%m-%d")
            d = parse_date_spec(spec, today)
            result[name] = d.strftime(fmt)
        elif typ in ("int", "number"):
            result[name] = str(cfg.get("value", 0))
        else:
            result[name] = str(cfg.get("value", ""))

    # 2) 规则级覆盖
    for name, override in (rule_params or {}).items():
        base_cfg = (general_params or {}).get(name, {}) or {}
        base_type = base_cfg.get("type", "string")

        if isinstance(override, dict):
            typ = override.get("type", base_type)
            if typ == "date":
                spec = override.get("spec", base_cfg.get("spec", "T"))
                fmt = override.get("format", base_cfg.get("format", "%Y-%m-%d"))
                d = parse_date_spec(spec, today)
                result[name] = d.strftime(fmt)
            elif typ in ("int", "number"):
                result[name] = str(override.get("value", 0))
            else:
                result[name] = str(override.get("value", ""))
        else:
            if base_type == "date":
                d = parse_date_spec(str(override), today)
                fmt = base_cfg.get("format", "%Y-%m-%d")
                result[name] = d.strftime(fmt)
            else:
                result[name] = str(override)

    return result


def render_name_template(template: str, params: Dict[str, str]) -> Optional[str]:
    """
    将模板中的 {param} 替换成实际参数值。
    缺失参数时返回 None。
    """
    missing = []

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in params:
            return params[key]
        missing.append(key)
        return ""

    rendered = re.sub(r"{([A-Za-z0-9_]+)}", repl, template)

    if missing:
        logging.warning(f"Missing params {missing} for template '{template}', rule skipped")
        return None

    return rendered


_regex_cache = {}


def name_to_regex(template: str, params: Dict[str, str], ignore_case: bool) -> Optional[re.Pattern]:
    """
    先渲染模板，再把 * 和 ? 当成通配符转正则。
    """
    rendered = render_name_template(template, params)
    if rendered is None:
        return None

    cache_key = (rendered, ignore_case)
    if cache_key in _regex_cache:
        return _regex_cache[cache_key]

    s = re.escape(rendered)
    s = s.replace(r"\*", ".*").replace(r"\?", ".")

    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile("^" + s + "$", flags)
    _regex_cache[cache_key] = regex
    return regex


def compile_rules(config: dict, today: date):
    """
    根据“今天”计算出当日有效规则：
    - 先算参数
    - 再渲染模板
    - 再编译成正则
    """
    general = config.get("general", {})
    ignore_case = bool(general.get("case_insensitive", False))
    general_params = general.get("params", {})

    compiled = []
    for rule in config.get("file_rules", []):
        name_tpl = (rule.get("name") or "").strip()
        if not name_tpl:
            continue

        params = compute_params(today, general_params, rule.get("params"))
        regex = name_to_regex(name_tpl, params, ignore_case)
        if regex is None:
            continue

        compiled.append((rule, regex))

    return compiled


def send_via_channel(filepath: str, channel: str, user_id: str) -> None:
    """
    统一发送入口。
    你只需要在这里根据 channel + user_id 实现真实发送。
    """
    if channel == "email":
        logging.info(f"[EMAIL] {filepath} -> user:{user_id}")
        # TODO: 调用 SMTP 发送
    elif channel == "chat":
        logging.info(f"[CHAT]  {filepath} -> user:{user_id}")
        # TODO: 调用聊天工具 API 发送
    else:
        raise ValueError(f"Unknown channel: {channel}")


def try_send_with_retries(
    filepath: str,
    channel: str,
    user_id: str,
    retry_count: int,
    retry_delay: float
) -> bool:
    for i in range(1, retry_count + 1):
        try:
            send_via_channel(filepath, channel, user_id)
            return True
        except Exception as e:
            logging.warning(
                f"Attempt {i}/{retry_count} failed ({channel}) "
                f"for {filepath} -> user:{user_id}: {e}"
            )
            time.sleep(retry_delay)

    logging.error(f"All attempts failed ({channel}) for {filepath} -> user:{user_id}")
    return False


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


ALLOWED_CHANNELS = {"email", "chat"}


def handle_new_file(filepath: str, compiled_rules, store: ProcessedStore, general: dict) -> None:
    abs_path = os.path.abspath(filepath)

    # 每天轮转
    store.rollover_if_needed()

    # 按路径去重
    if store.contains(abs_path):
        logging.debug(f"Already processed: {abs_path}")
        return

    # 忽略 Office 临时文件
    if general.get("ignore_office_temp", True) and os.path.basename(abs_path).startswith("~$"):
        return

    # 文件稳定检测
    if not wait_for_stable_file(
        abs_path,
        int(general.get("stable_checks", 6)),
        float(general.get("stable_wait", 0.5))
    ):
        logging.warning(f"File not stable: {abs_path}, skipping.")
        return

    filename = os.path.basename(abs_path)
    logging.info(f"Detected new file: {filename}")

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

            break  # 第一命中即止

    if matched:
        store.mark(abs_path)
        logging.info(f"Marked processed: {abs_path}")
    else:
        logging.debug(f"No matching rule for {filename}")


class FileHandler(FileSystemEventHandler):
    def __init__(self, compiled_rules, store: ProcessedStore, general: dict):
        self.compiled_rules = compiled_rules
        self.store = store
        self.general = general

    def on_created(self, event):
        if event.is_directory:
            return
        handle_new_file(event.src_path, self.compiled_rules, self.store, self.general)


def main():
    config = load_config("config.yaml")
    general = config.get("general", {})

    today = date.today()
    compiled_rules = compile_rules(config, today)

    store = ProcessedStore(general.get("processed_base", ".processed_files"))

    watch_dir = general.get("watch_dir", "./incoming")
    os.makedirs(watch_dir, exist_ok=True)

    observer = Observer()
    handler = FileHandler(compiled_rules, store, general)
    observer.schedule(
        handler,
        watch_dir,
        recursive=bool(general.get("recursive", True))
    )
    observer.start()

    logging.info(f"Watching {watch_dir} recursively for new files...")

    try:
        current_day = date.today()
        while True:
            time.sleep(1)

            # 跨天后自动刷新规则和已处理清单
            if date.today() != current_day:
                current_day = date.today()
                store.rollover_if_needed()
                handler.compiled_rules = compile_rules(config, current_day)
                logging.info("Rolled to new day: rules & store refreshed.")
    except KeyboardInterrupt:
        logging.info("Shutting down watcher...")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()

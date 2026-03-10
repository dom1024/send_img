import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional


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
    rule_params: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """
    先计算 general.params，再用 rule.params 覆盖。
    支持:
    - type: date/string/number
    - date: spec + format
    - string/number: value
    """
    result: Dict[str, str] = {}

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

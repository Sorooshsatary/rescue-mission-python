"""ذخیره‌سازی سراسری روی سرور (فایل‌های JSON در پوشهٔ data).

برخلاف نسخهٔ JS که همه‌چیز در localStorage هر مرورگر بود، اینجا
تنظیمات، استراتژی‌ها، تنظیم‌های ذخیره‌شدهٔ ادمین و سناریوها برای
همهٔ کاربران روی سرور نگه داشته می‌شوند.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import PARAM_DEFAULTS, sanitize_params
from .scenarios import SHOCK_SCENARIOS, sanitize_scenario

BASE_DIR = Path(os.environ.get("RESCUE_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
BASE_DIR.mkdir(parents=True, exist_ok=True)


def _path(name: str) -> Path:
    return BASE_DIR / name


def _read_json(name: str, default):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(name: str, value) -> None:
    tmp = _path(name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(name))


# -- تنظیمات سراسری ----------------------------------------------------------

def load_settings() -> dict:
    """تنظیمات سراسری ذخیره‌شده؛ اگر نباشد، پیش‌فرض‌ها."""
    return sanitize_params(_read_json("settings.json", None))


def save_settings(params: dict) -> dict:
    """تنظیمات را تمیز و ذخیره می‌کند و همان را برمی‌گرداند."""
    clean = sanitize_params(params)
    _write_json("settings.json", clean)
    return clean


# -- استراتژی‌های ذخیره‌شده ---------------------------------------------------

def load_strategies() -> list[dict]:
    raw = _read_json("strategies.json", [])
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, dict) and isinstance(s.get("name"), str) and isinstance(s.get("rules"), list)]


def save_strategies(items: list[dict]) -> list[dict]:
    _write_json("strategies.json", items)
    return items


# -- تنظیم‌های ذخیره‌شدهٔ ادمین ------------------------------------------------

def load_admin_presets() -> list[dict]:
    raw = _read_json("admin_presets.json", [])
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        params = item.get("params")
        if isinstance(name, str) and name.strip() and isinstance(params, dict):
            out.append({"name": name.strip()[:60], "params": sanitize_params(params)})
    return out


def save_admin_presets(items: list[dict]) -> list[dict]:
    _write_json("admin_presets.json", items)
    return items


# -- سناریوها ------------------------------------------------------------------

def load_scenario_config() -> dict:
    """پیکربندی سناریوها: {edited: {index: scenario}, customs: [scenario]}."""
    raw = _read_json("scenarios.json", None)
    cfg = {"edited": {}, "customs": []}
    if not isinstance(raw, dict):
        return cfg
    if isinstance(raw.get("edited"), dict):
        for index, item in raw["edited"].items():
            clean = sanitize_scenario(item)
            if clean:
                cfg["edited"][str(index)] = clean
    if isinstance(raw.get("customs"), list):
        cfg["customs"] = [s for s in (sanitize_scenario(x) for x in raw["customs"]) if s]
    return cfg


def save_scenario_config(cfg: dict) -> dict:
    _write_json("scenarios.json", cfg)
    return cfg


def all_scenarios(cfg: dict | None = None) -> list[dict]:
    """همهٔ سناریوها: ۶ سناریوی اصلی (با ویرایش‌های ذخیره‌شده) + سفارشی‌ها."""
    cfg = cfg or load_scenario_config()
    mains = [cfg["edited"].get(str(i), SHOCK_SCENARIOS[i]) for i in range(len(SHOCK_SCENARIOS))]
    return mains + list(cfg.get("customs", []))


# -- مدل یادگیرنده -------------------------------------------------------------

def load_qmodel() -> dict | None:
    return _read_json("qmodel.json", None)


def save_qmodel(agent_dict: dict) -> None:
    _write_json("qmodel.json", agent_dict)


# -- پرچم‌ها -------------------------------------------------------------------

def load_flags() -> dict:
    return _read_json("flags.json", {"showPresets": False})


def save_flags(flags: dict) -> dict:
    clean = {"showPresets": bool(flags.get("showPresets", False))}
    _write_json("flags.json", clean)
    return clean

"""سناریوهای تغییر ناگهانی محیط؛ دقیقاً همان ۶ سناریوی نسخهٔ JS."""
from __future__ import annotations

from .config import PARAM_DEFAULTS, clamp_param

#: برچسب فارسی هر کلید پارامتر که در سناریوها عوض می‌شود.
SHOCK_LABELS = {
    "capacity": "ظرفیت حمل",
    "maxTime": "زمان مأموریت",
    "dangerCost": "هزینهٔ خطر",
    "dangerCells": "خانه‌های خطرناک",
    "obstacles": "موانع",
    "chargeRate": "سرعت شارژ",
    "startBattery": "باتری شروع",
}

SHOCK_KEYS = list(SHOCK_LABELS)

SHOCK_SCENARIOS: list[dict] = [
    {"title": "ظرفیت حمل نصف شد!", "changes": {"capacity": 1}},
    {"title": "وقت مأموریت تنگ شد!", "changes": {"maxTime": 110}},
    {"title": "زمین خطرناک مرگبارتر شد!", "changes": {"dangerCost": 6, "dangerCells": 14}},
    {"title": "مسیرها پر از مانع و خطر شد!", "changes": {"obstacles": 22, "dangerCells": 14}},
    {"title": "شارژرها کند شدند و باتری شروع کمتر شد!", "changes": {"chargeRate": 4, "startBattery": 70}},
    {"title": "باتری کم و وقت کم!", "changes": {"startBattery": 60, "maxTime": 120}},
]


def sanitize_scenario(raw: object) -> dict | None:
    """یک سناریوی خام را تمیز می‌کند؛ نامعتبر باشد None برمی‌گرداند."""
    if not isinstance(raw, dict) or not isinstance(raw.get("changes"), dict):
        return None
    changes: dict[str, int] = {}
    for key in SHOCK_KEYS:
        if raw["changes"].get(key) is not None:
            changes[key] = int(clamp_param(key, raw["changes"][key]))
    if not changes:
        return None
    title = raw.get("title")
    title = title.strip()[:60] if isinstance(title, str) and title.strip() else "سناریوی بدون نام"
    return {"title": title, "changes": changes}


def expand_changes(scenario: dict) -> dict[str, int]:
    """تغییرات جزئی سناریو را با پیش‌فرض محیط کامل می‌کند."""
    out = {key: int(PARAM_DEFAULTS[key]) for key in SHOCK_KEYS}
    out.update(scenario.get("changes", {}))
    return out


def apply_scenario_changes(params: dict, scenario: dict) -> tuple[dict, list[dict]]:
    """تغییرات یک سناریو را روی پارامترها اعمال می‌کند.

    برمی‌گرداند: (پارامترهای تازه، فهرست تفاوت‌ها با قبل).
    """
    from .config import sanitize_params

    before = dict(params)
    next_params = sanitize_params({**params, **scenario.get("changes", {})})
    diffs = [
        {"key": key, "from": before[key], "to": next_params[key]}
        for key in scenario.get("changes", {})
        if before.get(key) != next_params.get(key)
    ]
    if not diffs:
        diffs = [
            {"key": key, "from": before.get(key), "to": next_params.get(key)}
            for key in scenario.get("changes", {})
        ]
    return next_params, diffs

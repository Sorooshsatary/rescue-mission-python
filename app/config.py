"""تنظیمات سراسری بازی مأموریت نجات.

این ماژول تنها مرجع مقدارهای پیش‌فرض، فیلدهای پارامتر، شرط‌ها،
اقدام‌ها، استراتژی‌های آماده و سناریوهای تغییر محیط است؛ دقیقاً
برگرفته از نسخهٔ جاوااسکریپت بازی (فایل rescue-mission__6.html).
"""
from __future__ import annotations

import os
from typing import Any

# ---------------------------------------------------------------------------
# پارامترها
# ---------------------------------------------------------------------------

PARAM_DEFAULTS: dict[str, float | int] = {
    "capacity": 2,
    "maxTime": 160,
    "startBattery": 100,
    "obstacles": 13,
    "dangerCells": 8,
    "dangerCost": 3,
    "chargeRate": 10,
    "smartChargeThreshold": 80,
    "returnMargin": 4,
    "survivorsCritical": 2,
    "survivorsUrgent": 2,
    "survivorsNormal": 2,
    "pointsCritical": 30,
    "pointsUrgent": 20,
    "pointsNormal": 10,
    "trainEpisodes": 400,
    "finetuneEpisodes": 200,
    "evalMaps": 30,
    "alpha": 0.15,
    "gamma": 0.95,
    "epsilon": 0.35,
}

#: فیلدهای پارامتر؛ ورودی ``sec`` فقط عنوان بخش در پنل ادمین است.
PARAM_FIELDS: list[dict[str, Any]] = [
    {"sec": "محیط بازی"},
    {"key": "capacity", "label": "ظرفیت حمل ربات (نفر)", "min": 1, "max": 4, "step": 1},
    {"key": "maxTime", "label": "سقف قدم‌های مأموریت", "min": 40, "max": 400, "step": 10},
    {"key": "startBattery", "label": "باتری شروع (٪)", "min": 20, "max": 100, "step": 5},
    {"key": "obstacles", "label": "تعداد موانع", "min": 0, "max": 40, "step": 1},
    {"key": "dangerCells", "label": "تعداد خانه‌های خطرناک", "min": 0, "max": 30, "step": 1},
    {"key": "dangerCost", "label": "هزینهٔ باتری هر قدم روی زمین خطرناک", "min": 1, "max": 10, "step": 1,
     "hint": "قدم عادی همیشه ۱ واحد باتری مصرف می‌کند."},
    {"key": "chargeRate", "label": "شارژ در هر قدم روی شارژر (٪)", "min": 1, "max": 50, "step": 1},
    {"key": "smartChargeThreshold", "label": "آستانهٔ شارژ هوشمند (٪)", "min": 10, "max": 100, "step": 5,
     "hint": "اقدام «شارژ هوشمند» زیر این باتری به شارژر می‌رود."},
    {"key": "returnMargin", "label": "حاشیهٔ اطمینان باتری برای بازگشت به پایگاه", "min": 0, "max": 20, "step": 1},
    {"sec": "مصدومان و امتیازها"},
    {"key": "survivorsCritical", "label": "تعداد مصدوم بحرانی", "min": 0, "max": 6, "step": 1},
    {"key": "survivorsUrgent", "label": "تعداد مصدوم فوری", "min": 0, "max": 6, "step": 1},
    {"key": "survivorsNormal", "label": "تعداد مصدوم عادی", "min": 0, "max": 6, "step": 1},
    {"key": "pointsCritical", "label": "امتیاز مصدوم بحرانی", "min": 0, "max": 100, "step": 5},
    {"key": "pointsUrgent", "label": "امتیاز مصدوم فوری", "min": 0, "max": 100, "step": 5},
    {"key": "pointsNormal", "label": "امتیاز مصدوم عادی", "min": 0, "max": 100, "step": 5},
    {"sec": "یادگیری تقویتی"},
    {"key": "trainEpisodes", "label": "مأموریت تمرینی آموزش عامل", "min": 50, "max": 2000, "step": 50},
    {"key": "finetuneEpisodes", "label": "مأموریت تمرینی یادگیری دوباره", "min": 50, "max": 1000, "step": 50},
    {"key": "evalMaps", "label": "تعداد نقشه‌های مقایسه", "min": 5, "max": 100, "step": 5},
    {"key": "alpha", "label": "نرخ یادگیری (α)", "min": 0.01, "max": 1, "step": 0.01},
    {"key": "gamma", "label": "ضریب تنزیل (γ)", "min": 0, "max": 0.99, "step": 0.01},
    {"key": "epsilon", "label": "نرخ کاوش شروع (ε)", "min": 0, "max": 1, "step": 0.01},
]

_PARAM_FIELD_BY_KEY = {f["key"]: f for f in PARAM_FIELDS if "key" in f}


def clamp_param(key: str, value: Any) -> float | int:
    """مقدار یک پارامتر را به بازه و گام مجازش محدود می‌کند."""
    field = _PARAM_FIELD_BY_KEY[key]
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = float(PARAM_DEFAULTS[key])
    if v != v:  # NaN
        v = float(PARAM_DEFAULTS[key])
    v = min(field["max"], max(field["min"], v))
    step = field["step"]
    decimals = len(str(step).split(".")[1]) if "." in str(step) else 0
    v = round(v, decimals)
    return int(v) if decimals == 0 else v


def sanitize_params(raw: dict[str, Any] | None) -> dict[str, float | int]:
    """دیکشنری خام پارامترها را تمیز می‌کند؛ دقیقاً معادل sanitizeParams در JS."""
    out: dict[str, float | int] = dict(PARAM_DEFAULTS)
    if isinstance(raw, dict):
        for field in PARAM_FIELDS:
            key = field.get("key")
            if key and raw.get(key) is not None:
                out[key] = clamp_param(key, raw[key])
    total_survivors = int(out["survivorsCritical"]) + int(out["survivorsUrgent"]) + int(out["survivorsNormal"])
    if total_survivors < 1:
        out["survivorsNormal"] = 1
    return out


def points_of(params: dict[str, float | int]) -> dict[str, int]:
    """امتیاز هر سطح مصدوم را از روی پارامترها برمی‌گرداند."""
    return {
        "normal": int(params["pointsNormal"]),
        "urgent": int(params["pointsUrgent"]),
        "critical": int(params["pointsCritical"]),
    }


# ---------------------------------------------------------------------------
# شرط‌ها و اقدام‌ها
# ---------------------------------------------------------------------------

CONDITIONS: list[dict[str, Any]] = [
    {"id": "full", "label": "ظرفیت حمل ربات پر است"},
    {"id": "carryingAny", "label": "ربات حداقل یک مصدوم حمل می‌کند"},
    {"id": "batteryBelow", "label": "باتری کمتر از حد انتخابی است",
     "param": {"kind": "battery", "def": 30, "min": 1, "max": 100, "step": 1, "inputLabel": "درصد باتری:", "unit": "٪"}},
    {"id": "batteryAbove", "label": "باتری بیشتر از حد انتخابی است",
     "param": {"kind": "battery", "def": 30, "min": 1, "max": 100, "step": 1, "inputLabel": "درصد باتری:", "unit": "٪"}},
    {"id": "criticalNear", "label": "مصدوم بحرانی در نزدیکی است",
     "param": {"kind": "distance", "def": 3, "min": 0, "max": 11, "step": 1, "inputLabel": "حداکثر فاصله:", "unit": "خانه"}},
    {"id": "criticalExists", "label": "هنوز مصدوم بحرانی نجات‌نیافته‌ای در نقشه هست (هر فاصله‌ای)"},
    {"id": "urgentNear", "label": "مصدوم فوری در نزدیکی است",
     "param": {"kind": "distance", "def": 3, "min": 0, "max": 11, "step": 1, "inputLabel": "حداکثر فاصله:", "unit": "خانه"}},
    {"id": "survivorNear", "label": "نزدیک‌ترین مصدوم در نزدیکی است",
     "param": {"kind": "distance", "def": 3, "min": 0, "max": 11, "step": 1, "inputLabel": "حداکثر فاصله:", "unit": "خانه"}},
    {"id": "noSurvivorVisible", "label": "هیچ مصدومی در محدودهٔ دید نیست",
     "param": {"kind": "distanceFar", "def": 5, "min": 0, "max": 11, "step": 1, "inputLabel": "محدودهٔ دید (فاصله):", "unit": "خانه"}},
    {"id": "baseNear", "label": "پایگاه نزدیک است",
     "param": {"kind": "distance", "def": 3, "min": 0, "max": 11, "step": 1, "inputLabel": "حداکثر فاصله:", "unit": "خانه"}},
    {"id": "baseFar", "label": "پایگاه دور است",
     "param": {"kind": "distanceFar", "def": 5, "min": 0, "max": 11, "step": 1, "inputLabel": "بیشتر از فاصله:", "unit": "خانه"}},
    {"id": "chargerNear", "label": "ایستگاه شارژ نزدیک است",
     "param": {"kind": "distance", "def": 3, "min": 0, "max": 11, "step": 1, "inputLabel": "حداکثر فاصله:", "unit": "خانه"}},
    {"id": "timeLow", "label": "زمان کمی تا پایان مأموریت مانده",
     "param": {"kind": "time", "def": 30, "min": 0, "max": 400, "step": 1, "inputLabel": "قدم باقی‌مانده:", "unit": "قدم یا کمتر"}},
    {"id": "lowForReturn", "label": "باتری برای بازگشت به پایگاه کافی نیست",
     "param": {"kind": "margin", "def": 4, "min": 0, "max": 30, "step": 1, "inputLabel": "حاشیهٔ باتری:", "unit": "واحد باتری"}},
]

ACTIONS: list[dict[str, str]] = [
    {"id": "rescueNearest", "label": "نجات نزدیک‌ترین مصدوم"},
    {"id": "rescueUrgent", "label": "نجات بحرانی‌ترین مصدوم"},
    {"id": "rescueSafe", "label": "نجات نزدیک‌ترین مصدوم از مسیر امن (دوری از زمین خطرناک)"},
    {"id": "toBase", "label": "بازگشت به پایگاه"},
    {"id": "deliverPartial", "label": "تحویل مصدومان حمل‌شده (اگر ندارد: جست‌وجو)"},
    {"id": "toCharger", "label": "رفتن به نزدیک‌ترین شارژر"},
    {"id": "chargeSmart", "label": "شارژ هوشمند (باتری زیر ۸۰٪: شارژ؛ وگرنه: نجات)"},
    {"id": "search", "label": "جست‌وجوی مصدومان"},
]

CONDITION_IDS = {c["id"] for c in CONDITIONS}
ACTION_IDS = {a["id"] for a in ACTIONS}
CONDITION_BY_ID = {c["id"]: c for c in CONDITIONS}
ACTION_LABEL = {a["id"]: a["label"] for a in ACTIONS}

LEVEL_NAME = {"normal": "عادی", "urgent": "فوری", "critical": "بحرانی"}

# ---------------------------------------------------------------------------
# استراتژی‌های آماده (پیش‌فرض‌های ۱ تا ۶ + استراتژی قهرمان)
# ---------------------------------------------------------------------------

PRESETS: list[dict[str, Any]] = [
    {"id": "1", "name": "استراتژی ۱ — نجات‌محور",
     "desc": "اول نجات بحرانی، بعد شارژ، بعد بازگشت",
     "rules": [
         {"id": "criticalNear", "threshold": 3, "action": "rescueUrgent"},
         {"id": "batteryBelow", "threshold": 30, "action": "toCharger"},
         {"id": "full", "action": "toBase"},
     ]},
    {"id": "2", "name": "استراتژی ۲ — ایمنی‌محور",
     "desc": "اول شارژ، بعد بازگشت، بعد نجات بحرانی",
     "rules": [
         {"id": "batteryBelow", "threshold": 30, "action": "toCharger"},
         {"id": "full", "action": "toBase"},
         {"id": "criticalNear", "threshold": 3, "action": "rescueUrgent"},
     ]},
    {"id": "3", "name": "استراتژی ۳ — امتیاز و سرعت",
     "desc": "شکار مداوم مصدوم؛ شارژ فقط وقتی باتری واقعاً کم است",
     "rules": [
         {"id": "full", "action": "toBase"},
         {"id": "criticalExists", "action": "rescueUrgent"},
         {"id": "survivorNear", "threshold": 3, "action": "rescueNearest"},
         {"id": "batteryBelow", "threshold": 20, "action": "toCharger"},
     ]},
    {"id": "4", "name": "استراتژی ۴ — محافظه‌کار باتری",
     "desc": "شارژ زودهنگام و محتاطانه؛ هیچ‌وقت با باتری کم ریسک نمی‌کند",
     "rules": [
         {"id": "batteryBelow", "threshold": 50, "action": "toCharger"},
         {"id": "lowForReturn", "threshold": 4, "action": "toCharger"},
         {"id": "full", "action": "toBase"},
         {"id": "criticalNear", "threshold": 3, "action": "rescueUrgent"},
         {"id": "survivorNear", "threshold": 3, "action": "rescueNearest"},
     ]},
    {"id": "5", "name": "استراتژی ۵ — متعادل هوشمند",
     "desc": "تحویل سریع وقتی پایگاه نزدیک است، شارژ هوشمند، وگرنه نجات",
     "rules": [
         {"id": "full", "action": "toBase"},
         {"id": "carryingAny", "action": "deliverPartial"},
         {"id": "batteryAbove", "threshold": 80, "action": "rescueNearest"},
         {"id": "criticalNear", "threshold": 3, "action": "rescueUrgent"},
         {"id": "batteryBelow", "threshold": 30, "action": "chargeSmart"},
     ]},
    {"id": "6", "name": "استراتژی ۶ — مسیر امن",
     "desc": "دوری از زمین خطرناک با مسیر امن، حتی اگر راه طولانی‌تر شود",
     "rules": [
         {"id": "full", "action": "toBase"},
         {"id": "batteryBelow", "threshold": 30, "action": "toCharger"},
         {"id": "criticalExists", "action": "rescueSafe"},
         {"id": "survivorNear", "threshold": 3, "action": "rescueSafe"},
     ]},
    {"id": "7", "name": "استراتژی قهرمان — رقیب عامل یادگیرنده",
     "desc": "۵ قانون بدون آستانهٔ باتری: پر→پایگاه، بحرانی نزدیک→بحرانی‌ترین، بحرانی در نقشه→مسیر امن، فوری نزدیک→بحرانی‌ترین، نزدیک‌ترین≤۳→نزدیک‌ترین",
     "rules": [
         {"id": "full", "action": "toBase"},
         {"id": "criticalNear", "threshold": 3, "action": "rescueUrgent"},
         {"id": "criticalExists", "action": "rescueSafe"},
         {"id": "urgentNear", "threshold": 3, "action": "rescueUrgent"},
         {"id": "survivorNear", "threshold": 3, "action": "rescueNearest"},
     ]},
]

# ---------------------------------------------------------------------------
# رمزها (از متغیر محیطی، با پیش‌فرض نسخهٔ JS)
# ---------------------------------------------------------------------------

ADMIN_CODE = os.environ.get("ADMIN_CODE", "123")
STAGE_CODE = os.environ.get("STAGE_CODE", "1384")


def normalize_code(value: Any) -> str:
    """ارقام فارسی/عربی را به لاتین تبدیل و فاصله‌ها را حذف می‌کند."""
    text = "" if value is None else str(value)
    fa = "۰۱۲۳۴۵۶۷۸۹"
    ar = "٠١٢٣٤٥٦٧٨٩"
    out = []
    for ch in text:
        if ch in fa:
            out.append(str(fa.index(ch)))
        elif ch in ar:
            out.append(str(ar.index(ch)))
        else:
            out.append(ch)
    return "".join(out).strip()

"""اعتبارسنجی استراتژی‌های دانش‌آموز؛ معادل validate در نسخهٔ JS."""
from __future__ import annotations

from .config import ACTION_IDS, CONDITION_BY_ID
from .engine import rule_number

_RESCUE_ACTIONS = {"rescueNearest", "rescueUrgent", "rescueSafe", "search"}


def validate_strategy(rules: list[dict] | None) -> list[str]:
    """فهرست هشدارهای منطقی یک استراتژی را برمی‌گرداند (خالی = سالم)."""
    warns: list[str] = []
    rules = rules or []
    if not rules:
        warns.append("هیچ قانونی تعریف نشده است؛ ربات در همهٔ قدم‌ها از رفتار پیش‌فرض استفاده می‌کند.")
    seen: set[str] = set()
    for i, rule in enumerate(rules):
        num = rule_number(rule)
        key = f"{rule.get('id')}:{num if num is not None else ''}"
        if key in seen:
            warns.append(
                f"قانون {i + 1} شرط تکراری دارد؛ قانون بالاتر همیشه زودتر اجرا می‌شود "
                "و این قانون شاید هیچ‌وقت نوبتش نرسد."
            )
        seen.add(key)
        if rule.get("id") == "full" and rule.get("action") in _RESCUE_ACTIONS:
            warns.append(
                f"قانون {i + 1} ناسازگار است: وقتی ظرفیت پر است، ربات نمی‌تواند مصدوم دیگری "
                "بردارد؛ اقدام‌هایی مثل «بازگشت به پایگاه» منطقی‌ترند."
            )
        if (
            rule.get("id") == "batteryBelow"
            and rule.get("action") not in ("toCharger", "chargeSmart")
            and (num if num is not None else 30) <= 30
        ):
            warns.append(
                f"قانون {i + 1}: باتری خیلی کم است ولی اقدام، رفتن به شارژر نیست؛ "
                "ربات ممکن است وسط راه خاموش شود."
            )
    if not any(r.get("action") == "toBase" for r in rules):
        warns.append(
            "هیچ قانونی ربات را به پایگاه برنمی‌گرداند (مگر قانون «ظرفیت پر» را داشته باشی)؛ "
            "مصدومان فقط وقتی امتیاز می‌گیرند که به پایگاه تحویل شوند."
        )
    return warns


def sanitize_rules(raw: object) -> list[dict]:
    """قانون‌های خام ورودی را تمیز می‌کند؛ قانون نامعتبر حذف می‌شود."""
    if not isinstance(raw, list):
        raise ValueError("rules باید فهرستی از قانون‌ها باشد")
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("id")
        action = item.get("action")
        if rule_id not in CONDITION_BY_ID or action not in ACTION_IDS:
            continue
        rule: dict = {"id": rule_id, "action": action}
        if "param" in CONDITION_BY_ID[rule_id]:
            rule["threshold"] = rule_number(item)
        out.append(rule)
    return out

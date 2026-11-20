"""سرور FastAPI مأموریت نجات.

همهٔ منطق بازی در پایتون است؛ فرانت‌اند فقط با این API حرف می‌زند.
تنظیمات سراسری روی سرور ذخیره می‌شوند و برای همه اعمال می‌شوند.
"""
from __future__ import annotations

import random

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import store
from .config import (
    ACTIONS,
    ADMIN_CODE,
    CONDITIONS,
    PARAM_DEFAULTS,
    PARAM_FIELDS,
    PRESETS,
    STAGE_CODE,
    normalize_code,
    sanitize_params,
)
from .engine import human_decision, normalize_rules, run_human_episode
from .qlearning import QAgent, Q_ACTIONS, eval_agent, eval_validation, model_strategy, train
from .rules import sanitize_rules, validate_strategy
from .scenarios import SHOCK_LABELS, SHOCK_SCENARIOS, apply_scenario_changes, expand_changes, sanitize_scenario

STATIC_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="مأموریت نجات", description="سرور بازی آموزشی مأموریت نجات")

_agent = QAgent.from_dict(store.load_qmodel())


def _save_agent() -> None:
    store.save_qmodel(_agent.to_dict())


def _require_admin(x_admin_code: str | None) -> None:
    if normalize_code(x_admin_code) != ADMIN_CODE:
        raise HTTPException(status_code=403, detail="رمز ادمین درست نیست")


# ---------------------------------------------------------------------------
# مدل‌های ورودی
# ---------------------------------------------------------------------------

class RuleIn(BaseModel):
    """یک قانون «اگر … آنگاه …»."""

    id: str
    action: str
    threshold: float | None = None


class SimulateIn(BaseModel):
    """ورودی شبیه‌سازی یک استراتژی روی یک نقشه."""

    rules: list[RuleIn] = Field(default_factory=list)
    seed: int = 7
    capacity: int | None = None


class CompareIn(BaseModel):
    """ورودی مقایسهٔ استراتژی انسانی با عامل یادگیرنده."""

    rules: list[RuleIn] = Field(default_factory=list)
    capacity: int | None = None


class TrainIn(BaseModel):
    """ورودی آموزش عامل یادگیرنده."""

    episodes: int | None = None
    capacity: int | None = None
    reset: bool = False


class UnlockIn(BaseModel):
    """ورودی باز کردن قفل مرحله یا ادمین."""

    code: str
    kind: str = "stage"  # "stage" | "admin"


class StrategyIn(BaseModel):
    """ذخیرهٔ یک استراتژی روی سرور."""

    name: str = Field(min_length=1, max_length=60)
    rules: list[RuleIn] = Field(default_factory=list)


class AdminPresetIn(BaseModel):
    """ذخیرهٔ یک ترکیب پارامتر با نام."""

    name: str = Field(min_length=1, max_length=60)
    params: dict = Field(default_factory=dict)


class ScenarioIn(BaseModel):
    """یک سناریوی تغییر محیط."""

    title: str = Field(min_length=1, max_length=60)
    changes: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# صفحهٔ اصلی و فایل‌های ایستا
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# فراداده و تنظیمات
# ---------------------------------------------------------------------------

@app.get("/api/meta")
def meta():
    """شرط‌ها، اقدام‌ها، پیش‌فرض‌ها، سناریوها و پیش‌فرض پارامترها."""
    settings = store.load_settings()
    cfg = store.load_scenario_config()
    return {
        "conditions": CONDITIONS,
        "actions": ACTIONS,
        "presets": PRESETS,
        "paramFields": PARAM_FIELDS,
        "paramDefaults": PARAM_DEFAULTS,
        "settings": settings,
        "shockLabels": SHOCK_LABELS,
        "shockScenarios": SHOCK_SCENARIOS,
        "customScenarios": cfg["customs"],
        "editedScenarios": cfg["edited"],
        "showPresets": store.load_flags().get("showPresets", False),
        "totalSurvivors": int(settings["survivorsCritical"]) + int(settings["survivorsUrgent"]) + int(settings["survivorsNormal"]),
    }


@app.get("/api/settings")
def get_settings():
    """تنظیمات سراسری فعلی."""
    return store.load_settings()


@app.put("/api/settings")
def put_settings(params: dict, x_admin_code: str | None = Header(default=None)):
    """تغییر تنظیمات سراسری؛ فقط با رمز ادمین. برای همه اعمال می‌شود."""
    _require_admin(x_admin_code)
    return {"settings": store.save_settings(params), "message": "پارامترها اعمال و ذخیره شدند؛ برای همه اعمال شد."}


@app.post("/api/settings/reset")
def reset_settings(x_admin_code: str | None = Header(default=None)):
    """بازنشانی تنظیمات به پیش‌فرض؛ فقط با رمز ادمین."""
    _require_admin(x_admin_code)
    return {"settings": store.save_settings(dict(PARAM_DEFAULTS))}


# ---------------------------------------------------------------------------
# باز کردن قفل
# ---------------------------------------------------------------------------

@app.post("/api/unlock")
def unlock(body: UnlockIn):
    """باز کردن قفل مرحله (رمز مرحله) یا ادمین (رمز ادمین)."""
    code = normalize_code(body.code)
    if body.kind == "admin":
        if code == ADMIN_CODE:
            return {"ok": True, "kind": "admin"}
        raise HTTPException(status_code=403, detail="رمز درست نیست — از آموزگار بپرس.")
    if code == STAGE_CODE:
        return {"ok": True, "kind": "stage"}
    raise HTTPException(status_code=403, detail="رمز درست نیست — از آموزگار بپرس.")


# ---------------------------------------------------------------------------
# شبیه‌سازی و مقایسه
# ---------------------------------------------------------------------------

@app.post("/api/simulate")
def simulate(body: SimulateIn):
    """اجرای یک استراتژی روی یک نقشه؛ برمی‌گرداند خلاصه + همهٔ قدم‌ها و لاگ تصمیم."""
    rules = normalize_rules(sanitize_rules([r.model_dump() for r in body.rules]))
    params = store.load_settings()
    capacity = body.capacity if body.capacity is not None else int(params["capacity"])
    result = run_human_episode(rules, body.seed, params, capacity)
    result["warnings"] = validate_strategy(rules)
    result["rules"] = rules
    return result


@app.post("/api/train")
def train_agent(body: TrainIn):
    """آموزش عامل یادگیرنده؛ برمی‌گرداند منحنی + امتیاز اعتبارسنجی."""
    params = store.load_settings()
    capacity = body.capacity if body.capacity is not None else int(params["capacity"])
    episodes = body.episodes if body.episodes is not None else int(params["trainEpisodes"])
    episodes = max(1, min(5000, episodes))
    if body.reset:
        _agent.reset()
    summary = train(_agent, episodes, params, capacity, rng=random.Random())
    _save_agent()
    summary["modelStrategy"] = model_strategy(_agent)
    return summary


@app.post("/api/train/reset")
def reset_training():
    """شروع دوبارهٔ آموزش از صفر."""
    _agent.reset()
    _save_agent()
    return {"ok": True, "message": "جدول یادگیری از صفر شروع شد."}


@app.get("/api/train/status")
def train_status():
    """وضعیت آموزش فعلی و استراتژی مدل."""
    return {
        "trained": _agent.trained,
        "episodes": _agent.episodes,
        "states": len(_agent.q),
        "curve": _agent.curve,
        "bestValidationScore": None if _agent.best_val_score == float("-inf") else _agent.best_val_score,
        "bestValidationAt": _agent.best_val_at,
        "modelStrategy": model_strategy(_agent) if _agent.trained else [],
    }


@app.post("/api/compare")
def compare(body: CompareIn):
    """مقایسهٔ استراتژی انسانی با عامل یادگیرنده روی نقشه‌های یکسان.

    اگر عامل هنوز آموزش ندیده باشد، اول با تعداد مأموریت تمرینی
    تنظیمات آموزش می‌بیند (مثل JS که مقایسه بدون آموزش ممکن نبود).
    """
    params = store.load_settings()
    capacity = body.capacity if body.capacity is not None else int(params["capacity"])
    rules = normalize_rules(sanitize_rules([r.model_dump() for r in body.rules]))
    if not _agent.trained:
        train(_agent, int(params["trainEpisodes"]), params, capacity, rng=random.Random())
        _save_agent()
    human = eval_agent(lambda st: human_decision(rules, st, params).action_id, params, capacity)
    rl = eval_agent(lambda st: Q_ACTIONS[_agent.choose(st, params, 0.0)], params, capacity)
    # ردّ یک مأموریت نمونه (بذر ۵۰۰۰) از هر دو عامل، برای نمایش همزمان دو تخته
    from .engine import run_trace

    human_trace = run_trace(lambda st: human_decision(rules, st, params).action_id, 5000, params, capacity)
    rl_trace = run_trace(lambda st: Q_ACTIONS[_agent.choose(st, params, 0.0)], 5000, params, capacity)
    return {
        "capacity": capacity,
        "evalMaps": int(params["evalMaps"]),
        "human": human,
        "rl": rl,
        "trainedEpisodes": _agent.episodes,
        "modelStrategy": model_strategy(_agent),
        "humanTrace": human_trace,
        "rlTrace": rl_trace,
    }


@app.post("/api/finetune")
def finetune(body: CompareIn):
    """یادگیری دوبارهٔ عامل در محیط جدید، بعد مقایسه."""
    params = store.load_settings()
    capacity = body.capacity if body.capacity is not None else int(params["capacity"])
    train(_agent, int(params["finetuneEpisodes"]), params, capacity, rng=random.Random())
    _save_agent()
    return compare(body)


# ---------------------------------------------------------------------------
# استراتژی‌های ذخیره‌شده (روی سرور)
# ---------------------------------------------------------------------------

@app.get("/api/strategies")
def list_strategies():
    return {"strategies": store.load_strategies()}


@app.post("/api/strategies")
def save_strategy(body: StrategyIn):
    rules = normalize_rules(sanitize_rules([r.model_dump() for r in body.rules]))
    items = store.load_strategies()
    name = body.name.strip()
    existing = next((i for i, s in enumerate(items) if s["name"] == name), None)
    entry = {"name": name, "rules": rules}
    if existing is not None:
        items[existing] = entry
    else:
        items.append(entry)
    store.save_strategies(items)
    return {"strategies": items}


@app.delete("/api/strategies/{name}")
def delete_strategy(name: str):
    items = [s for s in store.load_strategies() if s["name"] != name]
    store.save_strategies(items)
    return {"strategies": items}


# ---------------------------------------------------------------------------
# تنظیم‌های ذخیره‌شدهٔ ادمین
# ---------------------------------------------------------------------------

@app.get("/api/admin-presets")
def list_admin_presets(x_admin_code: str | None = Header(default=None)):
    _require_admin(x_admin_code)
    return {"presets": store.load_admin_presets()}


@app.post("/api/admin-presets")
def save_admin_preset(body: AdminPresetIn, x_admin_code: str | None = Header(default=None)):
    _require_admin(x_admin_code)
    items = store.load_admin_presets()
    name = body.name.strip()
    params = sanitize_params(body.params)
    existing = next((i for i, p in enumerate(items) if p["name"] == name), None)
    entry = {"name": name, "params": params}
    if existing is not None:
        items[existing] = entry
    else:
        items.append(entry)
    store.save_admin_presets(items)
    return {"presets": items}


@app.delete("/api/admin-presets/{name}")
def delete_admin_preset(name: str, x_admin_code: str | None = Header(default=None)):
    _require_admin(x_admin_code)
    items = [p for p in store.load_admin_presets() if p["name"] != name]
    store.save_admin_presets(items)
    return {"presets": items}


@app.post("/api/admin-presets/{name}/apply")
def apply_admin_preset(name: str, x_admin_code: str | None = Header(default=None)):
    _require_admin(x_admin_code)
    preset = next((p for p in store.load_admin_presets() if p["name"] == name), None)
    if preset is None:
        raise HTTPException(status_code=404, detail="تنظیمی با این نام پیدا نشد")
    return {"settings": store.save_settings(preset["params"])}


@app.put("/api/flags")
def set_flags(body: dict, x_admin_code: str | None = Header(default=None)):
    """نمایش/مخفی‌کردن استراتژی‌های آماده؛ فقط با رمز ادمین."""
    _require_admin(x_admin_code)
    return {"flags": store.save_flags(body)}


# ---------------------------------------------------------------------------
# سناریوها و تغییر محیط
# ---------------------------------------------------------------------------

@app.get("/api/scenarios")
def list_scenarios():
    cfg = store.load_scenario_config()
    return {
        "defaults": SHOCK_SCENARIOS,
        "edited": cfg["edited"],
        "customs": cfg["customs"],
        "all": store.all_scenarios(cfg),
        "labels": SHOCK_LABELS,
    }


@app.put("/api/scenarios")
def put_scenarios(body: dict, x_admin_code: str | None = Header(default=None)):
    """ذخیرهٔ ویرایش سناریوهای اصلی و سناریوهای سفارشی؛ فقط با رمز ادمین."""
    _require_admin(x_admin_code)
    cfg = {"edited": {}, "customs": []}
    if isinstance(body.get("edited"), dict):
        for index, item in body["edited"].items():
            clean = sanitize_scenario(item)
            if clean:
                cfg["edited"][str(index)] = clean
    if isinstance(body.get("customs"), list):
        cfg["customs"] = [s for s in (sanitize_scenario(x) for x in body["customs"]) if s]
    store.save_scenario_config(cfg)
    return {"scenarios": cfg, "all": store.all_scenarios(cfg)}


@app.post("/api/scenarios/reset")
def reset_scenarios(x_admin_code: str | None = Header(default=None)):
    _require_admin(x_admin_code)
    cfg = {"edited": {}, "customs": []}
    store.save_scenario_config(cfg)
    return {"scenarios": cfg, "all": SHOCK_SCENARIOS}


@app.post("/api/shock")
def apply_shock(body: dict | None = None):
    """اعمال یک سناریوی تصادفی (یا با اندیس مشخص) روی تنظیمات سراسری."""
    scenarios = store.all_scenarios()
    index = (body or {}).get("index")
    if isinstance(index, int) and 0 <= index < len(scenarios):
        scenario = scenarios[index]
    else:
        candidates = [
            s for s in scenarios
            if any(store.load_settings().get(k) != v for k, v in s["changes"].items())
        ]
        pool = candidates or scenarios
        scenario = random.choice(pool)
    params, diffs = apply_scenario_changes(store.load_settings(), scenario)
    store.save_settings(params)
    return {
        "scenario": scenario,
        "changes": diffs,
        "expanded": expand_changes(scenario),
        "settings": params,
    }


@app.post("/api/restore-env")
def restore_env():
    """بازگشت به محیط عادی (پارامترهای پیش‌فرض)."""
    settings = store.save_settings(dict(PARAM_DEFAULTS))
    return {"settings": settings, "message": "به محیط عادی برگشتیم."}

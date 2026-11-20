"""عامل یادگیرنده — Watkins's Q(λ) با جدول درشت (coarse) به‌عنوان پشتیبان.

برگردان دقیق منطق JS: λ=0.8، حالت ریز ۶ ویژگی (۱٬۶۲۰ حالت) با
priorityBin چهارسطحی، حالت درشت ۳ ویژگی (۶۰ حالت)، ترکیب وزنی
وقتی بازدید حالت ریز کمتر از ۵ است، تساوی تصادفی، برنامهٔ کاوش
در هر دور آموزش، و checkpoint بهترین جدول روی نقشه‌های 9000–9009.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .config import PARAM_DEFAULTS, sanitize_params
from .engine import GameState, gen_map, observe, step_env

Q_ACTIONS = ["rescueNearest", "rescueUrgent", "rescueSafe", "toBase", "toCharger", "search"]
Q_LAMBDA = 0.8
VALIDATION_SEEDS = list(range(9000, 9010))
EVAL_SEEDS_START = 5000

# ---------------------------------------------------------------------------
# کلیدهای حالت
# ---------------------------------------------------------------------------

BATT_TXT = [
    "باتری خیلی کم است (۰ تا ۲۰٪)",
    "باتری کم است (۲۰ تا ۴۰٪)",
    "باتری متوسط است (۴۰ تا ۶۰٪)",
    "باتری خوب است (۶۰ تا ۸۰٪)",
    "باتری پر است (۸۰ تا ۱۰۰٪)",
]
CARRY_TXT = [
    "ربات هیچ مصدومی حمل نمی‌کند",
    "ربات مصدوم حمل می‌کند ولی ظرفیتش پر نیست",
    "ظرفیت حمل ربات پر است",
]
NEAR_TXT = [
    "نزدیک‌ترین مصدوم خیلی نزدیک است (حداکثر ۲ خانه)",
    "نزدیک‌ترین مصدوم در فاصلهٔ متوسط است (۳ تا ۵ خانه)",
    "نزدیک‌ترین مصدوم دور است (۶ خانه یا بیشتر) یا مصدومی نمانده است",
]
CRIT_TXT = [
    "مصدوم بحرانی نزدیک است (حداکثر ۳ خانه)",
    "مصدوم بحرانی در نقشه هست ولی دور است (بیش از ۳ خانه)",
    "مصدوم بحرانی نمانده ولی مصدوم فوری نزدیک است (حداکثر ۳ خانه)",
    "مصدوم بحرانی نمانده و مصدوم فوری نزدیکی هم نیست",
]
TIME_TXT = [
    "زمان کمی تا پایان مأموریت مانده است (حداکثر ۲۵ قدم)",
    "زمان باقی‌مانده متوسط است (۲۶ تا ۷۵ قدم)",
    "زمان زیادی تا پایان مأموریت مانده است (بیش از ۷۵ قدم)",
]
CHARGER_TXT = [
    "شارژر خیلی نزدیک است (حداکثر ۲ خانه)",
    "شارژر در فاصلهٔ متوسط است (۳ تا ۵ خانه)",
    "شارژر دور است (۶ خانه یا بیشتر)",
]

ACTION_LABEL = {
    "rescueNearest": "نجات نزدیک‌ترین مصدوم",
    "rescueUrgent": "نجات بحرانی‌ترین مصدوم",
    "rescueSafe": "نجات نزدیک‌ترین مصدوم از مسیر امن (دوری از زمین خطرناک)",
    "toBase": "بازگشت به پایگاه",
    "deliverPartial": "تحویل مصدومان حمل‌شده (اگر ندارد: جست‌وجو)",
    "toCharger": "رفتن به نزدیک‌ترین شارژر",
    "chargeSmart": "شارژ هوشمند (باتری زیر ۸۰٪: شارژ؛ وگرنه: نجات)",
    "search": "جست‌وجوی مصدومان",
}


def _battery_bin(battery: int) -> int:
    return min(4, max(0, min(100, battery)) // 20)


def _dist_bin(d: float) -> int:
    if d is None or d == float("inf"):
        return 2
    if d <= 2:
        return 0
    if d <= 5:
        return 1
    return 2


def _time_bin(time_left: int) -> int:
    if time_left <= 25:
        return 0
    if time_left <= 75:
        return 1
    return 2


def _priority_bin(obs) -> int:
    if obs.crit:
        return 0 if obs.crit_d <= 3 else 1
    if obs.urg and obs.urg_d <= 3:
        return 2
    return 3


def _carry_bin(obs) -> int:
    if obs.carrying == 0:
        return 0
    return 2 if obs.carrying >= obs.capacity else 1


def q_state_key(obs) -> str:
    """کلید حالت ریز: باتری | حمل | نزدیک‌ترین | اولویت | زمان | شارژر."""
    return "|".join(str(v) for v in (
        _battery_bin(obs.battery),
        _carry_bin(obs),
        _dist_bin(obs.nearest_d),
        _priority_bin(obs),
        _time_bin(obs.time_left),
        _dist_bin(obs.charger_d),
    ))


def q_coarse_key(obs) -> str:
    """کلید حالت درشت: باتری | حمل | اولویت."""
    return "|".join(str(v) for v in (_battery_bin(obs.battery), _carry_bin(obs), _priority_bin(obs)))


def env_signature(params: dict, capacity: int) -> str:
    """امضای محیط؛ هر تغییری در آن، checkpoint بهترین جدول را باطل می‌کند."""
    keys = (
        capacity, params["maxTime"], params["startBattery"], params["obstacles"],
        params["dangerCells"], params["dangerCost"], params["chargeRate"],
        params["survivorsCritical"], params["survivorsUrgent"], params["survivorsNormal"],
        params["pointsCritical"], params["pointsUrgent"], params["pointsNormal"],
    )
    return "|".join(str(k) for k in keys)


def state_phrase(state_key: str) -> str:
    """توصیف خوانای یک حالت ریز، مثل قانون‌های دانش‌آموز."""
    p = [int(v) for v in state_key.split("|")]
    return " و ".join([
        BATT_TXT[p[0]], CARRY_TXT[p[1]], NEAR_TXT[p[2]],
        CRIT_TXT[p[3]], TIME_TXT[p[4]], CHARGER_TXT[p[5]],
    ])


# ---------------------------------------------------------------------------
# عامل
# ---------------------------------------------------------------------------

@dataclass
class QAgent:
    """جدول‌های Q (ریز و درشت) به‌همراه وضعیت آموزش و بهترین checkpoint."""

    q: dict[str, list[float]] = field(default_factory=dict)
    q_coarse: dict[str, list[float]] = field(default_factory=dict)
    visits: dict[str, int] = field(default_factory=dict)
    trained: bool = False
    episodes: int = 0
    curve: list[float] = field(default_factory=list)
    best_q: dict[str, list[float]] | None = None
    best_q_coarse: dict[str, list[float]] | None = None
    best_visits: dict[str, int] | None = None
    best_val_score: float = float("-inf")
    best_val_at: int = 0
    best_val_env_sig: str | None = None

    # -- سریال‌سازی ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "q": self.q, "q_coarse": self.q_coarse, "visits": self.visits,
            "trained": self.trained, "episodes": self.episodes, "curve": self.curve,
            "best_q": self.best_q, "best_q_coarse": self.best_q_coarse,
            "best_visits": self.best_visits, "best_val_score": self.best_val_score,
            "best_val_at": self.best_val_at, "best_val_env_sig": self.best_val_env_sig,
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "QAgent":
        if not isinstance(raw, dict):
            return cls()
        agent = cls()
        agent.q = {k: [float(v) for v in row] for k, row in (raw.get("q") or {}).items()}
        agent.q_coarse = {k: [float(v) for v in row] for k, row in (raw.get("q_coarse") or {}).items()}
        agent.visits = {k: int(v) for k, v in (raw.get("visits") or {}).items()}
        agent.trained = bool(raw.get("trained"))
        agent.episodes = int(raw.get("episodes") or 0)
        agent.curve = [float(v) for v in (raw.get("curve") or [])]
        agent.best_q = raw.get("best_q")
        agent.best_q_coarse = raw.get("best_q_coarse")
        agent.best_visits = raw.get("best_visits")
        agent.best_val_score = float(raw.get("best_val_score") if raw.get("best_val_score") is not None else float("-inf"))
        agent.best_val_at = int(raw.get("best_val_at") or 0)
        agent.best_val_env_sig = raw.get("best_val_env_sig")
        return agent

    def reset(self) -> None:
        """شروع دوبارهٔ آموزش از صفر."""
        self.q = {}
        self.q_coarse = {}
        self.visits = {}
        self.trained = False
        self.episodes = 0
        self.curve = []
        self.best_q = None
        self.best_q_coarse = None
        self.best_visits = None
        self.best_val_score = float("-inf")
        self.best_val_at = 0
        self.best_val_env_sig = None

    # -- انتخاب اقدام -----------------------------------------------------
    def _row(self, table: dict[str, list[float]], key: str) -> list[float]:
        return table.setdefault(key, [0.0] * len(Q_ACTIONS))

    def effective_values(self, obs) -> list[float]:
        """مقادیر مؤثر یک حالت: ترکیب ریز و درشت بر اساس بازدید."""
        fine_key = q_state_key(obs)
        coarse_key = q_coarse_key(obs)
        visits = self.visits.get(fine_key, 0)
        fine = self.q.get(fine_key)
        coarse = self.q_coarse.get(coarse_key)
        if visits >= 5 and fine is not None:
            return fine
        if fine is None and coarse is None:
            return [0.0] * len(Q_ACTIONS)
        if fine is None:
            return coarse
        if coarse is None:
            return fine
        w = min(1.0, visits / 5)
        return [w * f + (1 - w) * c for f, c in zip(fine, coarse)]

    def choose(self, state: GameState, params: dict, epsilon: float = 0.0, rng: random.Random | None = None) -> int:
        """اندیس اقدام؛ با احتمال epsilon تصادفی، وگرنه بهترین با تساوی تصادفی."""
        rng = rng or random
        if rng.random() < epsilon:
            return rng.randrange(len(Q_ACTIONS))
        obs = observe(state, params)
        return _argmax_random_tie(self.effective_values(obs), rng)


def _argmax_random_tie(values: list[float], rng) -> int:
    """اندیس بیشترین مقدار؛ در تساوی، تصادفی یکی را برمی‌گزیند."""
    best = max(values)
    tied = [i for i, v in enumerate(values) if v >= best - 1e-9]
    return rng.choice(tied)


# ---------------------------------------------------------------------------
# اجرای یک مأموریت
# ---------------------------------------------------------------------------

def run_episode(agent_fn, seed: int, params: dict, capacity: int) -> dict:
    """اجرای یک مأموریت با یک تابع تصمیم‌گیر (بدون آموزش)."""
    state = gen_map(seed, params, capacity)
    total_reward = 0.0
    guard = 0
    while not state.over and guard < 400:
        guard += 1
        info = step_env(state, agent_fn(state), params)
        total_reward += info.reward
    return {
        "score": state.score,
        "rescued": state.delivered_count,
        "total": state.total_survivors,
        "win": state.result == "win",
        "battery": max(0, state.battery),
        "time": state.time,
        "reward": total_reward,
    }


def run_training_episode(agent: QAgent, seed: int, params: dict, capacity: int, epsilon: float, rng: random.Random) -> dict:
    """یک مأموریت تمرینی با Q(λ): ردپای واجد شرایط (eligibility traces)."""
    state = gen_map(seed, params, capacity)
    total_reward = 0.0
    traces_fine: dict[str, list] = {}
    traces_coarse: dict[str, list] = {}
    guard = 0
    while not state.over and guard < 400:
        guard += 1
        obs_before = observe(state, params)
        fine_before = q_state_key(obs_before)
        coarse_before = q_coarse_key(obs_before)
        agent.visits[fine_before] = agent.visits.get(fine_before, 0) + 1

        greedy = _argmax_random_tie(agent.effective_values(obs_before), rng)
        explored = rng.random() < epsilon
        action = rng.randrange(len(Q_ACTIONS)) if explored else greedy
        if explored and action != greedy:
            traces_fine.clear()
            traces_coarse.clear()

        info = step_env(state, Q_ACTIONS[action], params)
        total_reward += info.reward

        obs_after = observe(state, params)
        fine_after = q_state_key(obs_after)
        coarse_after = q_coarse_key(obs_after)
        max_next = 0.0 if state.over else max(agent.effective_values(obs_after))
        fine_row = agent._row(agent.q, fine_before)
        delta_f = info.reward + params["gamma"] * max_next - fine_row[action]
        coarse_row = agent._row(agent.q_coarse, coarse_before)
        max_next_c = 0.0 if state.over else max(agent._row(agent.q_coarse, coarse_after))
        delta_c = info.reward + params["gamma"] * max_next_c - coarse_row[action]

        traces_fine[fine_before + "#" + str(action)] = [fine_before, action, 1.0]
        traces_coarse[coarse_before + "#" + str(action)] = [coarse_before, action, 1.0]

        decay = params["gamma"] * Q_LAMBDA
        for trace_id in list(traces_fine):
            key, a, e = traces_fine[trace_id]
            row = agent._row(agent.q, key)
            row[a] += params["alpha"] * delta_f * e
            e *= decay
            if e < 0.01:
                del traces_fine[trace_id]
            else:
                traces_fine[trace_id][2] = e
        for trace_id in list(traces_coarse):
            key, a, e = traces_coarse[trace_id]
            row = agent._row(agent.q_coarse, key)
            row[a] += (params["alpha"] * 0.5) * delta_c * e
            e *= decay
            if e < 0.01:
                del traces_coarse[trace_id]
            else:
                traces_coarse[trace_id][2] = e
    return {
        "score": state.score,
        "rescued": state.delivered_count,
        "total": state.total_survivors,
        "win": state.result == "win",
        "battery": max(0, state.battery),
        "time": state.time,
        "reward": total_reward,
    }


# ---------------------------------------------------------------------------
# آموزش و اعتبارسنجی
# ---------------------------------------------------------------------------

def eval_validation(agent: QAgent, params: dict, capacity: int) -> float:
    """میانگین امتیاز روی ۱۰ نقشهٔ ثابت اعتبارسنجی (بذرهای 9000–9009)."""
    total = 0.0
    for seed in VALIDATION_SEEDS:
        result = run_episode(lambda st: Q_ACTIONS[agent.choose(st, params, 0.0)], seed, params, capacity)
        total += result["score"]
    return total / len(VALIDATION_SEEDS)


def _checkpoint(agent: QAgent, params: dict, capacity: int) -> float:
    score = eval_validation(agent, params, capacity)
    if score > agent.best_val_score:
        agent.best_val_score = score
        agent.best_q = {k: list(v) for k, v in agent.q.items()}
        agent.best_q_coarse = {k: list(v) for k, v in agent.q_coarse.items()}
        agent.best_visits = dict(agent.visits)
        agent.best_val_at = agent.episodes
        agent.best_val_env_sig = env_signature(params, capacity)
    return score


def train(agent: QAgent, episodes: int, params: dict, capacity: int, rng: random.Random | None = None) -> dict:
    """آموزش عامل برای episodes مأموریت؛ برمی‌گرداند خلاصهٔ آموزش.

    معادل trainQL در JS: برنامهٔ کاوش در هر دور، checkpoint هر ۵۰
    مأموریت، و بازگشت به بهترین جدول اگر جدول نهایی بدتر بود.
    """
    rng = rng or random.Random()
    params = sanitize_params(params)
    sig = env_signature(params, capacity)
    env_changed = agent.best_val_env_sig is not None and agent.best_val_env_sig != sig
    if env_changed:
        agent.best_q = None
        agent.best_q_coarse = None
        agent.best_visits = None
        agent.best_val_score = float("-inf")
        agent.best_val_at = 0
    agent.best_val_env_sig = sig
    if agent.episodes == 0:
        eps_start = params["epsilon"]
    elif env_changed:
        eps_start = max(0.25, params["epsilon"])
    else:
        eps_start = max(0.18, params["epsilon"] * 0.6)
    eps_min = 0.03

    window_reward = 0.0
    done = 0
    while done < episodes:
        progress = done / max(1, episodes - 1)
        eps = max(eps_min, eps_start * (eps_min / max(eps_min, eps_start)) ** progress)
        seed = 31000 + agent.episodes * 3 + rng.randrange(2)
        result = run_training_episode(agent, seed, params, capacity, eps, rng)
        agent.episodes += 1
        done += 1
        window_reward += result["reward"]
        if agent.episodes % 25 == 0:
            agent.curve.append(window_reward / 25)
            window_reward = 0.0
            if len(agent.curve) > 40:
                agent.curve = agent.curve[-40:]
        if done % 50 == 0:
            _checkpoint(agent, params, capacity)

    final_score = eval_validation(agent, params, capacity)
    restored = False
    if agent.best_q is not None and final_score < agent.best_val_score:
        agent.q = {k: list(v) for k, v in agent.best_q.items()}
        if agent.best_q_coarse is not None:
            agent.q_coarse = {k: list(v) for k, v in agent.best_q_coarse.items()}
        if agent.best_visits is not None:
            agent.visits = dict(agent.best_visits)
        restored = True
    elif final_score >= agent.best_val_score:
        agent.best_val_score = final_score
        agent.best_q = {k: list(v) for k, v in agent.q.items()}
        agent.best_q_coarse = {k: list(v) for k, v in agent.q_coarse.items()}
        agent.best_visits = dict(agent.visits)
        agent.best_val_at = agent.episodes
        agent.best_val_env_sig = sig
    agent.trained = True
    return {
        "episodes": agent.episodes,
        "states": len(agent.q),
        "curve": list(agent.curve),
        "validationScore": final_score,
        "bestValidationScore": agent.best_val_score,
        "bestValidationAt": agent.best_val_at,
        "restoredBest": restored,
    }


# ---------------------------------------------------------------------------
# ارزیابی و مقایسه
# ---------------------------------------------------------------------------

def eval_agent(agent_fn, params: dict, capacity: int) -> dict:
    """میانگین نتیجهٔ یک عامل روی نقشه‌های مقایسه (بذرهای 5000 به بعد)."""
    n = int(params["evalMaps"])
    agg = {"score": 0.0, "rescued": 0.0, "win": 0, "battery": 0.0, "time": 0.0}
    for i in range(n):
        result = run_episode(agent_fn, EVAL_SEEDS_START + i, params, capacity)
        agg["score"] += result["score"]
        agg["rescued"] += result["rescued"]
        agg["win"] += 1 if result["win"] else 0
        agg["battery"] += result["battery"]
        agg["time"] += result["time"]
    return {
        "score": agg["score"] / n,
        "rescued": agg["rescued"] / n,
        "winRate": agg["win"] / n * 100,
        "battery": agg["battery"] / n,
        "time": agg["time"] / n,
    }


def model_strategy(agent: QAgent, limit: int = 12) -> list[dict]:
    """استراتژی مدل: پرتکرارترین حالت‌های یادگرفته‌شده به‌صورت «اگر … آنگاه …»."""
    entries = []
    for key, count in agent.visits.items():
        row = agent.q.get(key)
        if not row:
            continue
        best_action = max(range(len(row)), key=lambda i: row[i])
        entries.append({"stateKey": key, "count": count, "actionId": Q_ACTIONS[best_action], "q": row[best_action]})
    entries.sort(key=lambda e: (-e["count"], -e["q"]))
    return [
        {
            "phrase": state_phrase(e["stateKey"]),
            "actionId": e["actionId"],
            "actionLabel": ACTION_LABEL[e["actionId"]],
        }
        for e in entries[:limit]
    ]

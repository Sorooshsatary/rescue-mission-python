"""موتور بازی مأموریت نجات — برگردان دقیق منطق جاوااسکریپت به پایتون.

شامل: تولید نقشهٔ تصادفی با mulberry32، دایکسترا، مشاهدهٔ ربات،
ارزیابی شرط‌ها، اجرای یک قدم (stepEnv) با همهٔ پاداش‌ها و جریمه‌ها،
و انتخاب اقدام از روی قانون‌های دانش‌آموز.

فقط از کتابخانهٔ استاندارد استفاده می‌شود (heapq و random).
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field

from .config import (
    CONDITION_BY_ID,
    LEVEL_NAME,
    PARAM_DEFAULTS,
    points_of,
    sanitize_params,
)

GRID = 12
INF = float("inf")

# ---------------------------------------------------------------------------
# ابزارهای پایه
# ---------------------------------------------------------------------------

_MASK32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    """معادل Math.imul در جاوااسکریپت: ۳۲ بیت پایین ضرب علامت‌دار."""
    return ((a & _MASK32) * (b & _MASK32)) & _MASK32


def mulberry32(seed: int):
    """مولد تصادفی mulberry32؛ دقیقاً همان پیاده‌سازی نسخهٔ JS.

    با بذر یکسان، دقیقاً همان دنبالهٔ اعداد JS را تولید می‌کند.
    """
    a = seed & _MASK32

    def rnd() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & _MASK32
        t = _imul(a ^ (a >> 15), 1 | a)
        t = (((t + _imul(t ^ (t >> 7), 61 | t)) & _MASK32) ^ t) & _MASK32
        return ((t ^ (t >> 14)) & _MASK32) / 4294967296

    return rnd


def cell_key(x: int, y: int) -> int:
    """کلید یک خانه: y*12 + x (همان key در JS)."""
    return y * GRID + x


def in_bounds(x: int, y: int) -> bool:
    """آیا مختصات داخل شبکهٔ ۱۲×۱۲ است؟"""
    return 0 <= x < GRID and 0 <= y < GRID


def fa_num(value) -> str:
    """عدد را با ارقام فارسی برمی‌گرداند (برای پیام‌های رویداد)."""
    fa = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(fa[int(d)] if d.isdigit() else d for d in str(value))


# ---------------------------------------------------------------------------
# وضعیت بازی
# ---------------------------------------------------------------------------

@dataclass
class Survivor:
    """یک مصدوم روی نقشه."""

    x: int
    y: int
    level: str  # "normal" | "urgent" | "critical"
    picked: bool = False
    delivered: bool = False


@dataclass
class GameState:
    """وضعیت کامل یک مأموریت."""

    seed: int
    capacity: int
    base: tuple[int, int]
    chargers: list[tuple[int, int]]
    obstacles: set[int]
    danger: set[int]
    survivors: list[Survivor]
    robot: tuple[int, int]
    battery: int
    time: int
    max_time: int
    carrying: list[str] = field(default_factory=list)
    score: int = 0
    delivered_count: int = 0
    over: bool = False
    result: str = ""  # "win" | "battery" | "time"
    visited: set[int] = field(default_factory=set)

    @property
    def total_survivors(self) -> int:
        """تعداد کل مصدومان نقشه."""
        return len(self.survivors)


def gen_map(seed: int, params: dict, capacity: int | None = None) -> GameState:
    """ساخت نقشهٔ تصادفی با بذر ثابت؛ دقیقاً معادل genMap در JS.

    تا ۲۰۰ تلاش می‌کند تا نقشه‌ای بسازد که همهٔ مصدومان و شارژرها
    از پایگاه قابل‌دسترس باشند؛ در غیر این صورت خطا می‌دهد.
    """
    params = sanitize_params(params)
    cap = params["capacity"] if capacity is None else capacity
    base = (0, 11)
    for attempt in range(200):
        rnd = mulberry32(seed * 1000 + attempt)
        used = {cell_key(*base)}

        def pick() -> tuple[int, int]:
            while True:
                x = int(rnd() * GRID)
                y = int(rnd() * GRID)
                k = cell_key(x, y)
                if k not in used:
                    used.add(k)
                    return (x, y)

        chargers = [pick(), pick()]
        obstacles = {cell_key(*pick()) for _ in range(int(params["obstacles"]))}
        danger = {cell_key(*pick()) for _ in range(int(params["dangerCells"]))}
        levels = (
            ["critical"] * int(params["survivorsCritical"])
            + ["urgent"] * int(params["survivorsUrgent"])
            + ["normal"] * int(params["survivorsNormal"])
        )
        survivors = [Survivor(x=p[0], y=p[1], level=lv) for lv, p in ((lv, pick()) for lv in levels)]
        state = GameState(
            seed=seed,
            capacity=int(cap),
            base=base,
            chargers=chargers,
            obstacles=obstacles,
            danger=danger,
            survivors=survivors,
            robot=base,
            battery=int(params["startBattery"]),
            time=0,
            max_time=int(params["maxTime"]),
            visited={cell_key(*base)},
        )
        # بررسی دسترس‌پذیری همهٔ هدف‌ها از پایگاه (BFS)
        seen = {cell_key(*base)}
        queue = [base]
        while queue:
            cx, cy = queue.pop(0)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                k = cell_key(nx, ny)
                if in_bounds(nx, ny) and k not in obstacles and k not in seen:
                    seen.add(k)
                    queue.append((nx, ny))
        if all(cell_key(s.x, s.y) in seen for s in survivors) and all(
            cell_key(*c) in seen for c in chargers
        ):
            return state
    raise RuntimeError("map generation failed")


# ---------------------------------------------------------------------------
# دایکسترا
# ---------------------------------------------------------------------------

@dataclass
class DijkstraResult:
    """نتیجهٔ دایکسترا از موقعیت ربات: فاصله (قدم) و هزینهٔ باتری."""

    dist: dict[int, int]
    cost: dict[int, int]
    prev: dict[int, int]


def dijkstra(state: GameState, params: dict, danger_cost: int | None = None) -> DijkstraResult:
    """دایکسترا از موقعیت ربات؛ هزینهٔ باتری (خطرناک=dangerCost) + تعداد قدم.

    ترتیب اولویت (هزینه، فاصله) دقیقاً مثل JS است؛ برای تساوی کامل،
    ترتیب درج (شمارنده) به‌جای مختصات استفاده می‌شود.
    """
    dc = params["dangerCost"] if danger_cost is None else danger_cost
    dist: dict[int, int] = {}
    cost: dict[int, int] = {}
    prev: dict[int, int] = {}
    start = cell_key(*state.robot)
    dist[start] = 0
    cost[start] = 0
    counter = itertools.count()
    pq: list[tuple[int, int, int, int, int]] = [(0, 0, next(counter), state.robot[0], state.robot[1])]
    while pq:
        c, d, _, x, y = heapq.heappop(pq)
        k = cell_key(x, y)
        if c != cost.get(k):
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            nk = cell_key(nx, ny)
            if not in_bounds(nx, ny) or nk in state.obstacles:
                continue
            nc = c + (dc if nk in state.danger else 1)
            nd = d + 1
            if nk not in cost or nc < cost[nk] or (nc == cost[nk] and nd < dist[nk]):
                cost[nk] = nc
                dist[nk] = nd
                prev[nk] = k
                heapq.heappush(pq, (nc, nd, next(counter), nx, ny))
    return DijkstraResult(dist=dist, cost=cost, prev=prev)


def next_step_toward(state: GameState, dij: DijkstraResult, target: tuple[int, int]) -> tuple[int, int] | None:
    """یک قدم از ربات به سمت هدف، در امتداد کوتاه‌ترین مسیر دایکسترا."""
    tk = cell_key(*target)
    if tk not in dij.prev:
        return None
    cur = tk
    start = cell_key(*state.robot)
    while dij.prev[cur] != start:
        cur = dij.prev[cur]
    return (cur % GRID, cur // GRID)


# ---------------------------------------------------------------------------
# مشاهده و شرط‌ها
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    """آنچه ربات در یک قدم می‌بیند."""

    dij: DijkstraResult
    alive: list[Survivor]
    nearest: Survivor | None
    nearest_d: float
    crit: Survivor | None
    crit_d: float
    crit_exists: bool
    urg: Survivor | None
    urg_d: float
    charger_d: float
    base_d: float
    base_cost: float
    battery: int
    carrying: int
    capacity: int
    time_left: int


def observe(state: GameState, params: dict) -> Observation:
    """مشاهدهٔ ربات از وضعیت فعلی؛ معادل observe در JS."""
    dij = dijkstra(state, params)
    alive = [s for s in state.survivors if not s.picked and not s.delivered]

    def dist_of(s: Survivor) -> float:
        return dij.dist.get(cell_key(s.x, s.y), INF)

    nearest: Survivor | None = None
    nearest_d: float = INF
    crit: Survivor | None = None
    crit_d: float = INF
    urg: Survivor | None = None
    urg_d: float = INF
    for s in alive:
        d = dist_of(s)
        if d == INF:
            continue
        if d < nearest_d:
            nearest_d = d
            nearest = s
        if s.level == "critical" and d < crit_d:
            crit_d = d
            crit = s
        if s.level == "urgent" and d < urg_d:
            urg_d = d
            urg = s
    base_d = dij.dist.get(cell_key(*state.base), INF)
    base_cost = dij.cost.get(cell_key(*state.base), INF)
    charger_d: float = INF
    for c in state.chargers:
        d = dij.dist.get(cell_key(*c), INF)
        if d < charger_d:
            charger_d = d
    return Observation(
        dij=dij,
        alive=alive,
        nearest=nearest,
        nearest_d=nearest_d,
        crit=crit,
        crit_d=crit_d,
        crit_exists=any(s.level == "critical" for s in alive),
        urg=urg,
        urg_d=urg_d,
        charger_d=charger_d,
        base_d=base_d,
        base_cost=base_cost,
        battery=state.battery,
        carrying=len(state.carrying),
        capacity=state.capacity,
        time_left=state.max_time - state.time,
    )


def rule_number(rule: dict) -> int | None:
    """عدد مؤثر یک قانون: مقدار ذخیره‌شدهٔ آن، وگرنه پیش‌فرض شرط."""
    definition = CONDITION_BY_ID.get(rule.get("id", ""))
    if not definition or "param" not in definition:
        return None
    param = definition["param"]
    value = rule.get("threshold", rule.get("value"))
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = float(param["def"])
    if math.isnan(v):
        v = float(param["def"])
    return int(min(param["max"], max(param["min"], round(v))))


def normalize_rules(rules: list[dict] | None) -> list[dict]:
    """برای هر شرط کمی، عدد پیش‌فرض صریح را در قانون می‌نویسد."""
    if not isinstance(rules, list):
        return []
    out = []
    for rule in rules:
        r = dict(rule) if isinstance(rule, dict) else {}
        if r.get("id") in CONDITION_BY_ID and "param" in CONDITION_BY_ID[r["id"]]:
            r["threshold"] = rule_number(r)
        out.append(r)
    return out


def condition_label(rule: dict) -> str:
    """برچسب خوانای یک قانون، با عدد انتخابی دانش‌آموز (ارقام فارسی)."""
    definition = CONDITION_BY_ID.get(rule.get("id", ""))
    base = definition["label"] if definition else str(rule.get("id", ""))
    if not definition or "param" not in definition:
        return base
    n = fa_num(rule_number(rule))
    kind = definition["param"]["kind"]
    if kind == "battery":
        return base.replace("حد انتخابی", n + "٪")
    if kind == "distance":
        return base + " (حداکثر " + n + " خانه)"
    if kind == "distanceFar":
        if rule.get("id") == "baseFar":
            return base + " (بیش از " + n + " خانه)"
        return base + " (نزدیک‌ترین مصدوم بیش از " + n + " خانه دور است)"
    if kind == "time":
        return base + " (" + n + " قدم یا کمتر)"
    if kind == "margin":
        return base + " (با حاشیهٔ " + n + " واحد باتری)"
    return base


def eval_condition(rule: dict, obs: Observation) -> bool:
    """آیا شرط این قانون در مشاهدهٔ فعلی برقرار است؟"""
    n = rule_number(rule)
    rule_id = rule.get("id")
    if rule_id == "full":
        return obs.carrying >= obs.capacity
    if rule_id == "carryingAny":
        return obs.carrying > 0
    if rule_id == "batteryBelow":
        return obs.battery < n
    if rule_id == "batteryAbove":
        return obs.battery > n
    if rule_id == "criticalNear":
        return bool(obs.crit and obs.crit_d <= n)
    if rule_id == "criticalExists":
        return obs.crit_exists
    if rule_id == "urgentNear":
        return bool(obs.urg and obs.urg_d <= n)
    if rule_id == "survivorNear":
        return bool(obs.nearest and obs.nearest_d <= n)
    if rule_id == "noSurvivorVisible":
        return not obs.nearest or obs.nearest_d > n
    if rule_id == "baseNear":
        return obs.base_d <= n
    if rule_id == "baseFar":
        return obs.base_d > n
    if rule_id == "chargerNear":
        return obs.charger_d <= n
    if rule_id == "timeLow":
        return obs.time_left <= n
    if rule_id == "lowForReturn":
        return obs.battery < obs.base_cost + n
    return False


# ---------------------------------------------------------------------------
# اجرای یک قدم
# ---------------------------------------------------------------------------

@dataclass
class StepInfo:
    """نتیجهٔ یک قدم: رویداد، پاداش، برداشتن و تحویل."""

    event: str = ""
    reward: float = -0.05
    picked: Survivor | None = None
    delivered_now: int = 0
    ineffective: bool = False


def _finish_step(state: GameState, info: StepInfo) -> None:
    """پایان‌بندی قدم: برد، مرگ باتری یا تمام‌شدن زمان."""
    if all(s.delivered for s in state.survivors):
        state.over = True
        state.result = "win"
        info.reward += 15
        return
    on_charger = any(c == state.robot for c in state.chargers)
    if state.battery <= 0 and not on_charger:
        state.over = True
        state.result = "battery"
        info.reward -= 8
        return
    if state.time >= state.max_time:
        state.over = True
        state.result = "time"
        info.reward -= 2


def step_env(state: GameState, action_id: str, params: dict) -> StepInfo:
    """اجرای یک قدم از یک اقدام کلان؛ دقیقاً معادل stepEnv در JS.

    پاداش‌ها: برداشتن ۳+ (بحرانی ۲+، فوری ۱+)، تحویل ۰٫۴×امتیاز،
    برد ۱۵+، مرگ باتری ۸−، تمام‌شدن زمان ۲−، قدم پایه ۰٫۰۵−،
    بازگشت خالی به پایگاه ۰٫۲۵−، توقف روی شارژر پر ۰٫۲۵−، اقدام بی‌اثر ۱−.
    """
    params = sanitize_params(params)
    points = points_of(params)
    info = StepInfo()
    if state.over:
        return info
    obs = observe(state, params)
    state.visited.add(cell_key(*state.robot))
    orig_action = action_id
    # اقدام‌های ترکیبی به رفتار پایه ترجمه می‌شوند
    if action_id == "chargeSmart":
        action_id = "toCharger" if obs.battery < params["smartChargeThreshold"] else "rescueNearest"
    elif action_id == "deliverPartial":
        action_id = "toBase" if state.carrying else "search"
    on_charger = any(c == state.robot for c in state.chargers)
    target: tuple[int, int] | None = None
    want_pickup: Survivor | None = None
    ineffective = False

    if action_id in ("rescueNearest", "rescueUrgent", "search") or orig_action == "rescueSafe":
        if len(state.carrying) >= state.capacity:
            # ظرفیت پر است: اقدام نجات/جست‌وجو واقعاً بی‌اثر می‌ماند
            # (هیچ تغییر مسیر مخفی‌ای به پایگاه در کار نیست).
            ineffective = True
        elif orig_action == "rescueSafe":
            dij_safe = dijkstra(state, params, danger_cost=15)
            best: Survivor | None = None
            best_cost = INF
            for sv in obs.alive:
                c = dij_safe.cost.get(cell_key(sv.x, sv.y))
                if c is not None and c < best_cost:
                    best_cost = c
                    best = sv
            if best:
                if (best.x, best.y) == state.robot:
                    want_pickup = best
                else:
                    target = (best.x, best.y)
            else:
                target = state.base
        elif action_id == "search":
            # جست‌وجو یعنی کاوش: نزدیک‌ترین خانه‌ای که هنوز دیده نشده است؛
            # فقط وقتی همهٔ خانه‌های قابل‌دسترس دیده شده‌اند، سراغ نزدیک‌ترین مصدوم.
            tgt: tuple[int, int] | None = None
            td = INF
            for y in range(GRID):
                for x in range(GRID):
                    k = cell_key(x, y)
                    if k in state.obstacles or k in state.visited:
                        continue
                    d = obs.dij.dist.get(k)
                    if d is not None and d < td:
                        td = d
                        tgt = (x, y)
            if tgt:
                target = tgt
            elif obs.nearest:
                s = obs.nearest
                if (s.x, s.y) == state.robot:
                    want_pickup = s
                else:
                    target = (s.x, s.y)
            else:
                target = state.base
        elif obs.alive:
            if action_id == "rescueUrgent":
                def sort_key(s: Survivor):
                    return (-points[s.level], obs.dij.dist.get(cell_key(s.x, s.y), 99))

                s = sorted(obs.alive, key=sort_key)[0]
            else:
                s = obs.nearest
            if s:
                if (s.x, s.y) == state.robot:
                    want_pickup = s
                else:
                    target = (s.x, s.y)
        else:
            target = state.base
    elif action_id == "toBase":
        target = state.base
        if not state.carrying and obs.alive:
            info.reward -= 0.25
    elif action_id == "toCharger":
        if on_charger and state.battery < 100:
            state.battery = min(100, state.battery + int(params["chargeRate"]))
            state.time += 1
            info.event = "در حال شارژ… +" + fa_num(params["chargeRate"]) + "٪ باتری"
            _finish_step(state, info)
            return info
        if on_charger and state.battery >= 100:
            state.time += 1
            info.event = "باتری پر است — توقف روی شارژر"
            info.reward -= 0.25
            _finish_step(state, info)
            return info
        best_charger: tuple[int, int] | None = None
        best_d = INF
        for c in state.chargers:
            d = obs.dij.dist.get(cell_key(*c))
            if d is not None and d < best_d:
                best_d = d
                best_charger = c
        target = best_charger

    if want_pickup is not None:
        state.time += 1
        want_pickup.picked = True
        state.carrying.append(want_pickup.level)
        info.picked = want_pickup
        info.event = "مصدوم " + LEVEL_NAME[want_pickup.level] + " سوار شد"
        info.reward += 3 + (2 if want_pickup.level == "critical" else 1 if want_pickup.level == "urgent" else 0)
    elif ineffective:
        state.time += 1
        info.event = (
            "ظرفیت پر است — اقدام جست‌وجو بی‌اثر ماند"
            if action_id == "search"
            else "ظرفیت پر است — اقدام نجات بی‌اثر ماند"
        )
        info.reward -= 1
        info.ineffective = True
    elif target is not None:
        if target == state.robot:
            state.time += 1
            info.event = "در مقصد، منتظر ماند"
        else:
            dij_use = dijkstra(state, params, danger_cost=15) if orig_action == "rescueSafe" else obs.dij
            ns = next_step_toward(state, dij_use, target)
            if ns:
                state.robot = ns
                state.battery -= int(params["dangerCost"]) if cell_key(*ns) in state.danger else 1
                state.time += 1
                info.event = "حرکت به سمت هدف"
            else:
                state.time += 1
                info.event = "مسیر بسته است؛ منتظر ماند"
    else:
        state.time += 1
        info.event = "اقدامی ممکن نبود"

    # تحویل در پایگاه
    if state.robot == state.base and state.carrying:
        pts = 0
        for lv in state.carrying:
            pts += points[lv]
            sv = next((s for s in state.survivors if s.picked and not s.delivered and s.level == lv), None)
            if sv:
                sv.delivered = True
        n = len(state.carrying)
        for s in state.survivors:
            if n <= 0:
                break
            if s.picked and not s.delivered:
                s.delivered = True
                n -= 1
        state.score += pts
        state.delivered_count += len(state.carrying)
        info.delivered_now = len(state.carrying)
        info.event = (
            fa_num(len(state.carrying))
            + " مصدوم به پایگاه تحویل شد (+"
            + fa_num(pts)
            + " امتیاز)"
        )
        info.reward += pts * 0.4
        state.carrying = []
    _finish_step(state, info)
    return info


# ---------------------------------------------------------------------------
# تصمیم انسانی از روی قانون‌ها
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    """تصمیم یک قدم: مشاهده، ارزیابی قانون‌ها و اقدام انتخاب‌شده."""

    obs: Observation
    evals: list[dict]
    rule_index: int
    action_id: str
    fallback: bool
    event: str = ""
    ineffective: bool = False


def human_decision(rules: list[dict], state: GameState, params: dict) -> Decision:
    """اولین قانون برقرار را اجرا می‌کند؛ وگرنه رفتار پیش‌فرض.

    رفتار پیش‌فرض: اگر مصدومی حمل می‌کند به پایگاه برمی‌گردد،
    وگرنه به جست‌وجوی مصدومان می‌رود.
    """
    obs = observe(state, params)
    evals = [{"rule": r, "match": eval_condition(r, obs)} for r in rules]
    for i, e in enumerate(evals):
        if e["match"]:
            return Decision(obs=obs, evals=evals, rule_index=i, action_id=e["rule"]["action"], fallback=False)
    fallback = "toBase" if state.carrying else "search"
    return Decision(obs=obs, evals=evals, rule_index=-1, action_id=fallback, fallback=True)


# ---------------------------------------------------------------------------
# اجرای کامل یک مأموریت و اسنپ‌شات
# ---------------------------------------------------------------------------

def snapshot(state: GameState, decision: Decision | None = None) -> dict:
    """اسنپ‌شات وضعیت برای بازپخش و نمایش در فرانت‌اند."""
    return {
        "robot": {"x": state.robot[0], "y": state.robot[1]},
        "battery": state.battery,
        "time": state.time,
        "score": state.score,
        "deliveredCount": state.delivered_count,
        "carrying": list(state.carrying),
        "survivors": [
            {"x": s.x, "y": s.y, "level": s.level, "picked": s.picked, "delivered": s.delivered}
            for s in state.survivors
        ],
        "over": state.over,
        "result": state.result,
        "decision": (
            {
                "ruleIndex": decision.rule_index,
                "actionId": decision.action_id,
                "fallback": decision.fallback,
                "event": decision.event,
                "ineffective": decision.ineffective,
                "obs": {
                    "battery": decision.obs.battery,
                    "carrying": decision.obs.carrying,
                    "capacity": decision.obs.capacity,
                    "nearestD": None if decision.obs.nearest_d == INF else decision.obs.nearest_d,
                    "nearestLevel": decision.obs.nearest.level if decision.obs.nearest else None,
                    "critD": None if decision.obs.crit_d == INF else decision.obs.crit_d,
                    "critExists": decision.obs.crit_exists,
                    "urgD": None if decision.obs.urg_d == INF else decision.obs.urg_d,
                    "chargerD": None if decision.obs.charger_d == INF else decision.obs.charger_d,
                    "baseD": None if decision.obs.base_d == INF else decision.obs.base_d,
                    "baseCost": None if decision.obs.base_cost == INF else decision.obs.base_cost,
                    "timeLeft": decision.obs.time_left,
                },
                "evals": [
                    {"rule": e["rule"], "match": e["match"], "label": condition_label(e["rule"])}
                    for e in decision.evals
                ],
            }
            if decision
            else None
        ),
    }


def map_info(state: GameState) -> dict:
    """اطلاعات ثابت نقشه (پایگاه، شارژرها، موانع، خطر) برای رندر فرانت‌اند."""
    return {
        "base": {"x": state.base[0], "y": state.base[1]},
        "chargers": [{"x": c[0], "y": c[1]} for c in state.chargers],
        "obstacles": sorted(state.obstacles),
        "danger": sorted(state.danger),
    }


def run_human_episode(rules: list[dict], seed: int, params: dict, capacity: int | None = None) -> dict:
    """اجرای کامل یک استراتژی انسانی روی یک نقشه؛ برمی‌گرداند خلاصه + قدم‌ها."""
    params = sanitize_params(params)
    state = gen_map(seed, params, capacity)
    steps = [snapshot(state)]
    guard = 0
    while not state.over and guard < 1000:
        guard += 1
        decision = human_decision(rules, state, params)
        info = step_env(state, decision.action_id, params)
        decision.event = info.event
        decision.ineffective = info.ineffective
        steps.append(snapshot(state, decision))
    return {
        "seed": seed,
        "score": state.score,
        "rescued": state.delivered_count,
        "total": state.total_survivors,
        "win": state.result == "win",
        "battery": max(0, state.battery),
        "time": state.time,
        "result": state.result,
        "map": map_info(state),
        "steps": steps,
    }


def run_trace(agent_fn, seed: int, params: dict, capacity: int | None = None) -> dict:
    """اجرای کامل یک مأموریت با یک تابع تصمیم‌گیر دلخواه، با ردّ قدم‌ها.

    برای نمایش همزمان دو تخته در بخش مقایسه استفاده می‌شود.
    """
    params = sanitize_params(params)
    state = gen_map(seed, params, capacity)
    steps = [snapshot(state)]
    guard = 0
    while not state.over and guard < 1000:
        guard += 1
        action = agent_fn(state)
        info = step_env(state, action, params)
        decision = Decision(
            obs=observe(state, params),
            evals=[],
            rule_index=-1,
            action_id=action,
            fallback=False,
            event=info.event,
            ineffective=info.ineffective,
        )
        steps.append(snapshot(state, decision))
    return {
        "seed": seed,
        "score": state.score,
        "rescued": state.delivered_count,
        "total": state.total_survivors,
        "win": state.result == "win",
        "battery": max(0, state.battery),
        "time": state.time,
        "result": state.result,
        "map": map_info(state),
        "steps": steps,
    }

"""تست‌های موتور بازی: تعیین‌پذیری نقشه، قدم و تحویل مصدوم."""
from app.config import PARAM_DEFAULTS, sanitize_params
from app.engine import gen_map, human_decision, run_human_episode, step_env

CHAMPION = [
    {"id": "full", "action": "toBase"},
    {"id": "criticalNear", "threshold": 3, "action": "rescueUrgent"},
    {"id": "criticalExists", "action": "rescueSafe"},
    {"id": "urgentNear", "threshold": 3, "action": "rescueUrgent"},
    {"id": "survivorNear", "threshold": 3, "action": "rescueNearest"},
]


def _params(**overrides):
    return sanitize_params({**PARAM_DEFAULTS, **overrides})


def test_gen_map_deterministic_same_seed():
    """نقشه با بذر ثابت همیشه یکسان است."""
    a = gen_map(7, _params())
    b = gen_map(7, _params())
    assert [(s.x, s.y, s.level) for s in a.survivors] == [(s.x, s.y, s.level) for s in b.survivors]
    assert a.chargers == b.chargers
    assert a.obstacles == b.obstacles
    assert a.danger == b.danger


def test_gen_map_different_seed_differs():
    a = gen_map(7, _params())
    b = gen_map(8, _params())
    assert [(s.x, s.y) for s in a.survivors] != [(s.x, s.y) for s in b.survivors]


def test_gen_map_all_targets_reachable():
    """همهٔ مصدومان و شارژرها از پایگاه قابل‌دسترس‌اند."""
    from app.engine import cell_key, dijkstra

    state = gen_map(7, _params())
    dij = dijkstra(state, _params())
    for s in state.survivors:
        assert cell_key(s.x, s.y) in dij.dist
    for c in state.chargers:
        assert cell_key(*c) in dij.dist


def test_champion_episode_scores():
    """استراتژی قهرمان روی نقشهٔ ۷ امتیاز می‌گیرد و مأموریت تمام می‌شود."""
    result = run_human_episode(CHAMPION, 7, _params())
    assert result["score"] > 0
    assert result["rescued"] >= 1
    assert result["steps"][-1]["over"] is True
    assert result["steps"][-1]["result"] in ("win", "battery", "time")


def test_step_env_pickup_and_delivery():
    """ربات مصدوم را سوار می‌کند و با رسیدن به پایگاه تحویل می‌دهد."""
    params = _params()
    state = gen_map(7, params)
    # ربات را کنار اولین مصدوم می‌گذاریم تا برداشتن را تست کنیم
    target = state.survivors[0]
    state.robot = (target.x, target.y)
    info = step_env(state, "rescueNearest", params)
    assert info.picked is not None
    assert len(state.carrying) == 1
    assert info.reward > 0
    # حالا ربات را به پایگاه می‌بریم و تحویل را تست می‌کنیم
    state.robot = state.base
    before = state.score
    info = step_env(state, "toBase", params)
    assert info.delivered_now == 1
    assert state.score > before
    assert state.delivered_count == 1
    assert state.carrying == []


def test_step_env_full_capacity_ineffective():
    """وقتی ظرفیت پر است، اقدام نجات بی‌اثر می‌ماند و جریمه می‌گیرد."""
    params = _params(capacity=1)
    state = gen_map(7, params)
    state.carrying = ["normal"]
    state.robot = (5, 5)  # دور از پایگاه تا تحویل هم‌زمان رخ ندهد
    info = step_env(state, "rescueNearest", params)
    assert info.ineffective is True
    assert info.reward < 0
    assert len(state.carrying) == 1


def test_human_decision_fallback():
    """بدون قانون برقرار، رفتار پیش‌فرض جست‌وجو انتخاب می‌شود."""
    params = _params()
    state = gen_map(7, params)
    decision = human_decision([], state, params)
    assert decision.fallback is True
    assert decision.action_id == "search"

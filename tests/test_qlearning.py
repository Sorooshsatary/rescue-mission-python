"""تست‌های عامل یادگیرنده: آموزش کوتاه بدون خطا و امتیاز عددی."""
from app.config import PARAM_DEFAULTS, sanitize_params
from app.qlearning import QAgent, eval_agent, eval_validation, model_strategy, train


def _params(**overrides):
    return sanitize_params({**PARAM_DEFAULTS, **overrides})


def test_train_short_runs_and_scores():
    """آموزش ۲۰ مأموریت بدون خطا تمام می‌شود و امتیاز اعتبارسنجی عددی می‌دهد."""
    agent = QAgent()
    summary = train(agent, 20, _params(), capacity=2)
    assert agent.trained is True
    assert agent.episodes == 20
    assert len(agent.q) > 0
    assert isinstance(summary["validationScore"], float)
    assert summary["episodes"] == 20


def test_eval_agent_returns_averages():
    """ارزیابی عامل آموزش‌دیده میانگین‌های عددی برمی‌گرداند."""
    agent = QAgent()
    train(agent, 20, _params(), capacity=2)
    result = eval_agent(lambda st: agent.choose(st, _params(), 0.0), _params(evalMaps=5), capacity=2)
    assert 0 <= result["score"] <= 200
    assert 0 <= result["winRate"] <= 100
    assert 0 <= result["battery"] <= 100


def test_model_strategy_readable_rules():
    """استراتژی مدل بعد از آموزش، قانون‌های خوانای «اگر … آنگاه …» می‌دهد."""
    agent = QAgent()
    train(agent, 20, _params(), capacity=2)
    rules = model_strategy(agent)
    assert len(rules) >= 1
    assert all("اگر" in r["phrase"] or "باتری" in r["phrase"] for r in rules)
    assert all(r["actionLabel"] for r in rules)


def test_reset_clears_training():
    """شروع دوبارهٔ آموزش، جدول و شمار مأموریت‌ها را صفر می‌کند."""
    agent = QAgent()
    train(agent, 20, _params(), capacity=2)
    agent.reset()
    assert agent.episodes == 0
    assert agent.q == {}
    assert agent.trained is False

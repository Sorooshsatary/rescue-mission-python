"""تست‌های API: تنظیمات، قفل‌ها، شبیه‌سازی و ذخیرهٔ استراتژی."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import store

DATA_DIR = Path(__file__).parent / ".test-data"


@pytest.fixture(autouse=True)
def _clean_data():
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)


@pytest.fixture()
def client():
    import app.server as server_module
    import importlib

    importlib.reload(server_module)
    return TestClient(server_module.app)


CHAMPION = [
    {"id": "full", "action": "toBase"},
    {"id": "criticalNear", "threshold": 3, "action": "rescueUrgent"},
    {"id": "criticalExists", "action": "rescueSafe"},
    {"id": "urgentNear", "threshold": 3, "action": "rescueUrgent"},
    {"id": "survivorNear", "threshold": 3, "action": "rescueNearest"},
]


def test_meta_returns_conditions_actions_presets(client):
    r = client.get("/api/meta")
    assert r.status_code == 200
    data = r.json()
    assert len(data["conditions"]) == 14
    assert len(data["actions"]) == 8
    assert len(data["presets"]) == 7
    assert data["paramDefaults"]["capacity"] == 2


def test_settings_read_update_and_persist(client):
    """خواندن تنظیمات، تغییر با رمز درست و ماندگاری آن."""
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["capacity"] == 2

    r = client.put("/api/settings", json={"capacity": 1, "maxTime": 9999})
    assert r.status_code == 403  # بدون رمز ادمین

    r = client.put("/api/settings", json={"capacity": 1, "maxTime": 9999}, headers={"X-Admin-Code": "123"})
    assert r.status_code == 200
    assert r.json()["settings"]["capacity"] == 1
    assert r.json()["settings"]["maxTime"] == 400  # clamp به سقف مجاز

    r = client.get("/api/settings")
    assert r.json()["capacity"] == 1
    assert store.load_settings()["capacity"] == 1  # ماندگاری روی دیسک


def test_settings_wrong_code_forbidden(client):
    r = client.put("/api/settings", json={"capacity": 1}, headers={"X-Admin-Code": "000"})
    assert r.status_code == 403


def test_unlock_stage_and_admin(client):
    r = client.post("/api/unlock", json={"code": "1384", "kind": "stage"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    r = client.post("/api/unlock", json={"code": "۱۳۸۴", "kind": "stage"})
    assert r.status_code == 200  # ارقام فارسی هم پذیرفته می‌شوند
    r = client.post("/api/unlock", json={"code": "0000", "kind": "stage"})
    assert r.status_code == 403
    r = client.post("/api/unlock", json={"code": "123", "kind": "admin"})
    assert r.status_code == 200
    r = client.post("/api/unlock", json={"code": "999", "kind": "admin"})
    assert r.status_code == 403


def test_simulate_champion(client):
    r = client.post("/api/simulate", json={"rules": CHAMPION, "seed": 7})
    assert r.status_code == 200
    data = r.json()
    assert data["score"] > 0
    assert data["rescued"] >= 1
    assert len(data["steps"]) >= 2
    assert data["steps"][0]["decision"] is None
    assert data["steps"][1]["decision"]["actionId"]


def test_strategies_save_and_list(client):
    r = client.post("/api/strategies", json={"name": "شجاعانه", "rules": CHAMPION})
    assert r.status_code == 200
    assert len(r.json()["strategies"]) == 1
    r = client.get("/api/strategies")
    assert r.json()["strategies"][0]["name"] == "شجاعانه"
    assert r.json()["strategies"][0]["rules"][0]["id"] == "full"
    r = client.delete("/api/strategies/شجاعانه")
    assert r.json()["strategies"] == []


def test_train_status_and_short_train(client):
    r = client.get("/api/train/status")
    assert r.status_code == 200
    assert r.json()["trained"] is False
    r = client.post("/api/train", json={"episodes": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["episodes"] == 5
    assert isinstance(data["validationScore"], float)
    r = client.get("/api/train/status")
    assert r.json()["trained"] is True

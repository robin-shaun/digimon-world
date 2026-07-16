"""FastAPI app 测试: 验证 /api/digimon 列表 / 移动 / WebSocket。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world import __version__
from digimon_world.api import app
from digimon_world.world import get_world, reset_world


@pytest.fixture(autouse=True)
def _reset():
    """每个测试前重置世界单例,避免污染。"""
    reset_world()
    yield
    reset_world()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_root(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "DIGIMON WORLD"
    assert data["version"] == __version__
    assert data["status"] == "ok"
    assert data["digimon_count"] >= 1


def test_list_digimon(client: TestClient) -> None:
    r = client.get("/api/digimon")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 3
    names = {d["name"] for d in data["digimon"]}
    assert "亚古兽" in names
    assert "加布兽" in names
    # 字段完整性
    for d in data["digimon"]:
        assert "position" in d
        assert "x" in d["position"] and "y" in d["position"]
        assert d["stage"] == "rookie"


def test_get_digimon(client: TestClient) -> None:
    r = client.get("/api/digimon/亚古兽")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "亚古兽"
    assert data["species"] == "agumon"
    assert data["stage"] == "rookie"


def test_get_digimon_not_found(client: TestClient) -> None:
    r = client.get("/api/digimon/不存在兽")
    assert r.status_code == 404


def test_get_position(client: TestClient) -> None:
    r = client.get("/api/digimon/亚古兽/position")
    assert r.status_code == 200
    pos = r.json()
    assert "x" in pos and "y" in pos


def test_move_digimon(client: TestClient) -> None:
    # 先拿当前位置
    r = client.get("/api/digimon/亚古兽/position")
    start = (r.json()["x"], r.json()["y"])

    # 移动
    r = client.post("/api/digimon/亚古兽/move", json={"dx": 50, "dy": -30})
    assert r.status_code == 200
    new = r.json()["position"]
    assert new["x"] == start[0] + 50
    assert new["y"] == start[1] - 30


def test_move_clamp_to_bounds(client: TestClient) -> None:
    """移动不能出地图边界(多次移动累积后夹紧)。"""
    # 推到最右
    for _ in range(20):
        client.post("/api/digimon/亚古兽/move", json={"dx": 200, "dy": 0})
    pos = client.get("/api/digimon/亚古兽/position").json()
    # 文件岛 bounds=(0,0,960,600)
    assert pos["x"] == 960
    # 推到最左
    for _ in range(20):
        client.post("/api/digimon/亚古兽/move", json={"dx": -200, "dy": 0})
    pos = client.get("/api/digimon/亚古兽/position").json()
    assert pos["x"] == 0


def test_move_not_found(client: TestClient) -> None:
    r = client.post("/api/digimon/不存在兽/move", json={"dx": 1, "dy": 1})
    assert r.status_code == 404


def test_move_invalid_delta(client: TestClient) -> None:
    """超出 [-200, 200] 范围应被 pydantic 拒绝。"""
    r = client.post("/api/digimon/亚古兽/move", json={"dx": 999, "dy": 0})
    assert r.status_code == 422


def test_world_snapshot(client: TestClient) -> None:
    r = client.get("/api/world")
    assert r.status_code == 200
    data = r.json()
    assert "regions" in data
    assert "agents" in data
    # 文件岛 POI 应该在
    file_island = next(r for r in data["regions"] if r["id"] == "file_island")
    assert "evolution_shrine" in file_island["pois"]


def test_websocket_snapshot() -> None:
    """WS 端点应推送初始快照。"""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/world") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "snapshot"
            assert "world" in msg
            assert msg["world"]["agents"], "快照里应该有数码兽"


# ---- Phase 2: scheduler 接入 ----


def test_scheduler_starts_on_startup() -> None:
    """startup hook 应启动 scheduler task。"""
    # 用 context manager 形式的 TestClient 触发 startup/shutdown 事件
    with TestClient(app):
        task = getattr(app.state, "scheduler_task", None)
        assert task is not None
        assert not task.done()
        sched = getattr(app.state, "scheduler", None)
        assert sched is not None


def test_scheduler_status_endpoint() -> None:
    """GET /api/scheduler/status 返回 running / tick_count / current_world_time。"""
    with TestClient(app) as client:
        r = client.get("/api/scheduler/status")
        assert r.status_code == 200
        data = r.json()
        assert data["running"] is True
        assert isinstance(data["tick_count"], int)
        assert isinstance(data["current_world_time"], str)


def test_get_digimon_memories_endpoint(client: TestClient) -> None:
    """GET /api/digimon/{name}/memories 返回最近记忆(最多 10 条)。"""
    # 先给亚古兽塞一些记忆
    agent = get_world().get("亚古兽")
    assert agent is not None
    for i in range(15):
        agent.memory.add(f"记忆事件 {i}", importance=5)

    r = client.get("/api/digimon/亚古兽/memories")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "亚古兽"
    assert data["count"] == 10  # 只返回最近 10 条
    assert len(data["memories"]) == 10
    # 最后一条应是最新记忆
    assert data["memories"][-1]["description"] == "记忆事件 14"


def test_get_digimon_memories_not_found(client: TestClient) -> None:
    r = client.get("/api/digimon/不存在兽/memories")
    assert r.status_code == 404


# ---- Phase 4: 观察者/导演接口 ----


def test_director_inject_event(client: TestClient) -> None:
    """注入事件应 append 到 world.events 并返回序号。"""
    world = get_world()
    before = len(world.events)

    r = client.post("/api/director/inject_event", json={
        "type": "storm",
        "region_id": "file_island",
        "description": "文件岛突降暴风雨",
        "importance": 8,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == before  # 刚 append 的索引
    assert data["type"] == "storm"
    assert data["description"] == "文件岛突降暴风雨"

    # 事件确实进了列表
    assert len(world.events) == before + 1
    assert world.events[-1]["source"] == "director"


def test_director_speed(client: TestClient) -> None:
    """调整流速应返回旧/新 ratio 并写回 world_state。"""
    world = get_world()
    old = world.real_to_world_ratio

    r = client.post("/api/director/speed", json={"ratio": 120})
    assert r.status_code == 200
    data = r.json()
    assert data["old_ratio"] == old
    assert data["new_ratio"] == 120
    assert world.real_to_world_ratio == 120


def test_director_state(client: TestClient) -> None:
    """state 应返回流速 / 世界时间 / 最近事件。"""
    world = get_world()
    # 塞 12 条事件,验证只返回最近 10 条
    for i in range(12):
        world.events.append({"type": "test", "description": f"事件 {i}"})

    r = client.get("/api/director/state")
    assert r.status_code == 200
    data = r.json()
    assert data["ratio"] == world.real_to_world_ratio
    assert "current_world_time" in data
    assert len(data["recent_events"]) == 10
    assert data["recent_events"][-1]["description"] == "事件 11"


# ---- Phase 17: MBTI 人格档案 API ----
def test_personality_endpoint_returns_profile(client: TestClient) -> None:
    """GET /api/digimon/{name}/personality 返回 MBTI 人格档案。"""
    r = client.get("/api/digimon/亚古兽/personality")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_name"] == "亚古兽"
    assert "type_code" in data
    assert len(data["type_code"]) == 4  # e.g. "ENFP"
    assert "type_description" in data
    assert "ei" in data
    assert "sn" in data
    assert "tf" in data
    assert "jp" in data
    assert "strengths" in data
    assert "is_clear" in data
    assert "dominant_dimension" in data
    assert "history" in data
    assert "evolution_count" in data
    # 所有维度值在 [-1, 1] 范围内
    for dim in ("ei", "sn", "tf", "jp"):
        assert -1.0 <= data[dim] <= 1.0


def test_personality_endpoint_404(client: TestClient) -> None:
    """不存在的数码兽返回 404。"""
    r = client.get("/api/digimon/不存在的数码兽/personality")
    assert r.status_code == 404


def test_personality_endpoint_idempotent(client: TestClient) -> None:
    """同一数码兽多次请求返回同一档案 (get_or_create 语义)。"""
    r1 = client.get("/api/digimon/加布兽/personality")
    r2 = client.get("/api/digimon/加布兽/personality")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["type_code"] == r2.json()["type_code"]
    assert r1.json()["evolution_count"] == r2.json()["evolution_count"]

"""FastAPI app 测试: 验证 /api/digimon 列表 / 移动 / WebSocket。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world import __version__
from digimon_world.api import app
from digimon_world.world import reset_world


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

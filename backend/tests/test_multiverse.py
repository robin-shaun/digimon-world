"""Phase 9: 多元宇宙系统测试 (MultiverseManager + API)

测试内容:
- MultiverseManager: 创建/删除世界, 数码之门跨世界迁移, 序列化
- API: GET /api/multiverse, POST /api/multiverse/create, POST /api/multiverse/gate
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats
from digimon_world.world.multiverse import (
    PRIME_WORLD_ID,
    get_multiverse,
    reset_multiverse,
)
from digimon_world.world.world_state import get_world, reset_world


@pytest.fixture(autouse=True)
def _clean_multiverse():
    """每个测试前后重置多元宇宙和主世界,防止状态泄漏。"""
    reset_multiverse()
    reset_world()
    yield
    reset_multiverse()
    reset_world()


def _make_agent(name: str) -> DigimonAgent:
    """快速创建一个默认数码兽。"""
    return DigimonAgent(
        name=name,
        species=name,
        region_id="file_island",
        stats=DigimonStats(hp=100, ep=50, attack=20, defense=15, speed=15),
    )


# ========== MultiverseManager 单元测试 ==========


class TestMultiverseCreation:
    def test_prime_world_exists_by_default(self):
        mv = get_multiverse()
        assert mv.count() == 1
        assert PRIME_WORLD_ID in mv.worlds

    def test_create_world_auto_id(self):
        mv = get_multiverse()
        world = mv.create_world()
        assert mv.count() == 2
        assert mv.get_world("world_1") is world

    def test_create_world_explicit_id(self):
        mv = get_multiverse()
        world = mv.create_world(world_id="shadow_realm")
        assert mv.count() == 2
        assert mv.get_world("shadow_realm") is world

    def test_create_world_idempotent(self):
        mv = get_multiverse()
        w1 = mv.create_world(world_id="test")
        w2 = mv.create_world(world_id="test")
        assert w1 is w2
        assert mv.count() == 2  # prime + test, 不重复

    def test_all_world_ids(self):
        mv = get_multiverse()
        mv.create_world("world_a")
        mv.create_world("world_b")
        ids = mv.all_world_ids()
        assert PRIME_WORLD_ID in ids
        assert "world_a" in ids
        assert "world_b" in ids

    def test_remove_world(self):
        mv = get_multiverse()
        mv.create_world("temp")
        assert mv.count() == 2
        assert mv.remove_world("temp") is True
        assert mv.count() == 1
        assert mv.get_world("temp") is None

    def test_cannot_remove_prime(self):
        mv = get_multiverse()
        assert mv.remove_world(PRIME_WORLD_ID) is False
        assert mv.count() == 1


class TestDigitalGate:
    def test_open_gate_basic(self):
        mv = get_multiverse()
        mv.create_world("destination")

        prime = mv.get_world(PRIME_WORLD_ID)
        assert prime is not None
        agumon = _make_agent("亚古兽")
        prime.spawn(agumon)

        result = mv.open_gate("亚古兽", PRIME_WORLD_ID, "destination")
        assert result is not None
        assert result.name == "亚古兽"
        # 源世界不再有
        assert prime.get("亚古兽") is None
        # 目标世界有
        dest = mv.get_world("destination")
        assert dest is not None
        assert dest.get("亚古兽") is not None
        # 两边都有事件
        assert any(
            e["type"] == "digital_gate" and e["direction"] == "depart"
            for e in prime.events
        )
        assert any(
            e["type"] == "digital_gate" and e["direction"] == "arrive"
            for e in dest.events
        )

    def test_open_gate_same_world_returns_none(self):
        mv = get_multiverse()
        prime = mv.get_world(PRIME_WORLD_ID)
        assert prime is not None
        agumon = _make_agent("亚古兽")
        prime.spawn(agumon)

        assert mv.open_gate("亚古兽", PRIME_WORLD_ID, PRIME_WORLD_ID) is None
        assert prime.get("亚古兽") is not None

    def test_open_gate_agent_not_found_returns_none(self):
        mv = get_multiverse()
        mv.create_world("dest")
        assert mv.open_gate("不存在的兽", PRIME_WORLD_ID, "dest") is None

    def test_open_gate_world_not_found_returns_none(self):
        mv = get_multiverse()
        assert mv.open_gate("任何兽", PRIME_WORLD_ID, "ghost_world") is None

    def test_open_gate_transfers_memories(self):
        """数码之门迁移时,数码兽的记忆也随本体一起迁移。"""
        mv = get_multiverse()
        mv.create_world("dest")
        prime = mv.get_world(PRIME_WORLD_ID)
        assert prime is not None
        agumon = _make_agent("亚古兽")
        agumon.observe({"type": "exploration", "description": "在文件岛探索"})
        agumon.observe({"type": "battle", "description": "与加布兽战斗"})
        mem_before = len(agumon.memory.entries)
        prime.spawn(agumon)

        mv.open_gate("亚古兽", PRIME_WORLD_ID, "dest")
        dest = mv.get_world("dest")
        assert dest is not None
        migrated = dest.get("亚古兽")
        assert migrated is not None
        assert len(migrated.memory.entries) == mem_before


class TestToDict:
    def test_to_dict(self):
        mv = get_multiverse()
        mv.create_world("world_a")
        prime = mv.get_world(PRIME_WORLD_ID)
        assert prime is not None
        # prime 默认已有初始化数码兽(8+只), 再加一只测试用
        existing_before = prime.count()
        prime.spawn(_make_agent("test_agent_x"))
        d = mv.to_dict()
        assert d["count"] == 2
        assert len(d["worlds"]) == 2
        prime_info = next(w for w in d["worlds"] if w["world_id"] == PRIME_WORLD_ID)
        assert prime_info["agent_count"] == existing_before + 1
        wa_info = next(w for w in d["worlds"] if w["world_id"] == "world_a")
        assert wa_info["agent_count"] == 0


# ========== API 集成测试 ==========


class TestMultiverseAPI:
    @pytest.fixture
    def client(self):
        """返回 TestClient (延迟导入 app)。"""
        from digimon_world.api.app import app

        return TestClient(app)

    def test_get_multiverse(self, client):
        resp = client.get("/api/multiverse")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["worlds"][0]["world_id"] == PRIME_WORLD_ID

    def test_create_world_api(self, client):
        resp = client.post("/api/multiverse/create", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "world_1"
        assert data["total_worlds"] == 2

        # 验证多元宇宙概览更新
        resp2 = client.get("/api/multiverse")
        assert resp2.json()["count"] == 2

    def test_create_world_api_with_id(self, client):
        resp = client.post(
            "/api/multiverse/create", json={"world_id": "dark_world"}
        )
        assert resp.status_code == 200
        assert resp.json()["world_id"] == "dark_world"

    def test_open_gate_api(self, client):
        # 先创建目标世界
        client.post("/api/multiverse/create", json={"world_id": "dest"})
        # 主世界注入一只数码兽
        mv = get_multiverse()
        prime = mv.get_world(PRIME_WORLD_ID)
        assert prime is not None
        prime.spawn(_make_agent("哥玛兽"))

        resp = client.post(
            "/api/multiverse/gate",
            json={
                "agent_name": "哥玛兽",
                "from_world": PRIME_WORLD_ID,
                "to_world": "dest",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "哥玛兽"
        assert "数码之门" in data["message"]
        assert prime.get("哥玛兽") is None

    def test_open_gate_api_failure(self, client):
        resp = client.post(
            "/api/multiverse/gate",
            json={
                "agent_name": "不存在的兽",
                "from_world": PRIME_WORLD_ID,
                "to_world": "ghost",
            },
        )
        assert resp.status_code == 400
        assert "Gate failed" in resp.json()["detail"]


class TestSeasonsEnabled:
    def test_world_state_defaults_seasons_enabled(self):
        """新创建的 WorldState 默认启用季节系统。"""
        from digimon_world.world.world_state import WorldState
        ws = WorldState()
        assert ws.seasons_enabled is True

    def test_world_state_seasons_disabled(self):
        """可以显式关闭季节系统。"""
        from digimon_world.world.world_state import WorldState
        ws = WorldState(seasons_enabled=False)
        assert ws.seasons_enabled is False

    def test_to_dict_includes_seasons(self):
        """to_dict 包含 seasons_enabled 字段。"""
        from digimon_world.world.world_state import WorldState
        ws = WorldState(seasons_enabled=False)
        d = ws.to_dict()
        assert d["seasons_enabled"] is False


class TestMultiverseCreateSeasons:
    def test_create_world_seasons_disabled(self):
        """create_world 可以传递 seasons_enabled=False。"""
        mv = get_multiverse()
        mv.create_world(world_id="no_seasons", seasons_enabled=False)
        world = mv.get_world("no_seasons")
        assert world is not None
        assert world.seasons_enabled is False

    def test_create_api_seasons_disabled(self):
        """POST /api/multiverse/create 支持 seasons 参数。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post(
            "/api/multiverse/create",
            json={"world_id": "eternal_spring", "seasons": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "eternal_spring"
        assert data["seasons_enabled"] is False
        # 验证后端实际状态
        world = get_multiverse().get_world("eternal_spring")
        assert world is not None
        assert world.seasons_enabled is False


class TestGetWorldDetail:
    def test_get_prime_world(self):
        """GET /api/multiverse/prime 返回主世界详情。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/prime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "prime"
        assert data["seasons_enabled"] is True
        assert "agent_names" in data
        assert "recent_events" in data
        assert data["region_count"] > 0

    def test_get_nonexistent_world(self):
        """GET /api/multiverse/{id} 对不存在的世界返回 404。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/ghost_world")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_get_created_world(self):
        """GET /api/multiverse/{id} 可以查询新创建的世界。"""
        mv = get_multiverse()
        mv.create_world(world_id="target", seasons_enabled=False)
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/target")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "target"
        assert data["seasons_enabled"] is False
        assert data["agent_count"] == 0
        assert data["event_count"] == 0

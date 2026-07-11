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


class TestWorldStateId:
    """测试 WorldState.world_id 字段(Phase 9 新增)。"""

    def test_world_id_is_set_by_multiverse(self):
        """通过 MultiverseManager 创建的世界,world_id 正确设置。"""
        mv = get_multiverse()
        # prime 世界
        prime = mv.get_world("prime")
        assert prime is not None
        assert prime.world_id == "prime"
        # 新建世界
        mv.create_world(world_id="test_id")
        w = mv.get_world("test_id")
        assert w is not None
        assert w.world_id == "test_id"

    def test_auto_generated_world_id(self):
        """自动生成 world_id 时也正确设置。"""
        mv = get_multiverse()
        w = mv.create_world()
        assert w.world_id == "world_1"

    def test_world_id_in_to_dict(self):
        """WorldState.to_dict() 包含 world_id。"""
        mv = get_multiverse()
        w = mv.create_world(world_id="dict_test")
        d = w.to_dict()
        assert d["world_id"] == "dict_test"

    def test_direct_construction_world_id_none(self):
        """直接构造 WorldState 时 world_id 默认为 None。"""
        from digimon_world.world.world_state import WorldState
        ws = WorldState()
        assert ws.world_id is None


class TestSeedAgents:
    """测试 seed_agents 参数(Phase 9 新增)。"""

    def test_seed_agents_false_default(self):
        """默认 seed_agents=False,新世界为空。"""
        mv = get_multiverse()
        w = mv.create_world(world_id="empty_world", seed_agents=False)
        assert w.count() == 0

    def test_seed_agents_true(self):
        """seed_agents=True 注入 10 只默认数码兽。"""
        mv = get_multiverse()
        w = mv.create_world(world_id="seeded_world", seed_agents=True)
        assert w.count() == 10
        # 验证包含关键数码兽
        assert w.get("亚古兽") is not None
        assert w.get("加布兽") is not None
        assert w.get("迪路兽") is not None

    def test_seed_agents_api(self):
        """POST /api/multiverse/create 支持 seed_digimon 参数。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post(
            "/api/multiverse/create",
            json={"world_id": "seeded_api", "seed_digimon": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "seeded_api"
        assert data["agent_count"] == 10
        # 后端验证
        w = get_multiverse().get_world("seeded_api")
        assert w is not None
        assert w.count() == 10
        assert w.get("亚古兽") is not None


# ========== Phase 9: 世界删除 & 事件查询 API ==========


class TestDeleteWorldAPI:
    def test_delete_world(self):
        """DELETE /api/multiverse/{id} 删除一个非主世界。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        # 先创建一个世界
        client.post("/api/multiverse/create", json={"world_id": "to_delete"})
        assert get_multiverse().count() == 2

        resp = client.delete("/api/multiverse/to_delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "to_delete"
        assert data["deleted"] is True
        assert data["total_worlds"] == 1
        assert get_multiverse().get_world("to_delete") is None

    def test_delete_nonexistent_world(self):
        """DELETE 不存在的世界返回 404。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.delete("/api/multiverse/ghost")
        assert resp.status_code == 404

    def test_cannot_delete_prime(self):
        """DELETE prime 世界返回 400。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.delete("/api/multiverse/prime")
        assert resp.status_code == 400
        assert "prime" in resp.json()["detail"].lower()
        # prime 世界仍然存在
        assert get_multiverse().count() == 1

    def test_delete_world_removes_agents(self):
        """删除世界后其数码兽不复存在。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={
            "world_id": "populated", "seed_digimon": True,
        })
        w = get_multiverse().get_world("populated")
        assert w is not None and w.count() == 10

        client.delete("/api/multiverse/populated")
        assert get_multiverse().get_world("populated") is None

    def test_delete_then_recreate(self):
        """删除世界后可重新创建同名世界。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "recycled"})
        client.delete("/api/multiverse/recycled")
        # 重新创建
        resp = client.post("/api/multiverse/create", json={"world_id": "recycled"})
        assert resp.status_code == 200
        assert get_multiverse().get_world("recycled") is not None


class TestWorldEventsAPI:
    def test_get_prime_events(self):
        """GET /api/multiverse/prime/events 返回主世界事件。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/prime/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "prime"
        assert "events" in data
        assert "total" in data
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_get_world_events_empty(self):
        """新创建的空世界事件列表为空。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "empty_events"})
        resp = client.get("/api/multiverse/empty_events/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["events"] == []

    def test_get_world_events_not_found(self):
        """GET 不存在世界的事件返回 404。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/ghost/events")
        assert resp.status_code == 404

    def test_get_world_events_reversed_order(self):
        """事件按时间倒序(最新在前)。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "ordered"})
        # 手动注入事件到世界
        w = get_multiverse().get_world("ordered")
        assert w is not None
        w.events.append({"type": "test", "msg": "first"})
        w.events.append({"type": "test", "msg": "second"})
        w.events.append({"type": "test", "msg": "third"})

        resp = client.get("/api/multiverse/ordered/events", params={"limit": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        events = data["events"]
        # 最新在前: third → second → first
        assert events[0]["msg"] == "third"
        assert events[1]["msg"] == "second"
        assert events[2]["msg"] == "first"

    def test_get_world_events_pagination(self):
        """事件分页: limit + offset 正确工作。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "paged"})
        w = get_multiverse().get_world("paged")
        assert w is not None
        for i in range(5):
            w.events.append({"type": "test", "idx": i})

        # limit=2, offset=1 -> 应返回 idx=3, idx=2 (最新 5 条: 4,3,2,1,0, skip 1 -> 3,2)
        resp = client.get(
            "/api/multiverse/paged/events",
            params={"limit": 2, "offset": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert data["total"] == 5
        events = data["events"]
        assert len(events) == 2
        assert events[0]["idx"] == 3
        assert events[1]["idx"] == 2


# ========== Phase 9: Seed World API ==========


class TestSeedWorldAPI:
    def test_seed_empty_world(self):
        """POST /api/multiverse/{id}/seed 注入 10 只默认数码兽到空世界。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "empty"})
        w = get_multiverse().get_world("empty")
        assert w is not None and w.count() == 0

        resp = client.post("/api/multiverse/empty/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "empty"
        assert data["added"] == 10
        assert data["total_agents"] == 10
        assert w.get("亚古兽") is not None
        assert w.get("迪路兽") is not None

    def test_seed_existing_world_appends(self):
        """seed 对已有同名数码兽的世界会覆盖(spawn 是 upsert),不加新。

        要测试追加,先注入非默认名的数码兽,seed 不会覆盖它们。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats
        client = TestClient(app)
        client.post("/api/multiverse/create", json={
            "world_id": "has_custom", "seed_digimon": True,
        })
        w = get_multiverse().get_world("has_custom")
        assert w is not None and w.count() == 10

        # spawn 一只自定义名的数码兽(不会被 seed 覆盖)
        custom = DigimonAgent(
            name="吸血鬼兽",
            species="vamdemon",
            region_id="infinity_mountain",
            stats=DigimonStats(hp=100, ep=50, attack=20, defense=15, speed=15),
        )
        w.spawn(custom)
        assert w.count() == 11

        # seed: 默认 10 只会覆盖同名,自定义的不受影响,净增可能为 0
        resp = client.post("/api/multiverse/has_custom/seed")
        assert resp.status_code == 200
        data = resp.json()
        # spawn 是 upsert: 10 只默认兽覆盖同名(净增 0),自定义的不受影响
        assert data["added"] >= 0
        assert data["total_agents"] == 11  # 10 覆盖 + 1 自定义

    def test_seed_nonexistent_world(self):
        """seed 不存在的世界返回 404。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/api/multiverse/ghost/seed")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_seed_prime_world(self):
        """seed 主宇宙也允许,但 spawn 是 upsert(同名覆盖,净增可能为 0)。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        w = get_multiverse().get_world("prime")
        assert w is not None
        before = w.count()

        resp = client.post("/api/multiverse/prime/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "prime"
        # spawn 是 upsert,已有同名兽则净增可能为 0
        assert data["added"] >= 0
        assert data["total_agents"] >= before


# ========== Phase 9: 聚合统计 API ==========


class TestMultiverseStats:
    def test_stats_single_world(self):
        """只有一个 prime 世界时的统计。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_count"] == 1
        assert len(data["worlds"]) == 1
        assert data["worlds"][0]["world_id"] == "prime"
        assert data["worlds"][0]["agent_count"] > 0
        assert data["worlds"][0]["region_count"] > 0
        assert data["total_agents"] == data["worlds"][0]["agent_count"]
        assert data["total_events"] == data["worlds"][0]["event_count"]

    def test_stats_multiple_worlds(self):
        """多个世界时聚合统计正确。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        # 创建两个世界: 一个空,一个有种子
        client.post("/api/multiverse/create", json={"world_id": "empty"})
        client.post(
            "/api/multiverse/create",
            json={"world_id": "seeded", "seed_digimon": True},
        )

        resp = client.get("/api/multiverse/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_count"] == 3  # prime + empty + seeded
        assert len(data["worlds"]) == 3

        # 验证各世界数据
        world_map = {w["world_id"]: w for w in data["worlds"]}
        assert world_map["prime"]["agent_count"] > 0
        assert world_map["empty"]["agent_count"] == 0
        assert world_map["seeded"]["agent_count"] == 10

        # 聚合值
        assert data["total_agents"] == sum(
            w["agent_count"] for w in data["worlds"]
        )
        assert data["total_events"] == sum(
            w["event_count"] for w in data["worlds"]
        )

    def test_stats_after_delete(self):
        """删除世界后聚合统计更新。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "temp"})

        before = client.get("/api/multiverse/stats").json()
        assert before["world_count"] == 2

        client.delete("/api/multiverse/temp")

        after = client.get("/api/multiverse/stats").json()
        assert after["world_count"] == 1

    def test_stats_after_gate(self):
        """跨世界迁移后聚合统计更新(total_agents 不变)。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "dest"})

        # 主世界注入一只独特的数码兽
        from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats
        mv = get_multiverse()
        prime = mv.get_world("prime")
        assert prime is not None
        before_count = prime.count()
        custom = DigimonAgent(
            name="测试兽",
            species="testmon",
            region_id="file_island",
            stats=DigimonStats(hp=100, ep=50, attack=20, defense=15, speed=15),
        )
        prime.spawn(custom)

        before = client.get("/api/multiverse/stats").json()

        # 通过数码之门迁移
        client.post("/api/multiverse/gate", json={
            "agent_name": "测试兽",
            "from_world": "prime",
            "to_world": "dest",
        })

        after = client.get("/api/multiverse/stats").json()
        # total_agents 不变(只是从一个世界移到另一个)
        assert after["total_agents"] == before["total_agents"]
        # total_events 增加(两边各一条 gate 事件)
        assert after["total_events"] == before["total_events"] + 2
        # prime 减少 1, dest 增加 1
        after_map = {w["world_id"]: w for w in after["worlds"]}
        before_map = {w["world_id"]: w for w in before["worlds"]}
        assert after_map["prime"]["agent_count"] == before_map["prime"]["agent_count"] - 1
        assert after_map["dest"]["agent_count"] == before_map["dest"]["agent_count"] + 1

    def test_stats_includes_region_count(self):
        """stats 响应中每个世界包含 region_count。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/stats")
        assert resp.status_code == 200
        data = resp.json()
        for w in data["worlds"]:
            assert "region_count" in w
            assert w["region_count"] > 0  # 默认至少有 file_island 和 infinity_mountain


# ========== Phase 9: List World Digimon API ==========


class TestListWorldDigimon:
    def test_list_prime_digimon(self):
        """GET /api/multiverse/prime/digimon 返回主世界所有数码兽。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/prime/digimon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "prime"
        assert data["count"] > 0
        assert len(data["digimon"]) == data["count"]
        # 验证字段完整性
        d = data["digimon"][0]
        assert "name" in d
        assert "species" in d
        assert "stage" in d
        assert "attribute" in d
        assert "region_id" in d
        assert "position" in d
        assert "current_plan" in d
        assert "mood" in d

    def test_list_digimon_in_seeded_world(self):
        """GET /api/multiverse/{id}/digimon 返回种子世界数码兽列表。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post(
            "/api/multiverse/create",
            json={"world_id": "with_digis", "seed_digimon": True},
        )
        resp = client.get("/api/multiverse/with_digis/digimon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world_id"] == "with_digis"
        assert data["count"] == 10
        names = [d["name"] for d in data["digimon"]]
        assert "亚古兽" in names
        assert "迪路兽" in names

    def test_list_digimon_empty_world(self):
        """GET /api/multiverse/{id}/digimon 对空世界返回 count=0。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/api/multiverse/create", json={"world_id": "empty_w"})
        resp = client.get("/api/multiverse/empty_w/digimon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["digimon"] == []

    def test_list_digimon_nonexistent_world(self):
        """GET /api/multiverse/{id}/digimon 对不存在的世界返回 404。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/multiverse/ghost/digimon")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_list_digimon_after_gate(self):
        """数码之门迁移后,源世界和目标世界的数码兽列表正确更新。"""
        from digimon_world.api.app import app
        from fastapi.testclient import TestClient
        from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats
        client = TestClient(app)
        # 目标世界(空)
        client.post("/api/multiverse/create", json={
            "world_id": "after_gate_dest", "seed_digimon": False,
        })
        # 主世界注入一只独特数码兽
        mv = get_multiverse()
        prime = mv.get_world("prime")
        assert prime is not None
        custom = DigimonAgent(
            name="测试兽X",
            species="testmon",
            region_id="file_island",
            stats=DigimonStats(hp=100, ep=50, attack=20, defense=15, speed=15),
        )
        prime.spawn(custom)

        # 迁移前: prime 有测试兽X, dest 空
        r1 = client.get("/api/multiverse/prime/digimon")
        r2 = client.get("/api/multiverse/after_gate_dest/digimon")
        assert any(d["name"] == "测试兽X" for d in r1.json()["digimon"])
        assert r2.json()["count"] == 0

        # 执行数码之门
        client.post("/api/multiverse/gate", json={
            "agent_name": "测试兽X",
            "from_world": "prime",
            "to_world": "after_gate_dest",
        })

        # 迁移后: prime 不再有, dest 有
        r3 = client.get("/api/multiverse/prime/digimon")
        r4 = client.get("/api/multiverse/after_gate_dest/digimon")
        assert not any(d["name"] == "测试兽X" for d in r3.json()["digimon"])
        assert any(d["name"] == "测试兽X" for d in r4.json()["digimon"])

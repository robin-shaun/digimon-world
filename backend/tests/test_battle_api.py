"""
战斗 API 测试
=============

覆盖:
- POST /api/battle/start — 正常战斗 / 404 / 同名自打 / 赢家 +1 victory
- 战斗写入 world.events (type=battle)
- 战斗加入 _BATTLE_HISTORY
- GET /api/battle/recent — 默认 limit / 自定义 limit
- GET /api/digimon/{name}/battle_victories
- BattleEngine → EvolutionSystem 链路(赢家胜利 + bond → 进化)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world import __version__  # noqa: F401  (sanity import)
from digimon_world.api import app as fastapi_app  # FastAPI instance
from digimon_world.world import get_world, reset_world


@pytest.fixture(autouse=True)
def _reset():
    """每个测试前重置世界单例 + 清空战斗历史。

    _BATTLE_HISTORY 是定义在 digimon_world.api.app 模块的全局变量,
    但 digimon_world.api 包通过 __init__.py 把 FastAPI 实例暴露成 app,
    所以这里需要 sys.modules 直接拿到模块对象。
    """
    reset_world()
    import sys
    api_app_module = sys.modules["digimon_world.api.app"]
    if hasattr(api_app_module, "_BATTLE_HISTORY"):
        api_app_module._BATTLE_HISTORY.clear()
    yield
    reset_world()
    if hasattr(api_app_module, "_BATTLE_HISTORY"):
        api_app_module._BATTLE_HISTORY.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


# ---------- POST /api/battle/start ----------


class TestStartBattle:
    def test_battle_returns_winner(self, client: TestClient) -> None:
        """亚古兽 vs 加布兽,必有一个胜者。"""
        r = client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "加布兽"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["result"]["winner"] in {"亚古兽", "加布兽"}
        assert data["result"]["rounds"] >= 1
        assert data["event_id"] >= 0

    def test_battle_increments_winner_victories(self, client: TestClient) -> None:
        """战斗后赢家 battle_victories = 1。"""
        r = client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "加布兽"},
        )
        winner = r.json()["result"]["winner"]
        assert winner is not None
        # 查询胜利次数
        r2 = client.get(f"/api/digimon/{winner}/battle_victories")
        assert r2.status_code == 200
        assert r2.json()["battle_victories"] == 1

    def test_battle_appends_world_event(self, client: TestClient) -> None:
        """战斗会在 world.events 末尾追加 type=battle 的事件。"""
        before = len(get_world().events)
        client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "比丘兽"},
        )
        events = get_world().events
        assert len(events) == before + 1
        last = events[-1]
        assert last["type"] == "battle"
        assert last["attacker"] == "亚古兽"
        assert last["defender"] == "比丘兽"
        assert "at" in last

    def test_battle_attacker_not_found(self, client: TestClient) -> None:
        r = client.post(
            "/api/battle/start",
            json={"attacker": "不存在兽", "defender": "加布兽"},
        )
        assert r.status_code == 404

    def test_battle_defender_not_found(self, client: TestClient) -> None:
        r = client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "不存在兽"},
        )
        assert r.status_code == 404

    def test_battle_self_returns_400(self, client: TestClient) -> None:
        """同一只数码兽不能打自己。"""
        r = client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "亚古兽"},
        )
        assert r.status_code == 400

    def test_battle_with_use_llm_runs(self, client: TestClient) -> None:
        """use_llm=true 时调用 LLM 决策,战斗仍跑通。"""
        r = client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "加布兽", "use_llm": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["result"]["winner"] in {"亚古兽", "加布兽"}


# ---------- GET /api/battle/recent ----------


class TestRecentBattles:
    def test_recent_empty(self, client: TestClient) -> None:
        r = client.get("/api/battle/recent")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["battles"] == []

    def test_recent_after_fight(self, client: TestClient) -> None:
        client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "加布兽"},
        )
        r = client.get("/api/battle/recent")
        data = r.json()
        assert data["count"] == 1
        b = data["battles"][0]
        assert b["attacker"] == "亚古兽"
        assert b["defender"] == "加布兽"
        assert "at" in b

    def test_recent_limit_param(self, client: TestClient) -> None:
        """limit 参数控制返回多少条。"""
        for _ in range(3):
            client.post(
                "/api/battle/start",
                json={"attacker": "亚古兽", "defender": "加布兽"},
            )
        r = client.get("/api/battle/recent?limit=2")
        data = r.json()
        assert data["count"] == 3
        assert len(data["battles"]) == 2


# ---------- GET /api/digimon/{name}/battle_victories ----------


class TestBattleVictoriesEndpoint:
    def test_initial_victories_zero(self, client: TestClient) -> None:
        r = client.get("/api/digimon/亚古兽/battle_victories")
        assert r.status_code == 200
        assert r.json()["battle_victories"] == 0

    def test_victories_after_battle(self, client: TestClient) -> None:
        # 打 2 场(可能同一个人赢)
        client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "加布兽"},
        )
        client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "比丘兽"},
        )
        r = client.get("/api/digimon/亚古兽/battle_victories")
        n = r.json()["battle_victories"]
        # 0 ≤ n ≤ 2
        assert 0 <= n <= 2

    def test_victories_not_found(self, client: TestClient) -> None:
        r = client.get("/api/digimon/不存在兽/battle_victories")
        assert r.status_code == 404


# ---------- 战斗 → 进化 链路 ----------


class TestBattleTriggersEvolution:
    """赢家胜利数累计 + bond 累加 → EvolutionSystem 触发进化。"""

    def test_high_victories_triggers_evolution(self, client: TestClient) -> None:
        """预先给亚古兽塞 8 次胜利 + bond,再开一场战斗验证进化被触发。"""
        world = get_world()
        agumon = world.get("亚古兽")
        assert agumon is not None
        # 直接伪造历史胜利(模拟 8 场战斗已打完)
        agumon.battle_victories = 7
        # 加足够的 bond: 喂 14 条 importance=3 的记忆 → bond=42
        for i in range(14):
            agumon.observe({"type": "ate", "detail": f"meal_{i}"})
        assert agumon.stats.attack > 0  # sanity

        # 现在开第 8 场战斗(必胜,攻击 30 防 5)
        from digimon_world.agents.digimon_agent import DigimonStats
        gabumon = world.get("加布兽")
        assert gabumon is not None
        # 把亚古兽调到必胜状态
        agumon.stats = DigimonStats(
            hp=999, max_hp=999, attack=999, defense=999, speed=999
        )
        gabumon.stats = DigimonStats(
            hp=10, max_hp=10, attack=1, defense=1, speed=1
        )

        r = client.post(
            "/api/battle/start",
            json={"attacker": "亚古兽", "defender": "加布兽"},
        )
        assert r.status_code == 200
        data = r.json()
        # 战斗结果:亚古兽赢
        assert data["result"]["winner"] == "亚古兽"
        # 现在 8 场胜利 + 40+ bond → 应该触发进化
        assert data["evolution"] is not None
        assert data["evolution"]["evolved"] is True
        assert data["evolution"]["new_stage"] == "champion"
        # 进化后阶段真的改了
        r2 = client.get("/api/digimon/亚古兽")
        assert r2.json()["stage"] == "champion"

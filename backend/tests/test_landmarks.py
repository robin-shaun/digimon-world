"""
LandmarkSystem 单元测试 + /api/landmarks 集成测试
==================================================

覆盖:
- 邻近检测: <50px 触发, >=50px 不触发
- 进化神殿羁绊 +5/tick(封顶 100)
- 启程海滩心情提升 / 奥加兽商店随机道具 / 创世者祭坛究极进化
- GET /api/landmarks 返回各地标状态

运行: cd backend && source .venv/bin/activate && pytest tests/test_landmarks.py -v
"""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats, EvolutionStage
from digimon_world.api.app import app
from digimon_world.world.landmarks import (
    MEGA_EVOLUTION_CHANCE,
    LandmarkEffect,
    LandmarkSystem,
)
from digimon_world.world.world_state import WorldState, reset_world


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_world()
    yield
    reset_world()


def _agent(name: str, x: int, y: int, region: str = "file_island", **kw) -> DigimonAgent:
    return DigimonAgent(
        name=name,
        species=name,
        stage=kw.pop("stage", EvolutionStage.ROOKIE),
        region_id=region,
        location=(x, y),
        stats=DigimonStats(),
        **kw,
    )


def test_evolution_shrine_bond_boost_and_radius() -> None:
    """靠近进化神殿(<50px)羁绊 +5;远离(>=50px)不触发。"""
    system = LandmarkSystem()

    # 神殿在 (470, 230)。放一只紧挨着的
    near = _agent("Near", 470, 230)
    effects = system.apply_effects(near)
    assert len(effects) == 1
    assert effects[0]["effect"] == LandmarkEffect.BOND_BOOST.value
    assert near.stats.bond == 5

    # 再来一 tick,累加到 10
    system.apply_effects(near)
    assert near.stats.bond == 10

    # 远离的(距离 > 50)不触发
    far = _agent("Far", 470, 300)  # dy=70 > 50
    assert system.apply_effects(far) == []
    assert far.stats.bond == 0


def test_bond_boost_caps_at_100() -> None:
    """羁绊封顶 100,不会溢出。"""
    system = LandmarkSystem()
    a = _agent("Capped", 470, 230)
    a.stats.bond = 98
    effects = system.apply_effects(a)
    assert a.stats.bond == 100
    assert effects[0]["amount"] == 2  # 只涨了 2 就封顶


def test_beach_mood_boost() -> None:
    """靠近启程海滩(173, 468)心情提升为 excited。"""
    system = LandmarkSystem()
    a = _agent("Beachgoer", 173, 468)
    a.mood = "tired"
    effects = system.apply_effects(a)
    assert len(effects) == 1
    assert effects[0]["effect"] == LandmarkEffect.MOOD_BOOST.value
    assert a.mood == "excited"


def test_ogremon_shop_grants_item() -> None:
    """靠近奥加兽商店(745, 480)随机获得一件道具。"""
    system = LandmarkSystem()
    a = _agent("Shopper", 745, 480)
    rng = random.Random(42)  # 固定种子,可复现
    effects = system.apply_effects(a, rng=rng)
    assert len(effects) == 1
    assert effects[0]["effect"] == LandmarkEffect.RANDOM_ITEM.value
    item = effects[0]["item"]
    assert item  # 拿到了道具
    assert system.granted_items["Shopper"] == [item]


def test_creators_altar_mega_evolution() -> None:
    """创世者祭坛(480, 120, infinity_mountain)极低概率触发究极进化。

    用一个必中的 rng(random() 恒返回 0 < 概率阈值)验证进化逻辑。
    """
    system = LandmarkSystem()
    a = _agent("Chosen", 480, 120, region="infinity_mountain")
    assert a.stage is EvolutionStage.ROOKIE

    class _AlwaysHit(random.Random):
        def random(self) -> float:  # type: ignore[override]
            return 0.0  # 0 < MEGA_EVOLUTION_CHANCE → 必触发

    effects = system.apply_effects(a, rng=_AlwaysHit())
    assert len(effects) == 1
    assert effects[0]["effect"] == LandmarkEffect.MEGA_EVOLUTION.value
    assert a.stage is EvolutionStage.MEGA

    # 已是 MEGA,再靠近不重复触发
    assert system.apply_effects(a, rng=_AlwaysHit()) == []


def test_mega_evolution_miss_does_nothing() -> None:
    """祭坛未中概率(random() >= 阈值)时不进化,无效果事件。"""
    system = LandmarkSystem()
    a = _agent("Unlucky", 480, 120, region="infinity_mountain")

    class _AlwaysMiss(random.Random):
        def random(self) -> float:  # type: ignore[override]
            return 1.0  # >= 阈值 → 不触发

    assert system.apply_effects(a, rng=_AlwaysMiss()) == []
    assert a.stage is EvolutionStage.ROOKIE
    assert MEGA_EVOLUTION_CHANCE < 1.0  # 概率确实是"极低"


def test_region_isolation() -> None:
    """地标只对同 region 的数码兽生效: 祭坛在 infinity_mountain,
    坐标相同但 region 不同的数码兽不触发。"""
    system = LandmarkSystem()
    # 坐标落在祭坛(480,120)上,但 region 是 file_island(祭坛不在这)
    a = _agent("WrongRegion", 480, 120, region="file_island")
    effects = system.apply_effects(a)
    # file_island 里 (480,120) 附近没有地标 → 无效果
    assert effects == []


def test_process_all_agents() -> None:
    """process(world) 遍历所有数码兽施加效果。"""
    world = WorldState()
    world.spawn(_agent("A", 470, 230))            # 进化神殿
    world.spawn(_agent("B", 173, 468))            # 启程海滩
    world.spawn(_agent("C", 0, 0))                # 荒地,无地标
    system = LandmarkSystem()
    effects = system.process(world)
    agents_hit = {e["agent"] for e in effects}
    assert agents_hit == {"A", "B"}


def test_api_landmarks_endpoint() -> None:
    """GET /api/landmarks 返回全部地标 + 附近数码兽。"""
    client = TestClient(app)
    r = client.get("/api/landmarks")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 4
    assert data["trigger_radius"] == 50

    ids = {lm["id"] for lm in data["landmarks"]}
    assert ids == {
        "evolution_shrine",
        "beach_of_departure",
        "ogremon_shop",
        "creators_altar",
    }
    # 每个地标都带 nearby_digimon(因传入了 world)
    for lm in data["landmarks"]:
        assert "nearby_digimon" in lm
        assert isinstance(lm["nearby_digimon"], list)

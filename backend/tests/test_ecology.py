"""EcologySystem 单元测试。"""

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent
from digimon_world.world.ecology import (
    HUNGER_THRESHOLD,
    EcologySystem,
    reset_ecology_system,
)
from digimon_world.world.world_state import get_world, reset_world


@pytest.fixture
def fresh_ecology():
    return EcologySystem()


@pytest.fixture
def fresh_world():
    reset_world()
    w = get_world()
    yield w
    reset_world()


def test_ecology_default_food_levels():
    eco = EcologySystem()
    # 文件岛食物丰富
    assert eco.food_level("file_island") == 80
    # 无限山食物稀缺
    assert eco.food_level("infinity_mountain") == 40
    # 创始村适中
    assert eco.food_level("village_of_beginnings") == 60


def test_ecology_unknown_region_defaults():
    eco = EcologySystem()
    # 未知区域默认 50 食物
    assert eco.food_level("unknown_region") == 50


def test_ecology_food_level_getter_setter():
    eco = EcologySystem()
    eco._ensure_region("test_region")
    eco.regions["test_region"].food_level = 75
    assert eco.food_level("test_region") == 75


def test_ecology_is_hungry_agent(fresh_world):
    eco = EcologySystem()
    eco._ensure_region("file_island").food_level = 20  # 低于阈值

    agent = DigimonAgent(name="测试兽", species="test", region_id="file_island")
    fresh_world.spawn(agent)

    assert eco.is_hungry(agent)

    # 食物充足时不应饥饿
    eco._ensure_region("file_island").food_level = 80
    assert not eco.is_hungry(agent)


def test_ecology_vegetation_color():
    eco = EcologySystem()
    eco._ensure_region("file_island").vegetation = 80
    assert eco.vegetation_color("file_island") == "#2d6a4f"  # 深绿

    eco._ensure_region("file_island").vegetation = 10
    assert eco.vegetation_color("file_island") == "#6b4226"  # 深棕


def test_ecology_evolution_multiplier():
    eco = EcologySystem()
    # 无限山进化概率翻倍
    assert eco.evolution_multiplier("infinity_mountain") == 2.0
    # 文件岛标准
    assert eco.evolution_multiplier("file_island") == 1.0


def test_ecology_process_applies_hunger(fresh_world):
    eco = EcologySystem()

    agent = DigimonAgent(
        name="饥饿兽",
        species="test",
        region_id="file_island",
        location=(200, 400),
    )
    fresh_world.spawn(agent)

    # 设置低食物触发饥饿
    eco._ensure_region("file_island").food_level = 20

    events = eco.process(fresh_world, tick_count=1, season="spring")
    hunger_events = [e for e in events if e.get("type") == "hunger"]
    assert len(hunger_events) > 0


def test_ecology_process_regenerates_food(fresh_world):
    eco = EcologySystem()
    eco._ensure_region("file_island").food_level = 50

    eco.process(fresh_world, tick_count=1, season="spring")

    # 文件岛基础再生 2 + bonus 3 = 5/tick
    assert eco.food_level("file_island") == min(100, 50 + 5)


def test_ecology_drought_detection(fresh_world):
    eco = EcologySystem()
    # 食物极低(即使再生也达不到阈值),干旱持续 50+ tick
    eco._ensure_region("file_island").food_level = 5
    eco._ensure_region("file_island").drought_ticks = 50

    eco.process(fresh_world, tick_count=1, season="spring")

    assert eco.regions["file_island"].is_drought


def test_ecology_season_vegetation_effect():
    # 冬天植被下降
    from digimon_world.world.ecology import _season_vegetation_mult
    assert _season_vegetation_mult("winter") == 0.80
    assert _season_vegetation_mult("spring") == 1.05
    assert _season_vegetation_mult("autumn") == 0.95


def test_ecology_to_dict():
    eco = EcologySystem()
    d = eco.to_dict()
    assert "regions" in d
    assert "hunger_threshold" in d
    assert d["hunger_threshold"] == HUNGER_THRESHOLD


def test_reset_ecology_system():
    from digimon_world.world.ecology import get_ecology_system

    e1 = get_ecology_system()
    reset_ecology_system()
    e2 = get_ecology_system()
    assert e1 is not e2

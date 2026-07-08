"""
需求系统单元测试
================

覆盖:
- 每 tick hunger 衰减,夹紧到 [0, 100]
- hunger < 20 触发优先觅食,觅食计划提到最前
- 觅食成功 hunger +30 (夹紧 100),无食物地区觅食失败

运行: cd backend && source .venv/bin/activate && pytest tests/test_needs.py -v
"""

from __future__ import annotations

from digimon_world.agents.needs import (
    FORAGE_PLAN,
    FORAGE_RESTORE,
    FoodType,
    NeedsState,
    food_sources,
    forage,
    prioritized_plan,
    should_forage,
)


def test_tick_decays_hunger_and_clamps():
    """每 tick hunger-1,永远不低于 0。"""
    needs = NeedsState(hunger=100)
    for _ in range(5):
        needs.tick()
    assert needs.hunger == 95

    # 从接近 0 反复 tick 不会变负
    needs = NeedsState(hunger=2)
    for _ in range(10):
        needs.tick()
    assert needs.hunger == 0


def test_hungry_triggers_prioritized_foraging():
    """hunger < 20 时 should_forage=True,计划被觅食提到最前。"""
    hungry = NeedsState(hunger=15)
    assert should_forage(hungry) is True
    assert hungry.is_hungry() is True
    plan = prioritized_plan(hungry, "去进化神殿看看")
    assert plan.startswith(FORAGE_PLAN)
    assert "去进化神殿看看" in plan

    # 刚好在阈值 20 上时不算饿,保留原计划
    full = NeedsState(hunger=20)
    assert should_forage(full) is False
    assert prioritized_plan(full, "去进化神殿看看") == "去进化神殿看看"


def test_forage_restores_hunger_and_respects_region():
    """文件岛觅食成功 hunger+30 (夹紧 100);无食物地区觅食失败,hunger 不变。"""
    # 文件岛有 berries/fish/meat
    assert FoodType.BERRIES in food_sources("file_island")

    needs = NeedsState(hunger=15)
    got = forage(needs, "file_island")
    assert got is not None
    assert needs.hunger == 15 + FORAGE_RESTORE
    assert needs.last_food == got

    # 夹紧到 100
    high = NeedsState(hunger=90)
    forage(high, "file_island")
    assert high.hunger == 100

    # 未配置食物的地区: 觅食失败,hunger 不变
    starving = NeedsState(hunger=10)
    assert food_sources("digital_void") == []
    assert forage(starving, "digital_void") is None
    assert starving.hunger == 10

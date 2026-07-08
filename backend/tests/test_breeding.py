"""
繁衍系统单元测试
================

覆盖:
- 只挑出关系 > 80 的 pair,确定性排序
- 继承 stats = 父母平均 ±10%,满状态/bond 归零出生
- 到点 (每 500 tick) 才检查,概率产蛋,新生兽为 baby_i 阶段

运行: cd backend && source .venv/bin/activate && pytest tests/test_breeding.py -v
"""

from __future__ import annotations

import random

from digimon_world.agents.breeding import (
    BREEDING_INTERVAL_TICKS,
    BREEDING_THRESHOLD,
    STAT_VARIANCE,
    breed_egg,
    eligible_pairs,
    inherit_stats,
    is_breeding_tick,
    maybe_breed,
)
from digimon_world.agents.digimon_agent import (
    DigimonAgent,
    DigimonAttribute,
    DigimonStats,
    EvolutionStage,
)
from digimon_world.world.relationships import RelationshipTracker


def _agent(name: str, species: str = "Agumon", **stats) -> DigimonAgent:
    return DigimonAgent(
        name=name,
        species=species,
        stage=EvolutionStage.ROOKIE,
        attribute=DigimonAttribute.VACCINE,
        stats=DigimonStats(**stats),
    )


def test_eligible_pairs_only_above_threshold():
    """只有关系 > 80 的 pair 入选,结果按名字稳定排序。"""
    a, b, c = _agent("亚古兽"), _agent("加布兽"), _agent("巴达兽")
    tracker = RelationshipTracker()
    tracker.update("亚古兽", "加布兽", 85)   # 够亲密
    tracker.update("亚古兽", "巴达兽", 80)   # 刚好 80,不算 (需 > 80)
    tracker.update("加布兽", "巴达兽", 50)   # 太低

    pairs = eligible_pairs(tracker, [a, b, c])
    assert len(pairs) == 1
    lo, hi = pairs[0]
    assert (lo.name, hi.name) == ("亚古兽", "加布兽")
    assert lo.name <= hi.name  # 稳定排序


def test_inherit_stats_average_within_variance():
    """继承数值 = 父母平均 ±10%,bond 归零、满状态出生。"""
    pa = DigimonStats(max_hp=100, max_ep=50, attack=20, defense=10, speed=30, bond=90)
    pb = DigimonStats(max_hp=200, max_ep=150, attack=40, defense=30, speed=10, bond=40)
    rng = random.Random(42)

    child = inherit_stats(pa, pb, rng)

    # 每个继承字段都落在父母平均的 ±10% 内 (含取整误差)
    for name, avg in [
        ("attack", 30), ("defense", 20), ("speed", 20),
        ("max_hp", 150), ("max_ep", 100),
    ]:
        lo = round(avg * (1 - STAT_VARIANCE)) - 1
        hi = round(avg * (1 + STAT_VARIANCE)) + 1
        assert lo <= getattr(child, name) <= hi, name

    # 满状态出生,bond 归零,无技能
    assert child.hp == child.max_hp
    assert child.ep == child.max_ep
    assert child.bond == 0
    assert child.skills == []
    # 数值下限保护
    assert child.attack >= 1


def test_inherit_stats_deterministic_with_seed():
    """相同种子 → 完全可复现。"""
    pa = DigimonStats(attack=20, defense=10, speed=30)
    pb = DigimonStats(attack=40, defense=30, speed=10)
    c1 = inherit_stats(pa, pb, random.Random(7))
    c2 = inherit_stats(pa, pb, random.Random(7))
    assert c1.attack == c2.attack
    assert c1.defense == c2.defense
    assert c1.speed == c2.speed


def test_breed_egg_is_baby_i_next_to_parent():
    """产下的蛋是 baby_i 阶段,出生在父母身边,物种随父母之一。"""
    a = _agent("亚古兽", species="Agumon")
    b = _agent("加布兽", species="Gabumon")
    a.region_id = "file_island"
    a.location = (12, 34)

    egg = breed_egg(a, b, random.Random(1))
    assert egg.stage == EvolutionStage.BABY_I
    assert egg.region_id == "file_island"
    assert egg.location == (12, 34)
    assert egg.species in {"Agumon", "Gabumon"}
    assert egg.attribute in {a.attribute, b.attribute}


def test_is_breeding_tick():
    """每 500 tick 一次检查,tick 0 不算。"""
    assert is_breeding_tick(0) is False
    assert is_breeding_tick(BREEDING_INTERVAL_TICKS) is True
    assert is_breeding_tick(BREEDING_INTERVAL_TICKS * 3) is True
    assert is_breeding_tick(BREEDING_INTERVAL_TICKS - 1) is False


def test_maybe_breed_only_on_tick_and_produces_babies():
    """非检查点 tick 不产蛋;检查点上亲密 pair 有概率产下 baby_i 新兽。"""
    a, b = _agent("亚古兽"), _agent("加布兽")
    tracker = RelationshipTracker()
    tracker.update("亚古兽", "加布兽", 95)

    # 非检查点: 空
    assert maybe_breed(37, tracker, [a, b], random.Random(0)) == []

    # 检查点: 用种子确保命中概率 (seed 20 first < 0.25)
    newborns = maybe_breed(
        BREEDING_INTERVAL_TICKS, tracker, [a, b], random.Random(1)
    )
    assert len(newborns) == 1
    assert newborns[0].stage == EvolutionStage.BABY_I

    # 关系不够的 pair: 检查点也不产蛋
    cold = RelationshipTracker()
    cold.update("亚古兽", "加布兽", BREEDING_THRESHOLD)  # 刚好 80,不 > 80
    assert maybe_breed(
        BREEDING_INTERVAL_TICKS, cold, [a, b], random.Random(0)
    ) == []

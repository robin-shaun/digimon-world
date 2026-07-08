"""
繁衍系统 (Breeding System) — 数码蛋与新生代
============================================

数码世界不是静止的:关系亲密的两只数码兽会孕育出数码蛋 (Digi-Egg),
孵化出幼年期 I (baby_i) 的新一代。这让世界能自我繁衍、种群随时间演化。

模型 (Phase 5,简单版):
- 只有关系值 > BREEDING_THRESHOLD (80) 的一对 (pair) 才够亲密去繁衍。
- 繁衍是低频事件:每 BREEDING_INTERVAL_TICKS (500) tick 检查一次符合条件的
  pair,每对以 BREEDING_CHANCE 的概率产下一颗蛋。
- 新生数码兽处于 EvolutionStage.BABY_I 阶段,stats 继承父母平均值,
  再叠加 ±STAT_VARIANCE (10%) 的随机浮动。

设计要点:
- 与 RelationshipTracker 解耦:只读关系表挑出亲密 pair,不改关系值。
- 随机性通过显式传入的 random.Random 提供,默认新建一个;单测传入固定
  种子即可完全复现 (与 act()/needs 的确定性风格一致)。
- 幼年期新生兽 bond 从 0 起步、技能为空 (由技能系统按阶段另发),
  region/attribute 随父母之一,方便它"出生"在父母身边。

详细设计: docs/DESIGN.md 第 7 节 "繁衍与种群"。
"""

from __future__ import annotations

import random
from typing import Iterable, Optional

from .digimon_agent import (
    DigimonAgent,
    DigimonAttribute,
    DigimonStats,
    EvolutionStage,
)
from ..world.relationships import RelationshipTracker

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------

BREEDING_THRESHOLD: float = 80.0    # 关系值高于此才够亲密去繁衍
BREEDING_INTERVAL_TICKS: int = 500  # 每隔这么多 tick 检查一次繁衍
BREEDING_CHANCE: float = 0.25       # 符合条件的一对,单次检查产蛋的概率
STAT_VARIANCE: float = 0.10         # 继承 stats 的 ±随机浮动幅度 (10%)

# 继承时参与"平均 + 浮动"的数值型字段 (max_* 随 hp/ep 一起算,见下)
_INHERITED_STATS = ("attack", "defense", "speed", "max_hp", "max_ep")


# ----------------------------------------------------------------------------
# 挑选可繁衍的 pair
# ----------------------------------------------------------------------------

def eligible_pairs(
    tracker: RelationshipTracker,
    agents: Iterable[DigimonAgent],
) -> list[tuple[DigimonAgent, DigimonAgent]]:
    """挑出所有关系值 > BREEDING_THRESHOLD 的数码兽对。

    只考虑当前存活 (传入 agents) 的个体;关系表里含已离场者的记录会被忽略。
    返回按名字字典序稳定排序的 (a, b) 列表 (a.name <= b.name),保证确定性。

    Args:
        tracker: 关系表 (只读)。
        agents: 参与繁衍的数码兽集合。

    Returns:
        亲密到可繁衍的 pair 列表。
    """
    roster = list(agents)
    pairs: list[tuple[DigimonAgent, DigimonAgent]] = []
    for i in range(len(roster)):
        for j in range(i + 1, len(roster)):
            a, b = roster[i], roster[j]
            if tracker.get_relationship(a.name, b.name) > BREEDING_THRESHOLD:
                lo, hi = (a, b) if a.name <= b.name else (b, a)
                pairs.append((lo, hi))
    pairs.sort(key=lambda p: (p[0].name, p[1].name))
    return pairs


# ----------------------------------------------------------------------------
# stats 继承
# ----------------------------------------------------------------------------

def inherit_stats(
    parent_a: DigimonStats,
    parent_b: DigimonStats,
    rng: Optional[random.Random] = None,
) -> DigimonStats:
    """由父母 stats 生成后代 stats: 逐字段取平均,再叠加 ±STAT_VARIANCE 浮动。

    - attack/defense/speed/max_hp/max_ep 取父母平均后各自随机浮动 ±10%,四舍五入取整,
      并保证不小于 1 (不会生出 0 攻/0 血的兽)。
    - hp/ep 满状态出生 (= 新生的 max_hp/max_ep)。
    - bond 从 0 起步 (新生兽还没和任何训练师建立羁绊)。
    - skills 留空 (由技能系统按 baby_i 阶段另行发放)。

    Args:
        parent_a, parent_b: 父母双方的 stats。
        rng: 随机源;默认新建一个 (非确定性)。单测传固定种子可复现。

    Returns:
        新生代的 DigimonStats。
    """
    rng = rng or random.Random()

    child = DigimonStats(bond=0, skills=[])
    for field_name in _INHERITED_STATS:
        avg = (getattr(parent_a, field_name) + getattr(parent_b, field_name)) / 2.0
        factor = 1.0 + rng.uniform(-STAT_VARIANCE, STAT_VARIANCE)
        value = max(1, round(avg * factor))
        setattr(child, field_name, value)

    # 满状态出生
    child.hp = child.max_hp
    child.ep = child.max_ep
    return child


# ----------------------------------------------------------------------------
# 产蛋 (生成新 agent)
# ----------------------------------------------------------------------------

def breed_egg(
    parent_a: DigimonAgent,
    parent_b: DigimonAgent,
    rng: Optional[random.Random] = None,
    name: Optional[str] = None,
) -> DigimonAgent:
    """由一对父母孕育一颗数码蛋 (baby_i 阶段的新 DigimonAgent)。

    继承规则:
    - stage: 恒为 EvolutionStage.BABY_I (幼年期 I)。
    - stats: 见 inherit_stats (父母平均 ±10%)。
    - species/attribute: 随父母之一 (rng 抛硬币决定,默认偏 parent_a)。
    - region_id/location: 出生在 parent_a 身边。

    Args:
        parent_a, parent_b: 父母双方。
        rng: 随机源;默认新建 (非确定性),单测传固定种子可复现。
        name: 指定名字;省略时用 "{species}蛋" 占位 (孵化时可再命名)。

    Returns:
        新生的幼年期数码兽。
    """
    rng = rng or random.Random()

    # 物种 / 属性随父母之一
    take_a = rng.random() < 0.5
    species = parent_a.species if take_a else parent_b.species
    attribute = parent_a.attribute if take_a else parent_b.attribute

    stats = inherit_stats(parent_a.stats, parent_b.stats, rng)

    return DigimonAgent(
        name=name or f"{species}蛋",
        species=species,
        stage=EvolutionStage.BABY_I,
        attribute=attribute,
        region_id=parent_a.region_id,
        location=parent_a.location,
        stats=stats,
    )


# ----------------------------------------------------------------------------
# 世界推进钩子: 到点检查 + 概率产蛋
# ----------------------------------------------------------------------------

def is_breeding_tick(tick: int) -> bool:
    """当前 tick 是否到达繁衍检查点 (每 BREEDING_INTERVAL_TICKS 一次,tick 0 不算)。"""
    return tick > 0 and tick % BREEDING_INTERVAL_TICKS == 0


def maybe_breed(
    tick: int,
    tracker: RelationshipTracker,
    agents: Iterable[DigimonAgent],
    rng: Optional[random.Random] = None,
) -> list[DigimonAgent]:
    """世界推进到某 tick 时尝试繁衍,返回本次新产下的数码蛋列表。

    仅在繁衍检查点 (is_breeding_tick) 触发;其余 tick 直接返回空列表。
    对每一对亲密 pair 独立掷骰,命中 BREEDING_CHANCE 才产蛋。

    Args:
        tick: 当前世界 tick 数。
        tracker: 关系表 (只读)。
        agents: 参与繁衍的数码兽集合。
        rng: 随机源;默认新建 (非确定性),单测传固定种子可复现。

    Returns:
        本次新生的数码兽列表 (可能为空)。调用方负责把它们加入世界。
    """
    if not is_breeding_tick(tick):
        return []

    rng = rng or random.Random()
    newborns: list[DigimonAgent] = []
    for parent_a, parent_b in eligible_pairs(tracker, agents):
        if rng.random() < BREEDING_CHANCE:
            newborns.append(breed_egg(parent_a, parent_b, rng))
    return newborns


__all__ = [
    "BREEDING_THRESHOLD",
    "BREEDING_INTERVAL_TICKS",
    "BREEDING_CHANCE",
    "STAT_VARIANCE",
    "eligible_pairs",
    "inherit_stats",
    "breed_egg",
    "is_breeding_tick",
    "maybe_breed",
]

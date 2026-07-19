"""
BadgeSystem 单元测试
====================

覆盖:
- COURAGE: 战斗胜利 > 10 获得
- FRIENDSHIP: 关系分 > 90 获得
- HOPE: 进化到 champion/mega 获得
- KNOWLEDGE: 探索全部区域获得
- 无徽章场景
- 多徽章同时满足

运行: cd backend && source .venv/bin/activate && pytest tests/test_badges.py -v
"""

from __future__ import annotations

import pytest

from digimon_world.agents.badges import COURAGE_VICTORIES_THRESHOLD, FRIENDSHIP_SCORE_THRESHOLD, Badge, BadgeSystem
from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats, EvolutionStage
from digimon_world.world.relationships import RelationshipTracker
from digimon_world.world.world_state import WorldState

# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------

@pytest.fixture
def world() -> WorldState:
    """带两个区域的世界。"""
    w = WorldState()
    # WorldState 默认有 file_island; 加一个 server_continent
    if "server_continent" not in w.regions:
        from digimon_world.world.world_state import Region
        w.regions["server_continent"] = Region(
            region_id="server_continent",
            name="Server Continent",
            description="广阔的服务器大陆",
            bounds=(0, 0, 500, 500),
        )
    return w


@pytest.fixture
def tracker() -> RelationshipTracker:
    return RelationshipTracker()


@pytest.fixture
def rookie_agent() -> DigimonAgent:
    """一只普通 ROOKIE 数码兽,无战斗记录。"""
    return DigimonAgent(
        name="Agumon",
        species="Agumon",
        stage=EvolutionStage.ROOKIE,
        stats=DigimonStats(),
    )


@pytest.fixture
def badge_system(world: WorldState, tracker: RelationshipTracker) -> BadgeSystem:
    return BadgeSystem(world=world, tracker=tracker)


# ----------------------------------------------------------------------------
# COURAGE
# ----------------------------------------------------------------------------

def test_courage_not_earned_at_threshold(badge_system: BadgeSystem, rookie_agent: DigimonAgent):
    """刚好等于阈值不授予 COURAGE。"""
    rookie_agent.battle_victories = COURAGE_VICTORIES_THRESHOLD
    badges = badge_system.evaluate(rookie_agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.COURAGE.value not in badge_values


def test_courage_earned_above_threshold(badge_system: BadgeSystem, rookie_agent: DigimonAgent):
    """超过阈值授予 COURAGE。"""
    rookie_agent.battle_victories = COURAGE_VICTORIES_THRESHOLD + 1
    badges = badge_system.evaluate(rookie_agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.COURAGE.value in badge_values


# ----------------------------------------------------------------------------
# FRIENDSHIP
# ----------------------------------------------------------------------------

def test_friendship_not_earned_low_score(world: WorldState, tracker: RelationshipTracker, rookie_agent: DigimonAgent):
    """关系分不够不授予 FRIENDSHIP。"""
    tracker.record_battle(winner="Agumon", loser="Gabumon")  # 小幅变化
    system = BadgeSystem(world=world, tracker=tracker)
    badges = system.evaluate(rookie_agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.FRIENDSHIP.value not in badge_values


def test_friendship_earned_high_score(world: WorldState, tracker: RelationshipTracker, rookie_agent: DigimonAgent):
    """关系分超过 90 授予 FRIENDSHIP。"""
    # 手动设置高分关系
    tracker._scores[("Agumon", "Gabumon")] = FRIENDSHIP_SCORE_THRESHOLD + 1
    system = BadgeSystem(world=world, tracker=tracker)
    badges = system.evaluate(rookie_agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.FRIENDSHIP.value in badge_values


# ----------------------------------------------------------------------------
# HOPE
# ----------------------------------------------------------------------------

def test_hope_not_earned_rookie(badge_system: BadgeSystem, rookie_agent: DigimonAgent):
    """ROOKIE 阶段不授予 HOPE。"""
    badges = badge_system.evaluate(rookie_agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.HOPE.value not in badge_values


def test_hope_earned_champion(badge_system: BadgeSystem):
    """CHAMPION 阶段授予 HOPE。"""
    agent = DigimonAgent(
        name="Greymon",
        species="Greymon",
        stage=EvolutionStage.CHAMPION,
        stats=DigimonStats(),
    )
    badges = badge_system.evaluate(agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.HOPE.value in badge_values


def test_hope_earned_mega(badge_system: BadgeSystem):
    """MEGA 阶段也授予 HOPE。"""
    agent = DigimonAgent(
        name="WarGreymon",
        species="WarGreymon",
        stage=EvolutionStage.MEGA,
        stats=DigimonStats(),
    )
    badges = badge_system.evaluate(agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.HOPE.value in badge_values


# ----------------------------------------------------------------------------
# KNOWLEDGE
# ----------------------------------------------------------------------------

def test_knowledge_not_earned_single_region(badge_system: BadgeSystem, rookie_agent: DigimonAgent):
    """只待在一个区域不授予 KNOWLEDGE。"""
    badges = badge_system.evaluate(rookie_agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.KNOWLEDGE.value not in badge_values


def test_knowledge_earned_all_regions(world: WorldState, tracker: RelationshipTracker):
    """探索过全部区域授予 KNOWLEDGE。"""
    agent = DigimonAgent(
        name="Tentomon",
        species="Tentomon",
        stage=EvolutionStage.ROOKIE,
        stats=DigimonStats(),
        region_id="file_island",
    )
    # 模拟去过世界中所有其他区域的记忆
    for region_id in world.regions:
        if region_id != "file_island":
            agent.observe({"type": "moved", "region_id": region_id})

    system = BadgeSystem(world=world, tracker=tracker)
    badges = system.evaluate(agent)
    badge_values = [b["badge"] for b in badges]
    assert Badge.KNOWLEDGE.value in badge_values


# ----------------------------------------------------------------------------
# 综合
# ----------------------------------------------------------------------------

def test_no_badges_default(badge_system: BadgeSystem, rookie_agent: DigimonAgent):
    """默认新数码兽无任何徽章。"""
    badges = badge_system.evaluate(rookie_agent)
    assert badges == []


def test_multiple_badges(world: WorldState, tracker: RelationshipTracker):
    """同时满足多个条件获得多个徽章。"""
    agent = DigimonAgent(
        name="MetalGreymon",
        species="MetalGreymon",
        stage=EvolutionStage.CHAMPION,
        stats=DigimonStats(),
        region_id="file_island",
    )
    agent.battle_victories = 15  # COURAGE
    # KNOWLEDGE: 去过全部区域
    for region_id in world.regions:
        if region_id != "file_island":
            agent.observe({"type": "moved", "region_id": region_id})

    system = BadgeSystem(world=world, tracker=tracker)
    badges = system.evaluate(agent)
    badge_values = [b["badge"] for b in badges]

    assert Badge.COURAGE.value in badge_values
    assert Badge.HOPE.value in badge_values
    assert Badge.KNOWLEDGE.value in badge_values

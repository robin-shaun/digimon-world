"""
AchievementSystem 单元测试
============================

覆盖:
- FIRST_BATTLE: battle_victories >= 1 达成
- FIRST_EVOLUTION: stage 为 CHAMPION/MEGA 或记忆中有进化记录
- HUNDRED_TICKS: memory entries >= 100 达成
- 无里程碑场景
- 多里程碑同时满足

运行: cd backend && source .venv/bin/activate && pytest tests/test_achievements.py -v
"""

from __future__ import annotations

import pytest

from digimon_world.agents.achievements import (
    AchievementSystem,
    FIRST_BATTLE_VICTORIES,
    HUNDRED_TICKS_MEMORY_COUNT,
    Milestone,
)
from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats, EvolutionStage


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------

@pytest.fixture
def system() -> AchievementSystem:
    return AchievementSystem()


@pytest.fixture
def rookie_agent() -> DigimonAgent:
    """一只普通 ROOKIE 数码兽,无战斗记录。"""
    return DigimonAgent(
        name="Agumon",
        species="Agumon",
        stage=EvolutionStage.ROOKIE,
        stats=DigimonStats(),
    )


# ----------------------------------------------------------------------------
# FIRST_BATTLE
# ----------------------------------------------------------------------------

def test_first_battle_not_earned_zero_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """零胜场不达成 FIRST_BATTLE。"""
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_BATTLE.value not in milestone_values


def test_first_battle_earned_one_victory(system: AchievementSystem, rookie_agent: DigimonAgent):
    """一场胜利达成 FIRST_BATTLE。"""
    rookie_agent.battle_victories = FIRST_BATTLE_VICTORIES
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_BATTLE.value in milestone_values


def test_first_battle_earned_many_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """多场胜利也达成 FIRST_BATTLE。"""
    rookie_agent.battle_victories = 50
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_BATTLE.value in milestone_values


# ----------------------------------------------------------------------------
# FIRST_EVOLUTION
# ----------------------------------------------------------------------------

def test_first_evolution_not_earned_rookie(system: AchievementSystem, rookie_agent: DigimonAgent):
    """ROOKIE 阶段无进化记忆不达成 FIRST_EVOLUTION。"""
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_EVOLUTION.value not in milestone_values


def test_first_evolution_earned_champion(system: AchievementSystem):
    """CHAMPION 阶段达成 FIRST_EVOLUTION。"""
    agent = DigimonAgent(
        name="Greymon",
        species="Greymon",
        stage=EvolutionStage.CHAMPION,
        stats=DigimonStats(),
    )
    achievements = system.evaluate(agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_EVOLUTION.value in milestone_values


def test_first_evolution_earned_mega(system: AchievementSystem):
    """MEGA 阶段达成 FIRST_EVOLUTION。"""
    agent = DigimonAgent(
        name="WarGreymon",
        species="WarGreymon",
        stage=EvolutionStage.MEGA,
        stats=DigimonStats(),
    )
    achievements = system.evaluate(agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_EVOLUTION.value in milestone_values


def test_first_evolution_earned_by_memory(system: AchievementSystem, rookie_agent: DigimonAgent):
    """ROOKIE 阶段但记忆中有进化记录也达成(退化场景)。"""
    # 模拟 EvolutionSystem 写入的进化记忆
    rookie_agent.memory.add(
        event={"description": "I evolved from rookie to champion (new form: Greymon, reason: battle)", "type": "evolution"},
        importance=9,
    )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_EVOLUTION.value in milestone_values


# ----------------------------------------------------------------------------
# HUNDRED_TICKS
# ----------------------------------------------------------------------------

def test_hundred_ticks_not_earned_few_entries(system: AchievementSystem, rookie_agent: DigimonAgent):
    """记忆条目不足 100 不达成 HUNDRED_TICKS。"""
    for i in range(50):
        rookie_agent.memory.add(event=f"tick event {i}", importance=3)
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.HUNDRED_TICKS.value not in milestone_values


def test_hundred_ticks_not_earned_at_99(system: AchievementSystem, rookie_agent: DigimonAgent):
    """99 条记忆不达成 HUNDRED_TICKS。"""
    for i in range(99):
        rookie_agent.memory.add(event=f"tick event {i}", importance=3)
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.HUNDRED_TICKS.value not in milestone_values


def test_hundred_ticks_earned_at_100(system: AchievementSystem, rookie_agent: DigimonAgent):
    """刚好 100 条记忆达成 HUNDRED_TICKS。"""
    for i in range(HUNDRED_TICKS_MEMORY_COUNT):
        rookie_agent.memory.add(event=f"tick event {i}", importance=3)
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.HUNDRED_TICKS.value in milestone_values


# ----------------------------------------------------------------------------
# 综合
# ----------------------------------------------------------------------------

def test_no_achievements_default(system: AchievementSystem, rookie_agent: DigimonAgent):
    """默认新数码兽无任何里程碑。"""
    achievements = system.evaluate(rookie_agent)
    assert achievements == []


def test_multiple_achievements(system: AchievementSystem):
    """同时满足多个里程碑。"""
    agent = DigimonAgent(
        name="MetalGreymon",
        species="MetalGreymon",
        stage=EvolutionStage.CHAMPION,
        stats=DigimonStats(),
    )
    agent.battle_victories = 5  # FIRST_BATTLE
    # HUNDRED_TICKS
    for i in range(120):
        agent.memory.add(event=f"tick event {i}", importance=3)

    achievements = system.evaluate(agent)
    milestone_values = [a["milestone"] for a in achievements]

    assert Milestone.FIRST_BATTLE.value in milestone_values
    assert Milestone.FIRST_EVOLUTION.value in milestone_values
    assert Milestone.HUNDRED_TICKS.value in milestone_values
    assert len(achievements) == 3

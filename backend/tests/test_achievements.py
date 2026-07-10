"""
AchievementSystem 单元测试
============================

覆盖:
- FIRST_DIALOGUE: 记忆中有对话记录达成
- FIRST_BATTLE: battle_victories >= 1 达成
- TEN_BATTLES: battle_victories >= 10 达成
- FIRST_EVOLUTION: stage 为 CHAMPION/MEGA 或记忆中有进化记录
- HUNDRED_TICKS: memory entries >= 100 达成
- FIVE_HUNDRED_TICKS: memory entries >= 500 达成
- 无里程碑场景
- 多里程碑同时满足(含递进: 高阶自动包含低阶)

运行: cd backend && source .venv/bin/activate && pytest tests/test_achievements.py -v
"""

from __future__ import annotations

import pytest

from digimon_world.agents.achievements import (
    AchievementSystem,
    FIVE_HUNDRED_TICKS_MEMORY_COUNT,
    FIRST_BATTLE_VICTORIES,
    HUNDRED_TICKS_MEMORY_COUNT,
    TEN_BATTLES_VICTORIES,
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
# FIRST_DIALOGUE
# ----------------------------------------------------------------------------

def test_first_dialogue_not_earned_no_memory(system: AchievementSystem, rookie_agent: DigimonAgent):
    """无记忆时不达成 FIRST_DIALOGUE。"""
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_DIALOGUE.value not in milestone_values


def test_first_dialogue_earned_with_meet_memory(system: AchievementSystem, rookie_agent: DigimonAgent):
    """记忆中有相遇记录时达成 FIRST_DIALOGUE。"""
    rookie_agent.memory.add(
        event={"description": "遇到加布兽,对它说:你好!", "type": "first_meet"},
        importance=8,
    )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_DIALOGUE.value in milestone_values


def test_first_dialogue_earned_with_dialogue_memory(system: AchievementSystem, rookie_agent: DigimonAgent):
    """记忆中有对话记录时达成 FIRST_DIALOGUE。"""
    rookie_agent.memory.add(
        event={"description": "与比丘兽进行了一场愉快的对话", "type": "dialogue"},
        importance=6,
    )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_DIALOGUE.value in milestone_values


# ----------------------------------------------------------------------------
# TEN_BATTLES
# ----------------------------------------------------------------------------

def test_ten_battles_not_earned_5_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """5 胜不达成 TEN_BATTLES。"""
    rookie_agent.battle_victories = 5
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.TEN_BATTLES.value not in milestone_values
    # 但 FIRST_BATTLE 应当有
    assert Milestone.FIRST_BATTLE.value in milestone_values


def test_ten_battles_not_earned_9_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """9 胜不达成 TEN_BATTLES(边界)。"""
    rookie_agent.battle_victories = 9
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.TEN_BATTLES.value not in milestone_values


def test_ten_battles_earned_10_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """刚好 10 胜达成 TEN_BATTLES。"""
    rookie_agent.battle_victories = TEN_BATTLES_VICTORIES
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.TEN_BATTLES.value in milestone_values
    assert Milestone.FIRST_BATTLE.value in milestone_values  # 递进: 低阶自动包含


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
# FIVE_HUNDRED_TICKS
# ----------------------------------------------------------------------------

def test_five_hundred_ticks_not_earned_300(system: AchievementSystem, rookie_agent: DigimonAgent):
    """300 条记忆不达成 FIVE_HUNDRED_TICKS。"""
    for i in range(300):
        rookie_agent.memory.add(event=f"tick event {i}", importance=3)
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIVE_HUNDRED_TICKS.value not in milestone_values
    # 但 HUNDRED_TICKS 应当有
    assert Milestone.HUNDRED_TICKS.value in milestone_values


def test_five_hundred_ticks_not_earned_499(system: AchievementSystem, rookie_agent: DigimonAgent):
    """499 条记忆不达成 FIVE_HUNDRED_TICKS(边界)。"""
    for i in range(499):
        rookie_agent.memory.add(event=f"tick event {i}", importance=3)
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIVE_HUNDRED_TICKS.value not in milestone_values


def test_five_hundred_ticks_earned_at_500(system: AchievementSystem, rookie_agent: DigimonAgent):
    """刚好 500 条记忆达成 FIVE_HUNDRED_TICKS。"""
    for i in range(FIVE_HUNDRED_TICKS_MEMORY_COUNT):
        rookie_agent.memory.add(event=f"tick event {i}", importance=3)
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIVE_HUNDRED_TICKS.value in milestone_values
    assert Milestone.HUNDRED_TICKS.value in milestone_values  # 递进


# ----------------------------------------------------------------------------
# 综合
# ----------------------------------------------------------------------------

def test_no_achievements_default(system: AchievementSystem, rookie_agent: DigimonAgent):
    """默认新数码兽无任何里程碑。"""
    achievements = system.evaluate(rookie_agent)
    assert achievements == []


def test_multiple_achievements(system: AchievementSystem):
    """同时满足多个里程碑(含递进: 高阶自动包含低阶)。"""
    agent = DigimonAgent(
        name="MetalGreymon",
        species="MetalGreymon",
        stage=EvolutionStage.CHAMPION,
        stats=DigimonStats(),
    )
    agent.battle_victories = 15  # FIRST_BATTLE + TEN_BATTLES
    # HUNDRED_TICKS + FIVE_HUNDRED_TICKS
    for i in range(600):
        agent.memory.add(event=f"tick event {i}", importance=3)
    # FIRST_DIALOGUE: 加一条对话记忆
    agent.memory.add(
        event={"description": "遇到加布兽,对它说:你好!", "type": "first_meet"},
        importance=8,
    )

    achievements = system.evaluate(agent)
    milestone_values = [a["milestone"] for a in achievements]

    assert Milestone.FIRST_DIALOGUE.value in milestone_values
    assert Milestone.FIRST_BATTLE.value in milestone_values
    assert Milestone.TEN_BATTLES.value in milestone_values
    assert Milestone.FIRST_EVOLUTION.value in milestone_values
    assert Milestone.HUNDRED_TICKS.value in milestone_values
    assert Milestone.FIVE_HUNDRED_TICKS.value in milestone_values
    assert len(achievements) == 6

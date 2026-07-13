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
    EXPLORER_CORE_LANDMARKS,
    FIVE_HUNDRED_TICKS_MEMORY_COUNT,
    FIFTY_BATTLES_VICTORIES,
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
# FIFTY_BATTLES
# ----------------------------------------------------------------------------

def test_fifty_battles_not_earned_30_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """30 胜不达成 FIFTY_BATTLES。"""
    rookie_agent.battle_victories = 30
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIFTY_BATTLES.value not in milestone_values
    assert Milestone.FIRST_BATTLE.value in milestone_values
    assert Milestone.TEN_BATTLES.value in milestone_values


def test_fifty_battles_not_earned_49_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """49 胜不达成 FIFTY_BATTLES(边界)。"""
    rookie_agent.battle_victories = 49
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIFTY_BATTLES.value not in milestone_values


def test_fifty_battles_earned_50_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """刚好 50 胜达成 FIFTY_BATTLES。"""
    rookie_agent.battle_victories = FIFTY_BATTLES_VICTORIES
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIFTY_BATTLES.value in milestone_values
    assert Milestone.TEN_BATTLES.value in milestone_values  # 递进


def test_fifty_battles_earned_100_victories(system: AchievementSystem, rookie_agent: DigimonAgent):
    """100 胜也达成 FIFTY_BATTLES。"""
    rookie_agent.battle_victories = 100
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIFTY_BATTLES.value in milestone_values


# ----------------------------------------------------------------------------
# SOCIAL_BUTTERFLY
# ----------------------------------------------------------------------------

def test_social_butterfly_not_earned_3_partners(system: AchievementSystem, rookie_agent: DigimonAgent):
    """3 个不同对话对象不达成 SOCIAL_BUTTERFLY。"""
    for partner in ["加布兽", "比丘兽", "巴达兽"]:
        rookie_agent.memory.add(
            event={"description": f"遇到{partner},向它打了个招呼", "type": "first_meet", "partner": partner},
            importance=5,
        )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.FIRST_DIALOGUE.value in milestone_values
    assert Milestone.SOCIAL_BUTTERFLY.value not in milestone_values


def test_social_butterfly_earned_5_partners(system: AchievementSystem, rookie_agent: DigimonAgent):
    """5 个不同对话对象达成 SOCIAL_BUTTERFLY。"""
    partners = ["加布兽", "比丘兽", "巴达兽", "甲虫兽", "迪路兽"]
    for p in partners:
        rookie_agent.memory.add(
            event={"description": f"遇到{p},和它进行了一段对话", "type": "dialogue", "partner": p},
            importance=6,
        )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.SOCIAL_BUTTERFLY.value in milestone_values


def test_social_butterfly_earned_7_partners(system: AchievementSystem, rookie_agent: DigimonAgent):
    """7 个不同对话对象也达成 SOCIAL_BUTTERFLY。"""
    for partner in ["加布兽", "比丘兽", "巴达兽", "甲虫兽", "迪路兽", "哥玛兽", "巴鲁兽"]:
        rookie_agent.memory.add(
            event={"description": f"和{partner}相遇并聊了一会", "type": "first_meet", "partner": partner},
            importance=4,
        )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.SOCIAL_BUTTERFLY.value in milestone_values


# ----------------------------------------------------------------------------
# EXPLORER
# ----------------------------------------------------------------------------

def test_explorer_not_earned_empty_memory(system: AchievementSystem, rookie_agent: DigimonAgent):
    """无记忆时不达成 EXPLORER。"""
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.EXPLORER.value not in milestone_values


def test_explorer_not_earned_partial_landmarks(system: AchievementSystem, rookie_agent: DigimonAgent):
    """只访问部分地标不达成 EXPLORER。"""
    for region in ["创始村", "无限山"]:
        rookie_agent.memory.add(
            event={"description": f"在{region}闲逛", "type": "movement", "region_id": region},
            importance=4,
        )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.EXPLORER.value not in milestone_values


def test_explorer_earned_all_landmarks(system: AchievementSystem, rookie_agent: DigimonAgent):
    """访问所有核心地标达成 EXPLORER。"""
    for region in EXPLORER_CORE_LANDMARKS:
        rookie_agent.memory.add(
            event={"description": f"探索{region}", "type": "movement", "region_id": region},
            importance=5,
        )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.EXPLORER.value in milestone_values


def test_explorer_earned_with_extra_regions(system: AchievementSystem, rookie_agent: DigimonAgent):
    """访问所有核心地标 + 额外区域也达成 EXPLORER。"""
    for region in list(EXPLORER_CORE_LANDMARKS) + ["玩具城"]:
        rookie_agent.memory.add(
            event={"description": f"到达{region}", "type": "movement", "region_id": region},
            importance=4,
        )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.EXPLORER.value in milestone_values


# ----------------------------------------------------------------------------
# BREEDER
# ----------------------------------------------------------------------------

def test_breeder_not_earned_no_memory(system: AchievementSystem, rookie_agent: DigimonAgent):
    """无记忆时不达成 BREEDER。"""
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.BREEDER.value not in milestone_values


def test_breeder_not_earned_normal_events(system: AchievementSystem, rookie_agent: DigimonAgent):
    """普通事件不触发 BREEDER。"""
    rookie_agent.memory.add(event={"description": "在草原上奔跑"}, importance=3)
    rookie_agent.memory.add(event={"description": "与加布兽战斗"}, importance=6)
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.BREEDER.value not in milestone_values


def test_breeder_earned_gave_birth(system: AchievementSystem, rookie_agent: DigimonAgent):
    """记忆中有 'gave birth' 记录达成 BREEDER。"""
    rookie_agent.memory.add(
        event={"description": "gave birth to a new DigiEgg after bonding with Gabumon", "type": "breeding"},
        importance=10,
    )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.BREEDER.value in milestone_values


def test_breeder_earned_produced_egg(system: AchievementSystem, rookie_agent: DigimonAgent):
    """记忆中有产蛋记录达成 BREEDER。"""
    rookie_agent.memory.add(
        event={"description": "produced an egg with Biyomon", "type": "breeding"},
        importance=9,
    )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.BREEDER.value in milestone_values


def test_breeder_earned_chinese_description(system: AchievementSystem, rookie_agent: DigimonAgent):
    """中文描述的繁衍记录达成 BREEDER。"""
    rookie_agent.memory.add(
        event={"description": "与加布兽成功繁衍,产下了一颗数码蛋", "type": "breeding"},
        importance=8,
    )
    achievements = system.evaluate(rookie_agent)
    milestone_values = [a["milestone"] for a in achievements]
    assert Milestone.BREEDER.value in milestone_values


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

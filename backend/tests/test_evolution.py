"""
EvolutionSystem 单元测试
========================

覆盖:
- next_stage / is_final_stage 边界
- compute_bond 累计记忆 importance
- can_evolve 在 victory / bond / 不达标三种情况
- evolve 真的改 agent.stage / species / stats / 写记忆
- MEGA 终态不能再进化
- check_and_evolve 一站式

运行: cd backend && source .venv/bin/activate && pytest tests/test_evolution.py -v
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats, EvolutionStage
from digimon_world.agents.evolution import (
    EVOLUTION_CHAIN,
    EvolutionReason,
    EvolutionSystem,
    is_final_stage,
    next_stage,
)


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------

@pytest.fixture
def agumon() -> DigimonAgent:
    """一只刚从 ROOKIE 起步的亚古兽。"""
    return DigimonAgent(
        name="Agumon",
        species="Agumon",
        stage=EvolutionStage.ROOKIE,
        stats=DigimonStats(hp=100, max_hp=100, ep=50, max_ep=50, attack=30, defense=20, speed=25),
    )


@pytest.fixture
def evo_system() -> EvolutionSystem:
    return EvolutionSystem()


# ----------------------------------------------------------------------------
# Stage 边界
# ----------------------------------------------------------------------------

def test_next_stage_basic():
    assert next_stage(EvolutionStage.BABY_I) == EvolutionStage.BABY_II
    assert next_stage(EvolutionStage.BABY_II) == EvolutionStage.ROOKIE
    assert next_stage(EvolutionStage.ROOKIE) == EvolutionStage.CHAMPION
    assert next_stage(EvolutionStage.CHAMPION) == EvolutionStage.ULTIMATE
    assert next_stage(EvolutionStage.ULTIMATE) == EvolutionStage.MEGA


def test_next_stage_mega_returns_none():
    """MEGA 是终态,没有下一阶段。"""
    assert next_stage(EvolutionStage.MEGA) is None


def test_is_final_stage():
    assert is_final_stage(EvolutionStage.MEGA) is True
    assert is_final_stage(EvolutionStage.ROOKIE) is False
    assert is_final_stage(EvolutionStage.BABY_I) is False


def test_evolution_chain_has_five_entries():
    """6 个阶段中前 5 个有升级链,MEGA 不在里面。"""
    assert len(EVOLUTION_CHAIN) == 5
    assert EvolutionStage.MEGA not in EVOLUTION_CHAIN


# ----------------------------------------------------------------------------
# Bond 计算
# ----------------------------------------------------------------------------

def test_compute_bond_zero_on_fresh_agent(agumon, evo_system):
    assert evo_system.compute_bond(agumon) == 0


def test_compute_bond_sums_importance(agumon, evo_system):
    agumon.observe({"type": "moved", "delta": (1, 0)})            # importance 3
    agumon.observe({"type": "battle_victory", "opponent": "x"})   # importance 9
    agumon.observe({"type": "ate"})                                # importance 3
    assert evo_system.compute_bond(agumon) == 3 + 9 + 3


# ----------------------------------------------------------------------------
# can_evolve
# ----------------------------------------------------------------------------

def test_can_evolve_not_ready_too_few_victories_and_bond(agumon, evo_system):
    """刚开局什么都不够,不能进化。"""
    can, reason, crest = evo_system.can_evolve(agumon, battle_victories=0, bond=0)
    assert can is False
    assert reason == EvolutionReason.NOT_READY


def test_can_evolve_ready_when_both_met(agumon, evo_system):
    """ROOKIE → CHAMPION 需要 8 胜利 + 40 bond。"""
    can, reason, crest = evo_system.can_evolve(agumon, battle_victories=8, bond=40)
    assert can is True
    assert reason == EvolutionReason.BATTLE_VICTORIES


def test_can_evolve_bond_overflow_pure_bond_route(agumon, evo_system):
    """胜利不够,但羁绊值溢出 2 倍,纯羁绊路线。"""
    can, reason, crest = evo_system.can_evolve(agumon, battle_victories=0, bond=80)
    assert can is True
    assert reason == EvolutionReason.BOND


def test_can_evolve_mega_cannot_go_further(evo_system):
    mega = DigimonAgent(
        name="WarGreymon",
        species="WarGreymon",
        stage=EvolutionStage.MEGA,
    )
    can, reason, crest = evo_system.can_evolve(mega, battle_victories=999, bond=999)
    assert can is False
    assert reason == EvolutionReason.ALREADY_MEGA


# ----------------------------------------------------------------------------
# evolve
# ----------------------------------------------------------------------------

def test_evolve_changes_stage_and_species(agumon, evo_system):
    old_stage = agumon.stage
    result = evo_system.evolve(agumon, reason=EvolutionReason.BATTLE_VICTORIES)
    assert result.evolved is True
    assert result.old_stage == old_stage
    assert result.new_stage == EvolutionStage.CHAMPION
    assert agumon.stage == EvolutionStage.CHAMPION
    # Phase 8: Agumon → Greymon (物种特定路由)
    assert agumon.species == "greymon"


def test_evolve_scales_stats(agumon, evo_system):
    """进化后 hp/max_hp/attack 应该是 1.5 倍 (int 截断)。"""
    evo_system.evolve(agumon, reason=EvolutionReason.BATTLE_VICTORIES)
    assert agumon.stats.max_hp == 150       # 100 * 1.5
    assert agumon.stats.hp == 150            # 当前 HP 也按上限放
    assert agumon.stats.attack == 45         # 30 * 1.5


def test_evolve_writes_memory(agumon, evo_system):
    before = len(agumon.memory.entries)
    evo_system.evolve(agumon, reason=EvolutionReason.BATTLE_VICTORIES)
    assert len(agumon.memory.entries) == before + 1
    last = agumon.memory.entries[-1]
    # MemoryStream.add 把 dict 压成 description 字符串
    assert "evolved" in last.description.lower()
    assert "champion" in last.description
    assert last.importance >= 8  # 高重要


def test_evolve_mega_returns_failure(evo_system):
    mega = DigimonAgent(name="WGM", species="WGM", stage=EvolutionStage.MEGA)
    result = evo_system.evolve(mega, reason=EvolutionReason.BOND)
    assert result.evolved is False
    assert result.reason == EvolutionReason.ALREADY_MEGA
    assert mega.stage == EvolutionStage.MEGA


# ----------------------------------------------------------------------------
# check_and_evolve 一站式
# ----------------------------------------------------------------------------

def test_check_and_evolve_full_chain(evo_system):
    """一只 BABY_I 数码兽从最底层一路进化到 MEGA。"""
    a = DigimonAgent(
        name="Botamon",
        species="Botamon",
        stage=EvolutionStage.BABY_I,
        stats=DigimonStats(hp=20, max_hp=20, ep=10, max_ep=10, attack=5, defense=5, speed=5),
    )

    # BABY_I → BABY_II (1 win, 5 bond)
    r1 = evo_system.check_and_evolve(a, battle_victories=1, bond=5)
    assert r1.evolved and r1.new_stage == EvolutionStage.BABY_II

    # BABY_II → ROOKIE (3 wins, 15 bond)
    r2 = evo_system.check_and_evolve(a, battle_victories=3, bond=15)
    assert r2.evolved and r2.new_stage == EvolutionStage.ROOKIE

    # ROOKIE → CHAMPION (8 wins, 40 bond)
    r3 = evo_system.check_and_evolve(a, battle_victories=8, bond=40)
    assert r3.evolved and r3.new_stage == EvolutionStage.CHAMPION

    # CHAMPION → ULTIMATE (15 wins, 60 bond) — 无特定物种,无需徽章
    r4 = evo_system.check_and_evolve(a, battle_victories=15, bond=60)
    assert r4.evolved and r4.new_stage == EvolutionStage.ULTIMATE

    # Phase 8: ULTIMATE → MEGA 需要特殊事件触发
    evo_system.trigger_story_event("angemon_arrow")

    # ULTIMATE → MEGA (25 wins, 100 bond)
    r5 = evo_system.check_and_evolve(a, battle_victories=25, bond=100)
    assert r5.evolved and r5.new_stage == EvolutionStage.MEGA

    # MEGA 终止
    r6 = evo_system.check_and_evolve(a, battle_victories=999, bond=999)
    assert r6.evolved is False
    assert r6.reason == EvolutionReason.ALREADY_MEGA


def test_check_and_evolve_not_ready_no_change(agumon, evo_system):
    """什么都不够 → 不进化,状态不变。"""
    before_stage = agumon.stage
    before_species = agumon.species
    r = evo_system.check_and_evolve(agumon, battle_victories=0, bond=0)
    assert r.evolved is False
    assert agumon.stage == before_stage
    assert agumon.species == before_species
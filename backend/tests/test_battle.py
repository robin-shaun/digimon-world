"""
战斗系统测试
============

覆盖:
- 伤害计算: 基础 / 最小 1 / 属性克制 / 自由种无加成
- 战斗引擎: 跑通 / 必有胜者 / 上限 50 回合
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import (
    DigimonAgent,
    DigimonAttribute,
    DigimonStats,
)
from digimon_world.battle.damage import DamageCalculator, is_strong_against
from digimon_world.battle.engine import BattleEngine, MAX_ROUNDS
from digimon_world.battle.types import ActionType, BattleResult


# ---- helpers ----


def _agent(
    name: str,
    attack: int = 20,
    defense: int = 15,
    hp: int = 100,
    attribute: DigimonAttribute = DigimonAttribute.VACCINE,
) -> DigimonAgent:
    return DigimonAgent(
        name=name,
        species=name,
        attribute=attribute,
        stats=DigimonStats(hp=hp, max_hp=hp, attack=attack, defense=defense),
    )


# ========== 伤害计算 ==========


class TestDamageCalculator:
    """DamageCalculator 单元测试。"""

    def test_damage_base(self) -> None:
        """同样 stats 互相攻击,伤害 > 0。"""
        a = _agent("A", attack=20, defense=15)
        b = _agent("B", attack=20, defense=15)
        dmg = DamageCalculator.calc_damage(a, b)
        # base = 20 - 15//2 = 20 - 7 = 13
        assert dmg > 0
        assert dmg == 13

    def test_damage_minimum_one(self) -> None:
        """防御超高时,仍保证至少 1 点伤害。"""
        a = _agent("弱攻", attack=1, defense=0)
        b = _agent("铁壁", attack=1, defense=9999)
        dmg = DamageCalculator.calc_damage(a, b)
        assert dmg == 1

    def test_damage_attribute_vaccine_beats_virus(self) -> None:
        """疫苗种攻击病毒种,伤害 x1.5。"""
        a = _agent("疫苗兽", attack=20, defense=10, attribute=DigimonAttribute.VACCINE)
        b = _agent("病毒兽", attack=20, defense=10, attribute=DigimonAttribute.VIRUS)
        dmg_strong = DamageCalculator.calc_damage(a, b)
        # base = 20 - 10//2 = 15, * 1.5 = 22
        assert dmg_strong == 22

        # 反过来:virus 打 vaccine 无加成
        dmg_normal = DamageCalculator.calc_damage(b, a)
        # base = 20 - 10//2 = 15, * 1.0 = 15
        assert dmg_normal == 15
        assert dmg_strong > dmg_normal

    def test_damage_attribute_free_no_modifier(self) -> None:
        """自由种攻击任何属性,乘数为 1.0(无加成)。"""
        free = _agent("自由兽", attack=20, defense=10, attribute=DigimonAttribute.FREE)
        virus = _agent("病毒兽", attack=20, defense=10, attribute=DigimonAttribute.VIRUS)
        vaccine = _agent("疫苗兽", attack=20, defense=10, attribute=DigimonAttribute.VACCINE)

        dmg_vs_virus = DamageCalculator.calc_damage(free, virus)
        dmg_vs_vaccine = DamageCalculator.calc_damage(free, vaccine)
        # free 不克制任何人,全部 x1.0
        assert dmg_vs_virus == dmg_vs_vaccine
        assert not is_strong_against(DigimonAttribute.FREE, DigimonAttribute.VIRUS)
        assert not is_strong_against(DigimonAttribute.FREE, DigimonAttribute.VACCINE)

    def test_damage_with_skill_bonus(self) -> None:
        """使用技能时 +20% 加成。"""
        a = _agent("A", attack=20, defense=10)
        b = _agent("B", attack=20, defense=10)
        dmg_normal = DamageCalculator.calc_damage(a, b, skill=None)
        dmg_skill = DamageCalculator.calc_damage(a, b, skill="火焰弹")
        # skill 加成 1.2x
        assert dmg_skill > dmg_normal
        # base=15, normal=15, skill=int(15*1.2)=18
        assert dmg_skill == 18


# ========== 属性克制 helper ==========


class TestIsStrongAgainst:
    """is_strong_against 小测试。"""

    def test_vaccine_beats_virus(self) -> None:
        assert is_strong_against(DigimonAttribute.VACCINE, DigimonAttribute.VIRUS)

    def test_data_beats_vaccine(self) -> None:
        assert is_strong_against(DigimonAttribute.DATA, DigimonAttribute.VACCINE)

    def test_virus_beats_data(self) -> None:
        assert is_strong_against(DigimonAttribute.VIRUS, DigimonAttribute.DATA)

    def test_free_beats_none(self) -> None:
        for attr in DigimonAttribute:
            assert not is_strong_against(DigimonAttribute.FREE, attr)


# ========== 战斗引擎 ==========


class TestBattleEngine:
    """BattleEngine 集成测试。"""

    @pytest.mark.asyncio
    async def test_battle_starts(self) -> None:
        """两个 agent 可以正常开打并返回 BattleResult。"""
        a = _agent("亚古兽", attack=20, defense=10, hp=50)
        b = _agent("加布兽", attack=18, defense=12, hp=50)
        engine = BattleEngine()
        result = await engine.run_battle(a, b)

        assert isinstance(result, BattleResult)
        assert result.rounds > 0
        assert result.winner_name in {"亚古兽", "加布兽"}

    @pytest.mark.asyncio
    async def test_battle_winner_determined(self) -> None:
        """必有胜者: 败方 HP 归 0。"""
        a = _agent("强攻兽", attack=30, defense=5, hp=80)
        b = _agent("弱防兽", attack=10, defense=5, hp=60)
        engine = BattleEngine()
        result = await engine.run_battle(a, b)

        assert result.winner_name is not None
        # 败方 HP 归 0
        loser = "弱防兽" if result.winner_name == "强攻兽" else "强攻兽"
        assert result.final_hp[loser] == 0
        # 胜方 HP > 0
        assert result.final_hp[result.winner_name] > 0

    @pytest.mark.asyncio
    async def test_battle_max_50_rounds(self) -> None:
        """极强 agent 对极强,防御超高打不死——不死循环,上限 50 回合。"""
        # 两只都攻击极低、防御极高,每回合只打 1 点,但 HP 超大
        a = _agent("铁壁A", attack=1, defense=9999, hp=9999)
        b = _agent("铁壁B", attack=1, defense=9999, hp=9999)
        engine = BattleEngine()
        result = await engine.run_battle(a, b)

        # 不超过上限
        assert result.rounds <= MAX_ROUNDS
        # 在这种极端情况下应该是超时(50 回合仍未分胜负)
        # 每回合每人受 1 点伤害,50 回合 = 各受 50 点,远低于 9999
        assert result.winner_name is None
        assert result.rounds == MAX_ROUNDS

    @pytest.mark.asyncio
    async def test_battle_does_not_mutate_agent_stats(self) -> None:
        """战斗不修改 agent 自身的 stats.hp(用局部 HP 追踪)。"""
        a = _agent("A", attack=25, defense=5, hp=50)
        b = _agent("B", attack=25, defense=5, hp=50)
        engine = BattleEngine()
        await engine.run_battle(a, b)

        # 战斗后 agent 原始 HP 不变
        assert a.stats.hp == 50
        assert b.stats.hp == 50

"""
战斗引擎 (BattleEngine)
=======================

参考 docs/DESIGN.md 第 5 节。

本 commit(Phase 3 第一步):
- 脚本式确定性战斗: 每回合 A 打 B,再 B 打 A,直到一方 HP<=0
- 不调用 LLM(留给 Phase 3 后半)
- 上限 50 回合,防止死循环
- HP 归零 = 战斗失败(不真死,数字兽消散;后续可重生)
"""

from __future__ import annotations

from typing import Any, Optional

from ..agents.digimon_agent import DigimonAgent
from .damage import DamageCalculator
from .types import BattleResult

# 战斗回合上限(防止两只都打不死对方时死循环)
MAX_ROUNDS: int = 50


class BattleEngine:
    """回合制战斗引擎。

    Phase 3 第一步走脚本式(确定性)攻击循环;
    后半再接入 LLM 决策(攻击/防御/技能/逃跑)。
    """

    async def run_battle(
        self,
        agent_a: DigimonAgent,
        agent_b: DigimonAgent,
        llm_client: Optional[Any] = None,
    ) -> BattleResult:
        """跑一场 A vs B 的战斗。

        Args:
            agent_a: 先手方
            agent_b: 后手方
            llm_client: 预留给 Phase 3 后半的 LLM 决策客户端;本 commit 忽略。

        Returns:
            BattleResult(胜者 / 回合数 / 各方最终 HP)。

        注意: 战斗不修改 agent 自身的 stats.hp,使用局部 HP 追踪,
        以便同一只数码兽可反复战斗;由调用方决定如何落实伤害/消散。
        """
        # 局部 HP,不污染 agent.stats
        hp_a = agent_a.stats.hp
        hp_b = agent_b.stats.hp

        rounds = 0
        winner: Optional[str] = None

        while rounds < MAX_ROUNDS:
            rounds += 1

            # ---- A 攻击 B ----
            dmg = DamageCalculator.calc_damage(agent_a, agent_b, skill=None)
            hp_b -= dmg
            if hp_b <= 0:
                hp_b = 0
                winner = agent_a.name
                break

            # ---- B 攻击 A ----
            dmg = DamageCalculator.calc_damage(agent_b, agent_a, skill=None)
            hp_a -= dmg
            if hp_a <= 0:
                hp_a = 0
                winner = agent_b.name
                break

        return BattleResult(
            winner_name=winner,
            rounds=rounds,
            final_hp={agent_a.name: hp_a, agent_b.name: hp_b},
        )

"""
战斗引擎 (BattleEngine)
=======================

参考 docs/DESIGN.md 第 5 节。

本 commit(Phase 3 第一步):
- 脚本式确定性战斗: 每回合 A 打 B,再 B 打 A,直到一方 HP<=0
- 传入 llm_client 时: 每回合双方用 LLM 决策动作(attack/defend/flee)
- 上限 50 回合,防止死循环
- HP 归零 = 战斗失败(不真死,数字兽消散;后续可重生)
"""

from __future__ import annotations

from typing import Optional

from ..agents.digimon_agent import DigimonAgent
from ..llm.client import LlmClient
from . import llm_ai
from .damage import DamageCalculator
from .types import BattleResult

# defend 时受到的伤害折减系数(防御成功打五折)
DEFEND_MITIGATION: float = 0.5

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
        llm_client: Optional[LlmClient] = None,
    ) -> BattleResult:
        """跑一场 A vs B 的战斗。

        Args:
            agent_a: 先手方
            agent_b: 后手方
            llm_client: 若传入,则每回合双方用 LLM 决策动作(attack/defend/flee);
                不传则走旧的脚本式互打(向后兼容)。

        Returns:
            BattleResult(胜者 / 回合数 / 各方最终 HP)。

        注意: 战斗不修改 agent 自身的 stats.hp,使用局部 HP 追踪,
        以便同一只数码兽可反复战斗;由调用方决定如何落实伤害/消散。
        """
        # 局部 HP,不污染 agent.stats
        hp_a = agent_a.stats.hp
        hp_b = agent_b.stats.hp
        max_a = agent_a.stats.max_hp or agent_a.stats.hp
        max_b = agent_b.stats.max_hp or agent_b.stats.hp

        rounds = 0
        winner: Optional[str] = None

        while rounds < MAX_ROUNDS:
            rounds += 1

            if llm_client is None:
                # ---- 脚本式: A 打 B,再 B 打 A ----
                hp_b -= DamageCalculator.calc_damage(agent_a, agent_b, skill=None)
                if hp_b <= 0:
                    hp_b = 0
                    winner = agent_a.name
                    break
                hp_a -= DamageCalculator.calc_damage(agent_b, agent_a, skill=None)
                if hp_a <= 0:
                    hp_a = 0
                    winner = agent_b.name
                    break
                continue

            # ---- LLM 决策式 ----
            # 回合开始双方各自决策(基于回合初的 HP 态势)
            action_a = await llm_ai.decide_action(
                llm_client, agent_a, agent_b, hp_a / max_a, hp_b / max_b
            )
            action_b = await llm_ai.decide_action(
                llm_client, agent_b, agent_a, hp_b / max_b, hp_a / max_a
            )

            # 逃跑判定: 谁逃跑谁认输(对方为胜者);双方都逃则无胜者结束
            if action_a == "flee" or action_b == "flee":
                if action_a == "flee" and action_b != "flee":
                    winner = agent_b.name
                elif action_b == "flee" and action_a != "flee":
                    winner = agent_a.name
                break

            # ---- A 攻击 B(B 防御则折减) ----
            if action_a == "attack":
                dmg = DamageCalculator.calc_damage(agent_a, agent_b, skill=None)
                if action_b == "defend":
                    dmg = max(1, int(dmg * DEFEND_MITIGATION))
                hp_b -= dmg
                if hp_b <= 0:
                    hp_b = 0
                    winner = agent_a.name
                    break

            # ---- B 攻击 A(A 防御则折减) ----
            if action_b == "attack":
                dmg = DamageCalculator.calc_damage(agent_b, agent_a, skill=None)
                if action_a == "defend":
                    dmg = max(1, int(dmg * DEFEND_MITIGATION))
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

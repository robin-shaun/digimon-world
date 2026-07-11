"""
进化系统 (Evolution System)
===========================

数码兽 6 阶段进化链 (参考数码宝贝动画世界观):

    BABY_I  →  BABY_II  →  ROOKIE  →  CHAMPION  →  ULTIMATE  →  MEGA

触发条件 (本 commit):
1. 战斗胜利数 ≥ 当前阶段阈值
2. 羁绊值 ≥ 当前阶段阈值 (由 memory 中高 importance 记忆累计)
3. 剧情事件 (可选,占位)

进化会修改:
- agent.stage
- agent.stats (按 species 模板重新填充 hp/max_hp/attack/defense)
- 写一条 high-importance 记忆 "I evolved into <new stage>"
- 返回 EvolutionResult (old_stage, new_stage, reason)

参考 docs/DESIGN.md 第 4 节 "进化系统"。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .digimon_agent import DigimonAgent, DigimonStats, EvolutionStage


# ----------------------------------------------------------------------------
# 进化阈值表 (每个阶段 → 需要的胜利数 / 羁绊值)
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class EvolutionRequirement:
    """某一阶段升到下一阶段的前置条件。"""

    min_victories: int       # 战斗胜利次数门槛
    min_bond: int            # 羁绊值门槛 (记忆流累计 importance)
    next_species: str        # 进化后的 species 名 (占位,后续用图鉴映射)


# BABY_I → BABY_II 极宽松,开局几场战斗就能进化
# BABY_II → ROOKIE 主角首次 "成熟",典型动画设定
# ROOKIE → CHAMPION 战斗经验丰富
# CHAMPION → ULTIMATE 完全体进化,需要深厚羁绊
# ULTIMATE → MEGA 究极体,需要大量羁绊 + 胜利
EVOLUTION_CHAIN: dict[EvolutionStage, EvolutionRequirement] = {
    EvolutionStage.BABY_I: EvolutionRequirement(
        min_victories=1,
        min_bond=5,
        next_species="baby_ii_form",
    ),
    EvolutionStage.BABY_II: EvolutionRequirement(
        min_victories=3,
        min_bond=15,
        next_species="rookie_form",
    ),
    EvolutionStage.ROOKIE: EvolutionRequirement(
        min_victories=8,
        min_bond=40,
        next_species="champion_form",
    ),
    EvolutionStage.CHAMPION: EvolutionRequirement(
        min_victories=15,
        min_bond=60,
        next_species="ultimate_form",
    ),
    EvolutionStage.ULTIMATE: EvolutionRequirement(
        min_victories=25,
        min_bond=100,
        next_species="mega_form",
    ),
    # MEGA 已是终态,无下一阶段
}


def is_final_stage(stage: EvolutionStage) -> bool:
    """判断是否已达最高阶段。"""
    return stage == EvolutionStage.MEGA


def next_stage(stage: EvolutionStage) -> Optional[EvolutionStage]:
    """返回下一阶段,若已是 MEGA 则返回 None。"""
    order = [
        EvolutionStage.BABY_I,
        EvolutionStage.BABY_II,
        EvolutionStage.ROOKIE,
        EvolutionStage.CHAMPION,
        EvolutionStage.ULTIMATE,
        EvolutionStage.MEGA,
    ]
    try:
        idx = order.index(stage)
    except ValueError:
        return None
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


# ----------------------------------------------------------------------------
# 进化结果 / 触发原因
# ----------------------------------------------------------------------------

class EvolutionReason(str, Enum):
    """进化触发原因。"""

    BATTLE_VICTORIES = "battle_victories"
    BOND = "bond"
    STORY_EVENT = "story_event"
    NOT_READY = "not_ready"
    ALREADY_MEGA = "already_mega"


@dataclass
class EvolutionResult:
    """一次进化操作的结果。"""

    evolved: bool
    old_stage: EvolutionStage
    new_stage: EvolutionStage
    reason: EvolutionReason
    next_species: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "evolved": self.evolved,
            "old_stage": self.old_stage.value,
            "new_stage": self.new_stage.value,
            "reason": self.reason.value,
            "next_species": self.next_species,
        }


# ----------------------------------------------------------------------------
# 进化系统主体
# ----------------------------------------------------------------------------

class EvolutionSystem:
    """数码兽进化系统。

    用法:
        evo = EvolutionSystem()
        result = evo.check_and_evolve(agent, battle_victories=5, bond=20)
        if result.evolved:
            # 庆祝!
    """

    def compute_bond(self, agent: DigimonAgent) -> int:
        """从记忆流累计羁绊值。

        简化算法: 累计所有记忆的 importance (1-10) 当作羁绊值。
        未来可换成 LLM 评估"这份记忆对我意义多大"。
        """
        return sum(m.importance for m in agent.memory.entries)

    def can_evolve(
        self,
        agent: DigimonAgent,
        battle_victories: int,
        bond: Optional[int] = None,
    ) -> tuple[bool, EvolutionReason]:
        """判断当前能否进化。

        Returns:
            (can_evolve, reason)
        """
        if is_final_stage(agent.stage):
            return False, EvolutionReason.ALREADY_MEGA

        req = EVOLUTION_CHAIN.get(agent.stage)
        if req is None:
            return False, EvolutionReason.NOT_READY

        actual_bond = bond if bond is not None else self.compute_bond(agent)

        if battle_victories >= req.min_victories and actual_bond >= req.min_bond:
            return True, EvolutionReason.BATTLE_VICTORIES
        if actual_bond >= req.min_bond * 2:
            # 羁绊值严重溢出也算触发 (纯羁绊路线)
            return True, EvolutionReason.BOND
        return False, EvolutionReason.NOT_READY

    def evolve(self, agent: DigimonAgent, reason: EvolutionReason) -> EvolutionResult:
        """实际执行进化: 改 stage / 改 species / 重置 stats / 写记忆。

        注意: 本方法直接修改 agent 状态。调用方应先 can_evolve() 判定。
        """
        old_stage = agent.stage
        target = next_stage(old_stage)
        if target is None:
            return EvolutionResult(
                evolved=False,
                old_stage=old_stage,
                new_stage=old_stage,
                reason=EvolutionReason.ALREADY_MEGA,
            )

        req = EVOLUTION_CHAIN[old_stage]
        new_species = req.next_species

        # ---- 升级数值 (每升一级 * 1.5 系数,简单粗暴) ----
        scale = 1.5
        old_stats = agent.stats
        new_stats = DigimonStats(
            hp=int(old_stats.hp * scale),
            max_hp=int(old_stats.max_hp * scale),
            ep=int(old_stats.ep * scale),
            max_ep=int(old_stats.max_ep * scale),
            attack=int(old_stats.attack * scale),
            defense=int(old_stats.defense * scale),
            speed=int(old_stats.speed * scale),
        )

        # ---- 修改 agent ----
        agent.stage = target
        agent.species = new_species
        agent.stats = new_stats

        # ---- 写一条进化记忆 (Phase 2 reflector 会感知到 importance=9) ----
        desc = (
            f"I evolved from {old_stage.value} to {target.value} "
            f"(new form: {new_species}, reason: {reason.value})"
        )
        agent.memory.add(
            event={"description": desc, "type": "evolution"},
            importance=9,
            memory_type="observation",
        )

        return EvolutionResult(
            evolved=True,
            old_stage=old_stage,
            new_stage=target,
            reason=reason,
            next_species=new_species,
        )

    def check_and_evolve(
        self,
        agent: DigimonAgent,
        battle_victories: int,
        bond: Optional[int] = None,
    ) -> EvolutionResult:
        """一站式: 判定 + 执行。

        Returns:
            EvolutionResult(evolved=True/False, ...)
        """
        can, reason = self.can_evolve(agent, battle_victories=battle_victories, bond=bond)
        if not can:
            return EvolutionResult(
                evolved=False,
                old_stage=agent.stage,
                new_stage=agent.stage,
                reason=reason,
            )
        return self.evolve(agent, reason=reason)


__all__ = [
    "EvolutionSystem",
    "EvolutionResult",
    "EvolutionReason",
    "EvolutionRequirement",
    "EVOLUTION_CHAIN",
    "is_final_stage",
    "next_stage",
]
"""
里程碑系统 - 数码兽成就/里程碑自动判定
========================================

基于数码兽的行为历史实时计算已达成的里程碑。
与徽章系统(badges.py)互补: 徽章是荣誉勋章,里程碑是成长记录。

当前里程碑:
- FIRST_BATTLE   — 完成第一场战斗(battle_victories >= 1)
- FIRST_EVOLUTION — 完成第一次进化(stage != ROOKIE 且 stage != BABY_*)
- HUNDRED_TICKS  — 存活 100 个世界 tick(memory 条目数 >= 100 作为代理指标)

设计要点:
- 纯函数式判定,不持久化状态 — 每次查询实时计算。
- 通过 memory entries 数量近似"存活 tick 数"(每 tick 至少产生一条记忆)。
- 未来可扩展: first_friend / first_spar / 100_battles 等。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .digimon_agent import DigimonAgent


class Milestone(str, Enum):
    """数码兽可达成的里程碑。"""

    FIRST_BATTLE = "first_battle"          # 第一场战斗胜利
    FIRST_EVOLUTION = "first_evolution"    # 第一次进化
    HUNDRED_TICKS = "100ticks"            # 存活 100 tick


# ---- 判定阈值 ----
FIRST_BATTLE_VICTORIES = 1
HUNDRED_TICKS_MEMORY_COUNT = 100


class AchievementSystem:
    """根据数码兽行为实时计算已达成的里程碑列表。

    用法:
        system = AchievementSystem()
        achievements = system.evaluate(agent)
    """

    def evaluate(self, agent: "DigimonAgent") -> list[dict[str, Any]]:
        """计算该数码兽当前满足条件的所有里程碑。

        Returns:
            列表,每项包含 milestone(枚举值)和 reason(达成原因)。
        """
        earned: list[dict[str, Any]] = []

        # FIRST_BATTLE: 至少赢过一场战斗
        if agent.battle_victories >= FIRST_BATTLE_VICTORIES:
            earned.append({
                "milestone": Milestone.FIRST_BATTLE.value,
                "reason": f"完成第一场战斗胜利(累计 {agent.battle_victories} 胜)",
            })

        # FIRST_EVOLUTION: 已经进化过(不再是初始低阶形态)
        if self._check_first_evolution(agent):
            earned.append({
                "milestone": Milestone.FIRST_EVOLUTION.value,
                "reason": f"已进化到 {agent.stage.value}",
            })

        # HUNDRED_TICKS: 记忆条目数 >= 100(每 tick 至少一条记忆)
        if self._check_hundred_ticks(agent):
            earned.append({
                "milestone": Milestone.HUNDRED_TICKS.value,
                "reason": f"存活超过 100 tick(记忆条目: {len(agent.memory.entries)})",
            })

        return earned

    def _check_first_evolution(self, agent: "DigimonAgent") -> bool:
        """检查是否已经历过至少一次进化。

        判定(满足其一即可):
        - 当前阶段为 CHAMPION / MEGA(必定进化过)
        - 记忆流中存在进化记忆(EvolutionSystem 写入 "I evolved from ...")
        """
        from .digimon_agent import EvolutionStage

        if agent.stage in {EvolutionStage.CHAMPION, EvolutionStage.MEGA}:
            return True

        for entry in agent.memory.entries:
            desc = entry.description if hasattr(entry, "description") else str(entry)
            if "evolved" in desc.lower() or "进化" in desc:
                return True

        return False

    def _check_hundred_ticks(self, agent: "DigimonAgent") -> bool:
        """检查是否存活超过 100 tick。

        使用 memory entries 数量作为代理指标:
        调度器每次 tick 至少为 agent 产生一条记忆(moved/ate/rested 等)。
        """
        return len(agent.memory.entries) >= HUNDRED_TICKS_MEMORY_COUNT

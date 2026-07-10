"""
里程碑系统 - 数码兽成就/里程碑自动判定
========================================

基于数码兽的行为历史实时计算已达成的里程碑。
与徽章系统(badges.py)互补: 徽章是荣誉勋章,里程碑是成长记录。

里程碑分类:
  社交:  FIRST_DIALOGUE — 完成第一次对话
  战斗:  FIRST_BATTLE → TEN_BATTLES — 战斗胜利递进
  进化:  FIRST_EVOLUTION — 完成第一次进化
  寿命:  HUNDRED_TICKS → FIVE_HUNDRED_TICKS — 存活时间递进

设计要点:
- 纯函数式判定,不持久化状态 — 每次查询实时计算。
- 通过 memory entries 数量近似"存活 tick 数"(每 tick 至少产生一条记忆)。
- 递进式里程碑: 达到高阶自动包含低阶(如 500 ticks 同时满足 100 ticks)。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .digimon_agent import DigimonAgent


class Milestone(str, Enum):
    """数码兽可达成的里程碑。

    按类别组织:
    - 社交: FIRST_DIALOGUE
    - 战斗: FIRST_BATTLE, TEN_BATTLES (10 胜)
    - 进化: FIRST_EVOLUTION
    - 寿命: HUNDRED_TICKS (100), FIVE_HUNDRED_TICKS (500)
    """

    # 社交
    FIRST_DIALOGUE = "first_dialogue"       # 第一次对话

    # 战斗
    FIRST_BATTLE = "first_battle"            # 第一场战斗胜利
    TEN_BATTLES = "10_battles"               # 累计 10 胜

    # 进化
    FIRST_EVOLUTION = "first_evolution"     # 第一次进化

    # 寿命
    HUNDRED_TICKS = "100ticks"              # 存活 100 tick
    FIVE_HUNDRED_TICKS = "500ticks"         # 存活 500 tick


# ---- 判定阈值 ----
FIRST_BATTLE_VICTORIES = 1
TEN_BATTLES_VICTORIES = 10
HUNDRED_TICKS_MEMORY_COUNT = 100
FIVE_HUNDRED_TICKS_MEMORY_COUNT = 500


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
            高阶里程碑自动包含低阶(如 500 ticks 也触发 100 ticks)。
        """
        earned: list[dict[str, Any]] = []

        memory_count = len(agent.memory.entries)

        # ---- 社交 ----
        # FIRST_DIALOGUE: 记忆中有对话/相遇记录
        if self._check_first_dialogue(agent):
            earned.append({
                "milestone": Milestone.FIRST_DIALOGUE.value,
                "reason": "完成了第一次对话,交到了第一个朋友",
            })

        # ---- 战斗 ----
        # FIRST_BATTLE: 至少赢过一场战斗
        if agent.battle_victories >= FIRST_BATTLE_VICTORIES:
            earned.append({
                "milestone": Milestone.FIRST_BATTLE.value,
                "reason": f"完成第一场战斗胜利(累计 {agent.battle_victories} 胜)",
            })

        # TEN_BATTLES: 至少赢过 10 场战斗
        if agent.battle_victories >= TEN_BATTLES_VICTORIES:
            earned.append({
                "milestone": Milestone.TEN_BATTLES.value,
                "reason": f"累计 {agent.battle_victories} 场战斗胜利,身经百战",
            })

        # ---- 进化 ----
        # FIRST_EVOLUTION: 已经进化过(不再是初始低阶形态)
        if self._check_first_evolution(agent):
            earned.append({
                "milestone": Milestone.FIRST_EVOLUTION.value,
                "reason": f"已进化到 {agent.stage.value}",
            })

        # ---- 寿命 ----
        # HUNDRED_TICKS: 记忆条目数 >= 100(每 tick 至少一条记忆)
        if memory_count >= HUNDRED_TICKS_MEMORY_COUNT:
            earned.append({
                "milestone": Milestone.HUNDRED_TICKS.value,
                "reason": f"存活超过 100 tick(记忆条目: {memory_count})",
            })

        # FIVE_HUNDRED_TICKS: 记忆条目数 >= 500
        if memory_count >= FIVE_HUNDRED_TICKS_MEMORY_COUNT:
            earned.append({
                "milestone": Milestone.FIVE_HUNDRED_TICKS.value,
                "reason": f"存活超过 500 tick(记忆条目: {memory_count}),世界老兵",
            })

        return earned

    def _check_first_dialogue(self, agent: "DigimonAgent") -> bool:
        """检查是否完成过至少一次对话。

        通过扫描记忆流中是否有对话/相遇记录来判定:
        - 事件 type 为 "first_meet" 或 "dialogue"
        - 描述中包含 "遇到" / "对话" / "说" 等关键词
        """
        for entry in agent.memory.entries:
            desc = entry.description if hasattr(entry, "description") else str(entry)
            desc_lower = desc.lower()
            if any(kw in desc_lower for kw in ("遇到", "对话", "说", "first_meet", "dialogue", "meet")):
                return True
        return False

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

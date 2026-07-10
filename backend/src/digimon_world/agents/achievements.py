"""
里程碑系统 - 数码兽成就/里程碑自动判定
========================================

基于数码兽的行为历史实时计算已达成的里程碑。
与徽章系统(badges.py)互补: 徽章是荣誉勋章,里程碑是成长记录。

里程碑分类:
  社交:  FIRST_DIALOGUE → SOCIAL_BUTTERFLY — 对话递进
  战斗:  FIRST_BATTLE → TEN_BATTLES → FIFTY_BATTLES — 战斗胜利递进
  进化:  FIRST_EVOLUTION — 完成第一次进化
  寿命:  HUNDRED_TICKS → FIVE_HUNDRED_TICKS — 存活时间递进
  探索:  EXPLORER — 访问过所有地标
  繁衍:  BREEDER — 成功繁衍后代

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
    SOCIAL_BUTTERFLY = "social_butterfly"   # 与 5+ 只不同数码兽对话过

    # 战斗
    FIRST_BATTLE = "first_battle"            # 第一场战斗胜利
    TEN_BATTLES = "10_battles"               # 累计 10 胜
    FIFTY_BATTLES = "50_battles"             # 累计 50 胜

    # 进化
    FIRST_EVOLUTION = "first_evolution"     # 第一次进化

    # 寿命
    HUNDRED_TICKS = "100ticks"              # 存活 100 tick
    FIVE_HUNDRED_TICKS = "500ticks"         # 存活 500 tick

    # 探索
    EXPLORER = "explorer"                   # 访问过所有主要地标

    # 繁衍
    BREEDER = "breeder"                     # 成功繁衍后代


# ---- 判定阈值 ----
FIRST_BATTLE_VICTORIES = 1
TEN_BATTLES_VICTORIES = 10
FIFTY_BATTLES_VICTORIES = 50
SOCIAL_BUTTERFLY_MIN_UNIQUE = 5
HUNDRED_TICKS_MEMORY_COUNT = 100
FIVE_HUNDRED_TICKS_MEMORY_COUNT = 500

# 探索: 核心地标列表(来自 landmarks.py 初始数据)
EXPLORER_CORE_LANDMARKS = {"创始村", "无限山", "齿轮草原", "密哈拉西山"}


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

        # SOCIAL_BUTTERFLY: 与 5+ 只不同数码兽对话过
        if self._check_social_butterfly(agent):
            earned.append({
                "milestone": Milestone.SOCIAL_BUTTERFLY.value,
                "reason": "与 5 只以上数码兽对话过,社交达人",
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

        # FIFTY_BATTLES: 至少赢过 50 场战斗
        if agent.battle_victories >= FIFTY_BATTLES_VICTORIES:
            earned.append({
                "milestone": Milestone.FIFTY_BATTLES.value,
                "reason": f"累计 {agent.battle_victories} 场战斗胜利,战斗大师",
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

        # ---- 探索 ----
        # EXPLORER: 访问过所有核心地标
        if self._check_explorer(agent):
            earned.append({
                "milestone": Milestone.EXPLORER.value,
                "reason": "探索了文件岛所有主要地标,冒险家",
            })

        # ---- 繁衍 ----
        # BREEDER: 成功繁衍后代
        if self._check_breeder(agent):
            earned.append({
                "milestone": Milestone.BREEDER.value,
                "reason": "成功繁衍了后代,生命的延续",
            })

        return earned

    def _check_first_dialogue(self, agent: "DigimonAgent") -> bool:
        """检查是否完成过至少一次对话。

        通过扫描记忆流中是否有对话/相遇记录来判定:
        - 事件 type 为 "first_meet" 或 "dialogue"
        - 描述中包含 "遇到" / "对话" / "说" / "相遇" / "交朋友" 等关键词
        """
        for entry in agent.memory.entries:
            desc = entry.description if hasattr(entry, "description") else str(entry)
            desc_lower = desc.lower()
            if any(kw in desc_lower for kw in ("遇到", "对话", "说", "相遇", "交朋友", "聊天", "招呼",
                                                 "first_meet", "dialogue", "meet")):
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

    def _check_social_butterfly(self, agent: "DigimonAgent") -> bool:
        """检查是否与 5+ 只不同数码兽对话过。

        通过扫描记忆流中对话/相遇记录,在描述中提取数码兽名字来判定。
        """
        unique_partners: set[str] = set()
        known_names = ["加布兽", "比丘兽", "巴达兽", "甲虫兽", "迪路兽", "哥玛兽", "巴鲁兽",
                       "Gabumon", "Biyomon", "Patamon", "Tentomon", "Gatomon", "Gomamon", "Palmon"]
        for entry in agent.memory.entries:
            desc = entry.description if hasattr(entry, "description") else str(entry)
            desc_lower = desc.lower()
            if not any(kw in desc_lower for kw in ("遇到", "对话", "说", "相遇", "交朋友", "聊天", "招呼",
                                                     "first_meet", "dialogue", "meet")):
                continue
            for name in known_names:
                if name in desc and name != agent.name:
                    unique_partners.add(name)
        return len(unique_partners) >= SOCIAL_BUTTERFLY_MIN_UNIQUE

    def _check_explorer(self, agent: "DigimonAgent") -> bool:
        """检查是否访问过所有核心地标。

        通过扫描记忆流描述中是否提到各地标名来判定。
        """
        visited_regions: set[str] = set()
        for entry in agent.memory.entries:
            desc = entry.description if hasattr(entry, "description") else str(entry)
            for landmark in EXPLORER_CORE_LANDMARKS:
                if landmark in desc:
                    visited_regions.add(landmark)
        return EXPLORER_CORE_LANDMARKS.issubset(visited_regions)

    def _check_breeder(self, agent: "DigimonAgent") -> bool:
        """检查是否成功繁衍过后代。

        通过扫描记忆流中繁殖事件来判定(breeding 事件会写入
        "gave birth to" 或 "produced an egg" 等描述)。
        """
        for entry in agent.memory.entries:
            desc = entry.description if hasattr(entry, "description") else str(entry)
            desc_lower = desc.lower()
            if any(kw in desc_lower for kw in ("gave birth", "produced an egg", "egg hatched",
                                                 "繁衍", "产蛋", "孵化", "breeding")):
                return True
        return False

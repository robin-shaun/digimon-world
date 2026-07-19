"""
徽章系统 - 数码兽成就/徽章自动授予
=====================================

基于数码兽的行为历史自动判定是否获得对应徽章。
徽章对应「被选召的孩子」七大纹章:

- COURAGE    (勇气)  — 战斗胜利 > 10
- FRIENDSHIP (友情)  — 与任一数码兽关系分 > 90
- LOVE       (爱心)  — 预留(Phase 6: 照顾行为累计)
- KNOWLEDGE  (知识)  — 探索过全部地图区域
- SINCERITY  (诚实)  — 预留(Phase 6: 从不逃跑)
- HOPE       (希望)  — 进化到 champion 或以上
- LIGHT      (光明)  — 预留(Phase 6: 全徽章集齐后点亮)

设计要点:
- 纯函数式判定,不持久化徽章状态 — 每次查询实时计算。
- 需要外部传入关系分数(RelationshipTracker)和世界地图信息(WorldState)。
- 未来可扩展为带时间戳的授予记录。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..world.relationships import RelationshipTracker
    from ..world.world_state import WorldState
    from .digimon_agent import DigimonAgent


class Badge(StrEnum):
    """数码兽可获得的七大徽章。"""

    COURAGE = "courage"          # 勇气
    FRIENDSHIP = "friendship"    # 友情
    LOVE = "love"                # 爱心
    KNOWLEDGE = "knowledge"      # 知识
    SINCERITY = "sincerity"      # 诚实
    HOPE = "hope"                # 希望
    LIGHT = "light"              # 光明


# ---- 判定阈值 ----
COURAGE_VICTORIES_THRESHOLD = 10
FRIENDSHIP_SCORE_THRESHOLD = 90


class BadgeSystem:
    """根据数码兽行为实时计算已获得的徽章列表。

    用法:
        system = BadgeSystem(world, tracker)
        badges = system.evaluate(agent)
    """

    def __init__(
        self,
        world: WorldState,
        tracker: RelationshipTracker,
    ) -> None:
        self._world = world
        self._tracker = tracker

    def evaluate(self, agent: DigimonAgent) -> list[dict[str, Any]]:
        """计算该数码兽当前满足条件的所有徽章。

        Returns:
            列表,每项包含 badge(枚举值)和 reason(授予原因)。
        """
        earned: list[dict[str, Any]] = []

        # COURAGE: 战斗胜利 > 10
        if agent.battle_victories > COURAGE_VICTORIES_THRESHOLD:
            earned.append({
                "badge": Badge.COURAGE.value,
                "reason": f"战斗胜利 {agent.battle_victories} 次(阈值 {COURAGE_VICTORIES_THRESHOLD})",
            })

        # FRIENDSHIP: 与任一数码兽关系分 > 90
        if self._check_friendship(agent):
            earned.append({
                "badge": Badge.FRIENDSHIP.value,
                "reason": f"与某只数码兽关系分超过 {FRIENDSHIP_SCORE_THRESHOLD}",
            })

        # HOPE: 进化到 champion 或以上
        if self._check_hope(agent):
            earned.append({
                "badge": Badge.HOPE.value,
                "reason": f"已进化到 {agent.stage.value}",
            })

        # KNOWLEDGE: 探索过全部地图区域
        if self._check_knowledge(agent):
            earned.append({
                "badge": Badge.KNOWLEDGE.value,
                "reason": "已探索全部地图区域",
            })

        return earned

    def _check_friendship(self, agent: DigimonAgent) -> bool:
        """检查是否有任一关系分超过阈值。"""
        pairs = self._tracker.all_pairs()
        for pair in pairs:
            if agent.name in (pair.get("a"), pair.get("b")):
                score = pair.get("score", 0)
                if score > FRIENDSHIP_SCORE_THRESHOLD:
                    return True
        return False

    def _check_hope(self, agent: DigimonAgent) -> bool:
        """进化到 champion 或以上即获得 HOPE。"""
        from .digimon_agent import EvolutionStage

        advanced_stages = {
            EvolutionStage.CHAMPION,
            EvolutionStage.ULTIMATE,
            EvolutionStage.MEGA,
        }
        return agent.stage in advanced_stages

    def _check_knowledge(self, agent: DigimonAgent) -> bool:
        """检查是否探索过全部地图区域。

        通过遍历记忆流中的描述,匹配已知 region_id,
        与世界地图全部 region 对比。
        """
        all_regions = set(self._world.regions.keys())
        if not all_regions:
            return False

        # 当前所在区域
        visited: set[str] = {agent.region_id}

        # 遍历记忆描述,匹配已知区域名
        for entry in agent.memory.entries:
            desc = entry.description if hasattr(entry, "description") else str(entry)
            for region_id in all_regions:
                if region_id in desc:
                    visited.add(region_id)

        return visited >= all_regions

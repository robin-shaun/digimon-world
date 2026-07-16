"""
情感传播引擎 — AffectPropagationEngine
=======================================

当某数码兽情绪剧烈变化时，按关系距离衰减传播给圈内其他数码兽。

基于差序格局 (Differential Mode of Association) 理论:
- 情绪在亲密关系中强传播 (intimate factor=0.8)
- 在疏远关系中弱传播或阻断 (stranger factor=0.0)

参考:
- Fei Xiaotong, "From the Soil" (乡土中国)
- Hatfield, Cacioppo & Rapson (1993), "Emotional Contagion"
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from digimon_world.world.relational_circle import (
    AffectVector,
    RelationalCircle,
    RelationalDistance,
)

if TYPE_CHECKING:
    from digimon_world.world.world_state import WorldState

logger = logging.getLogger(__name__)

# 情绪剧变阈值: mood_state 任一维度变化超过此值即触发传播
CPM_CHANGE_THRESHOLD = 0.3

# 圈层 → 传播因子映射
_CIRCLE_PROPAGATION_FACTOR: dict[RelationalCircle, float] = {
    RelationalCircle.INTIMATE: 0.8,
    RelationalCircle.FRIENDLY: 0.6,
    RelationalCircle.ACQUAINTANCE: 0.3,
    RelationalCircle.NEUTRAL: 0.1,
    RelationalCircle.HOSTILE: 0.0,
}

# 圈层 → 距离标签映射
_DISTANCE_LABELS: dict[RelationalCircle, str] = {
    RelationalCircle.INTIMATE: "intimate",
    RelationalCircle.FRIENDLY: "close",
    RelationalCircle.ACQUAINTANCE: "acquaintance",
    RelationalCircle.NEUTRAL: "outsider",
    RelationalCircle.HOSTILE: "stranger",
}


class AffectPropagationEngine:
    """情感传播引擎 — 当某数码兽情绪剧烈变化时，按关系距离衰减传播。

    典型用法::

        engine = AffectPropagationEngine()
        # 检测到 source_agent 的情绪剧变
        affect = engine.mood_to_affect(source_agent)
        results = engine.propagate("亚古兽", affect, world, relationship_tracker)
        for r in results:
            print(f"{r['name']}: distance={r['distance']}, factor={r['factor']}")
    """

    def __init__(self) -> None:
        # 记录每个 agent 上一 tick 的 mood_state, 用于检测剧变
        self._prev_moods: dict[str, dict[str, float]] = {}

    def snapshot_moods(self, world: "WorldState") -> None:
        """在每个 tick 开始前, 快照所有 agent 的当前 mood_state。

        应放在 _step_agent 之前调用, 以便后续 detect_changes() 能对比。
        """
        for agent in world.all():
            self._prev_moods[agent.name] = dict(agent.mood_state)

    def detect_changes(self, world: "WorldState") -> list[tuple[str, dict[str, float]]]:
        """检测本 tick 中有哪些 agent 的情绪发生了剧变。

        Returns:
            [(agent_name, mood_delta_dict), ...] 情绪变化超过阈值的 agent 列表。
            mood_delta_dict 的维度为 joy/sadness/anger/fear。
        """
        changed: list[tuple[str, dict[str, float]]] = []
        for agent in world.all():
            prev = self._prev_moods.get(agent.name, {})
            curr = agent.mood_state
            delta = {}
            has_big_change = False
            for dim in ("joy", "sadness", "anger", "fear"):
                prev_val = prev.get(dim, 0.0)
                curr_val = curr.get(dim, 0.0)
                d = curr_val - prev_val
                delta[dim] = d
                if abs(d) >= CPM_CHANGE_THRESHOLD:
                    has_big_change = True
            if has_big_change:
                changed.append((agent.name, delta))
        return changed

    @staticmethod
    def mood_to_affect(agent) -> AffectVector:
        """将 agent 的 CPM mood_state (joy/sadness/anger/fear) 映射为 AffectVector。

        映射规则:
        - trust     ← joy (喜悦提升信任感)
        - affection ← max(joy, 1-sadness) (喜悦和低悲伤代表喜爱)
        - respect   ← 0.5 (默认中立, 当前没有直接映射)
        - fear      ← fear (直接从 mood_state 传递)
        """
        ms = agent.mood_state
        joy = ms.get("joy", 0.0)
        sadness = ms.get("sadness", 0.0)
        fear_val = ms.get("fear", 0.0)
        return AffectVector(
            trust=max(0.0, min(1.0, joy)),
            affection=max(0.0, min(1.0, max(joy, 1.0 - sadness))),
            respect=0.5,
            fear=max(0.0, min(1.0, fear_val)),
        )

    @staticmethod
    def _apply_affect_to_mood(
        agent, affect_delta: AffectVector, factor: float
    ) -> dict[str, float]:
        """将衰减后的 AffectVector 应用到 agent 的 mood_state。

        映射回 mood_state:
        - joy      ← (trust_delta + affection_delta) / 2 * factor
        - sadness  ← -affection_delta * factor * 0.5 (高喜爱度降低悲伤)
        - anger    ← 0 (AffectVector 没有直接映射)
        - fear     ← fear_delta * factor

        Returns:
            实际应用的 mood delta。
        """
        joy_delta = ((affect_delta.trust + affect_delta.affection) / 2.0) * factor
        sadness_delta = -affect_delta.affection * factor * 0.5
        fear_delta = affect_delta.fear * factor

        ms = agent.mood_state
        applied: dict[str, float] = {}
        for dim, d in [("joy", joy_delta), ("sadness", sadness_delta), ("fear", fear_delta)]:
            current = ms.get(dim, 0.0)
            new_val = max(0.0, min(1.0, current + d))
            ms[dim] = new_val
            applied[dim] = d

        # anger 维度保持 (AffectVector 当前不映射 anger)
        applied["anger"] = 0.0
        return applied

    def propagate(
        self,
        source_name: str,
        affect: AffectVector,
        world: "WorldState",
        tracker=None,
    ) -> list[dict]:
        """传播情感到圈内其他数码兽。

        Args:
            source_name: 情绪源 agent 名称。
            affect: 源 agent 的情感染色向量。
            world: 世界状态, 提供所有 agent。
            tracker: RelationshipTracker 实例, 用于创建 RelationalDistance。

        Returns:
            受影响列表: [{"name": "加布兽", "affect_delta": {...}, "distance": "intimate", "factor": 0.8}, ...]
        """
        if tracker is None:
            from digimon_world.world.relationships import get_tracker
            tracker = get_tracker()

        source_agent = world.get(source_name)
        if source_agent is None:
            logger.warning("propagate: source agent '%s' not found in world", source_name)
            return []

        rd = RelationalDistance(source_name, tracker)
        results: list[dict] = []

        for target in world.all():
            if target.name == source_name:
                continue  # 不传播给自己

            circle = rd.classify(target.name)
            factor = _CIRCLE_PROPAGATION_FACTOR.get(circle, 0.0)

            if factor <= 0.0:
                continue  # stranger 完全阻断

            affect_delta = self._apply_affect_to_mood(target, affect, factor)

            results.append({
                "name": target.name,
                "affect_delta": affect_delta,
                "distance": _DISTANCE_LABELS.get(circle, "unknown"),
                "factor": factor,
            })

        if results:
            logger.debug(
                "propagate: %s → %d agents affected (affect trust=%.2f)",
                source_name, len(results), affect.trust,
            )

        return results

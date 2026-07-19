"""
差序格局 (Differential Mode of Association) — 关系圈层系统
=========================================================

基于 Fei Xiaotong 的"差序格局"理论,将数码兽之间的关系按亲疏远近
分为五个同心圆层级。

参考:
- Fei Xiaotong, "From the Soil: The Foundations of Chinese Society" (乡土中国)
- ACL 2026 arXiv:2606.23764 "Emergent Relational Order in LLM Agent Societies"

与现有 RelationshipTracker 集成: 读取 get_composite_score() 的四维加权得分,
按阈值映射到圈层。本模块为只读分类层,不修改任何现有关系数据。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from digimon_world.world.relationships import RelationshipTracker, RelationshipVector


# ---- 圈层枚举 ----

class RelationalCircle(Enum):
    """五个关系圈层,从内到外亲密度递减。

    INTIMATE  —— 最内层: 挚友、伴侣、至亲
    FRIENDLY  —— 好友、可靠伙伴
    ACQUAINTANCE — 认识、点头之交
    NEUTRAL   —— 陌生人、无感
    HOSTILE   —— 敌人、对立
    """

    INTIMATE = 0
    FRIENDLY = 1
    ACQUAINTANCE = 2
    NEUTRAL = 3
    HOSTILE = 4

    def label_cn(self) -> str:
        """返回圈层中文标签。"""
        _labels = {
            RelationalCircle.INTIMATE: "至交",
            RelationalCircle.FRIENDLY: "友好",
            RelationalCircle.ACQUAINTANCE: "相识",
            RelationalCircle.NEUTRAL: "中立",
            RelationalCircle.HOSTILE: "敌对",
        }
        return _labels[self]

    def distance_value(self) -> float:
        """返回圈层对应的归一化距离值 (0=最亲密, 1=最疏远)。"""
        _distances = {
            RelationalCircle.INTIMATE: 0.0,
            RelationalCircle.FRIENDLY: 0.25,
            RelationalCircle.ACQUAINTANCE: 0.5,
            RelationalCircle.NEUTRAL: 0.75,
            RelationalCircle.HOSTILE: 1.0,
        }
        return _distances[self]

    @classmethod
    def from_composite(cls, composite: float) -> RelationalCircle:
        """根据综合关系得分判定圈层。

        阈值规则:
        - INTIMATE:      composite >= 20
        - FRIENDLY:      composite >= 8
        - ACQUAINTANCE:  composite >= 2
        - NEUTRAL:       composite > -5
        - HOSTILE:       composite <= -5
        """
        if composite >= 20:
            return cls.INTIMATE
        elif composite >= 8:
            return cls.FRIENDLY
        elif composite >= 2:
            return cls.ACQUAINTANCE
        elif composite > -5:
            return cls.NEUTRAL
        else:
            return cls.HOSTILE


# ---- 情感向量 ----

class AffectVector:
    """多维情感追踪: agent 对另一个 agent 的情感状态。

    四个维度均为 0–1 归一化值:
    - trust:     信任度
    - affection: 喜爱度
    - respect:   尊重度
    - fear:      恐惧度

    与 RelationshipVector 的区别: AffectVector 是归一化的行为驱动情感,
    而 RelationshipVector 是原始累积值。AffectVector 从后者派生而来。
    """

    __slots__ = ("affection", "fear", "respect", "trust")

    def __init__(
        self,
        trust: float = 0.5,
        affection: float = 0.5,
        respect: float = 0.5,
        fear: float = 0.0,
    ) -> None:
        self.trust = max(0.0, min(1.0, trust))
        self.affection = max(0.0, min(1.0, affection))
        self.respect = max(0.0, min(1.0, respect))
        self.fear = max(0.0, min(1.0, fear))

    def propagate(self, rel_distance: float) -> AffectVector:
        """情感随关系距离衰减传播。

        距离越远,情感传递越弱。衰减因子 = 1 - rel_distance。
        rel_distance=0 (至交) → 完全传递; rel_distance=1 (敌对) → 完全阻断。

        Args:
            rel_distance: 关系距离 0.0–1.0。

        Returns:
            衰减后的新 AffectVector。
        """
        factor = max(0.0, min(1.0, 1.0 - rel_distance))
        return AffectVector(
            trust=self.trust * factor,
            affection=self.affection * factor,
            respect=self.respect * factor,
            fear=self.fear * factor,
        )

    def intensity(self) -> float:
        """返回情感总强度 (四个维度的均方根)。"""
        return (
            (self.trust ** 2 + self.affection ** 2 + self.respect ** 2 + self.fear ** 2) / 4
        ) ** 0.5

    def to_dict(self) -> dict[str, float]:
        return {
            "trust": self.trust,
            "affection": self.affection,
            "respect": self.respect,
            "fear": self.fear,
        }

    @classmethod
    def from_relationship_vector(cls, rv: RelationshipVector) -> AffectVector:
        """从 RelationshipVector 派生出归一化的 AffectVector。

        映射规则:
        - trust  ← (affinity + 100) / 200 (亲和度映射到 0–1)
        - affection ← same as trust,但 rivalry 高时打折
        - respect ← respect / 100
        - fear   ← fear / 100
        """
        trust = (rv.affinity + 100.0) / 200.0
        # rivalry 高 → 喜爱度打折
        rivalry_penalty = 1.0 - (rv.rivalry / 200.0)  # rivalry 0→1.0, 100→0.5
        affection = trust * max(0.1, rivalry_penalty)
        return cls(
            trust=trust,
            affection=affection,
            respect=rv.respect / 100.0,
            fear=rv.fear / 100.0,
        )

    @classmethod
    def neutral(cls) -> AffectVector:
        """返回完全中立的默认情感向量。"""
        return cls(trust=0.5, affection=0.5, respect=0.5, fear=0.0)


# ---- 关系距离 ----

# 圈层 → 基础合作意愿
_CIRCLE_COOPERATION_BASE: dict[RelationalCircle, float] = {
    RelationalCircle.INTIMATE: 0.95,
    RelationalCircle.FRIENDLY: 0.75,
    RelationalCircle.ACQUAINTANCE: 0.50,
    RelationalCircle.NEUTRAL: 0.20,
    RelationalCircle.HOSTILE: 0.05,
}


class RelationalDistance:
    """单个 agent 对其他所有 agent 的关系距离视图。

    维护 agent_id → (RelationalCircle, distance_value) 的映射,
    基于 RelationshipTracker 的复合得分进行分类。只读,不修改任何关系。

    用法::

        from digimon_world.world.relationships import get_tracker
        from digimon_world.world.relational_circle import RelationalDistance

        tracker = get_tracker()
        rd = RelationalDistance("Agumon", tracker)
        circle = rd.get_circle("Gabumon")       # → RelationalCircle.FRIENDLY
        dist = rd.get_relation_distance("Gabumon")  # → 0.25
        coop = rd.compute_cooperation_threshold("Gabumon", task_risk=0.3)  # → ~0.75
    """

    __slots__ = ("_agent_id", "_cache", "_tracker")

    def __init__(self, agent_id: str, tracker: RelationshipTracker) -> None:
        self._agent_id = agent_id
        self._tracker = tracker
        # agent_id → (RelationalCircle, distance_value)
        self._cache: dict[str, tuple[RelationalCircle, float]] = {}

    def _compute(self, target_id: str) -> tuple[RelationalCircle, float]:
        """计算并缓存对 target_id 的圈层和距离。"""
        composite = self._tracker.get_composite_score(self._agent_id, target_id)
        circle = RelationalCircle.from_composite(composite)
        distance = self._composite_to_distance(composite)
        self._cache[target_id] = (circle, distance)
        return (circle, distance)

    @staticmethod
    def _composite_to_distance(composite: float) -> float:
        """将复合得分映射到 0.0–1.0 的归一化距离。

        映射采用分段线性: composite 从 40 (极亲密) → 0.0, 到 -40 (极敌对) → 1.0。
        """
        # composite 理论范围约 [-40, 40], 钳制到该区间
        clamped = max(-40.0, min(40.0, composite))
        # 线性映射: clamped=40 → 0.0, clamped=-40 → 1.0
        distance = (40.0 - clamped) / 80.0
        return round(distance, 4)

    # ---- 公共 API ----

    def get_circle(self, target_id: str) -> RelationalCircle:
        """获取 self 对 target_id 的关系圈层。

        如果目标是自己,返回 INTIMATE。
        """
        if target_id == self._agent_id:
            return RelationalCircle.INTIMATE
        cached = self._cache.get(target_id)
        if cached is not None:
            return cached[0]
        circle, _ = self._compute(target_id)
        return circle

    def get_relation_distance(self, target_id: str) -> float:
        """获取 self 对 target_id 的归一化关系距离 (0=至交, 1=敌对)。

        如果目标是自己,返回 0.0。
        """
        if target_id == self._agent_id:
            return 0.0
        cached = self._cache.get(target_id)
        if cached is not None:
            return cached[1]
        _, distance = self._compute(target_id)
        return distance

    def classify(
        self, target_id: str, relationship_vector: RelationshipVector | None = None
    ) -> RelationalCircle:
        """判定 target_id 属于哪个圈层。

        优先使用传入的 relationship_vector 直接计算;
        若为 None,则从 tracker 获取复合得分后分类。

        Args:
            target_id: 目标 agent ID。
            relationship_vector: 可选的四维关系向量,用于直接分类。

        Returns:
            对应的 RelationalCircle。
        """
        if target_id == self._agent_id:
            return RelationalCircle.INTIMATE

        if relationship_vector is not None:
            # 直接从 RelationshipVector 计算复合得分
            composite = (
                relationship_vector.affinity * 0.4
                - relationship_vector.rivalry * 0.25
                + relationship_vector.respect * 0.2
                - relationship_vector.fear * 0.15
            )
        else:
            composite = self._tracker.get_composite_score(self._agent_id, target_id)

        return RelationalCircle.from_composite(composite)

    def compute_cooperation_threshold(
        self, target_id: str, task_risk: float
    ) -> float:
        """计算与 target_id 合作某任务的意愿阈值 (0–1)。

        合作意愿取决于两个因素:
        1. 基础圈层合作度 (INTIMATE=0.95, FRIENDLY=0.75, ... HOSTILE=0.05)
        2. 任务风险惩罚: 高风险任务只有内圈才愿意合作

        Args:
            target_id: 目标 agent ID。
            task_risk: 任务风险 0–1 (0=无风险, 1=极高风险)。

        Returns:
            合作意愿概率 0–1。
        """
        circle = self.get_circle(target_id)
        base = _CIRCLE_COOPERATION_BASE.get(circle, 0.0)

        # 风险惩罚: 圈层越远惩罚越重
        circle_penalty = circle.distance_value()  # 0.0 (INTIMATE) → 1.0 (HOSTILE)
        risk_penalty = task_risk * circle_penalty * 0.8

        willingness = max(0.0, min(1.0, base - risk_penalty))
        return round(willingness, 4)

    def get_affect_vector(self, target_id: str) -> AffectVector:
        """获取 self 对 target_id 的归一化情感向量。

        从 tracker 的 RelationshipVector 派生。
        """
        if target_id == self._agent_id:
            return AffectVector(trust=1.0, affection=1.0, respect=1.0, fear=0.0)

        rv = self._tracker.get_vector(self._agent_id, target_id)
        return AffectVector.from_relationship_vector(rv)

    def invalidate_cache(self, target_id: str | None = None) -> None:
        """清除缓存。

        Args:
            target_id: 如果提供,仅清除该 target; 否则清空全部缓存。
        """
        if target_id is None:
            self._cache.clear()
        else:
            self._cache.pop(target_id, None)

    def all_circles(self) -> dict[str, RelationalCircle]:
        """获取所有已知 agent 的圈层映射。

        注意: 仅返回 tracker 中存在关系记录的 agent。
        """
        result: dict[str, RelationalCircle] = {}
        for (a, b), _v in self._tracker._vectors.items():
            other = b if a == self._agent_id else (a if b == self._agent_id else None)
            if other is not None:
                result[other] = self.get_circle(other)
        return result

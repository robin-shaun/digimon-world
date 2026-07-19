"""
人格动力学 (Personality Dynamics) — 社会影响 + 人格向量 + 演化追踪
================================================================

基于 personality_engine.py 的 PersonalityEvolutionEngine / PersonalityProfile /
MbtiDimension，构建三层新系统：

1. SocialInfluence — 追踪 agent 间互动对人格的社会影响力
2. PersonalityVector — 增强人格向量（含稳定性 / 漂移追踪 / 轨迹）
3. PersonalityDynamicsEngine — 人格演化引擎（记录互动、检测重大 shift）

核心设计：
- 纯算法 / dataclass / 单例模式，不调 LLM
- 对齐 personality_engine.py 的 API 惯例
- 可选依赖 Phase 24 economy 模块（ReciprocalAltruism 债务影响 influence_factor）
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Phase 24 economy 可选依赖 — ReciprocalAltruism 债务影响 influence_factor
# ---------------------------------------------------------------------------
try:
    from digimon_world.economy.energy_economy import ReciprocalAltruism as _ReciprocalAltruism

    _HAS_ECONOMY = True
except ImportError:
    _ReciprocalAltruism = None  # type: ignore[assignment]
    _HAS_ECONOMY = False

from .personality_engine import (
    MbtiDimension,
    PersonalityEvolutionEngine,
    PersonalityProfile,
    get_personality_engine,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 互动类型基础漂移向量（对 influenced 方的维度影响）
INTERACTION_BASE_VECTORS: dict[str, dict[str, float]] = {
    "dialogue": {"ei": 0.02, "sn": 0.00, "tf": -0.01, "jp": 0.00},
    "battle":   {"ei": 0.01, "sn": 0.00, "tf": 0.02,  "jp": 0.01},
    "help":     {"ei": 0.01, "sn": 0.00, "tf": -0.02, "jp": 0.00},
    "trade":    {"ei": 0.00, "sn": 0.01, "tf": 0.00,  "jp": -0.01},
    "gift":     {"ei": 0.00, "sn": -0.01, "tf": -0.01, "jp": 0.00},
    "wakeup":   {"ei": 0.02, "sn": 0.00, "tf": -0.01, "jp": 0.00},
}

# 稳定性计算：最近 N 次漂移的标准差窗口
_STABILITY_WINDOW: int = 10

# 重大转变检测：漂移距离阈值
_SHIFT_DRIFT_THRESHOLD: float = 0.3

# 默认 influence_factor（无债务时）
_DEFAULT_INFLUENCE_FACTOR: float = 1.0

# 债务归一化上限（与 energy_economy.MAX_DEBT 对齐）
_MAX_DEBT_NORMALIZE: float = 50.0

# 人格向量维度
_DIMS: list[str] = ["ei", "sn", "tf", "jp"]


# ===========================================================================
# 1. SocialInfluence — 社会影响力记录
# ===========================================================================

@dataclass
class SocialInfluenceRecord:
    """单条社会影响力记录。

    记录一次互动中 influencer 对 influenced 的人格维度的具体影响。
    """

    influencer_name: str
    """施加影响者。"""

    influenced_name: str
    """被影响者。"""

    interaction_type: str
    """互动类型: dialogue / battle / help / trade / gift / wakeup。"""

    magnitude: float
    """互动强度 [0, 1]（如战斗烈度、对话深度）。"""

    dimension_shifts: dict[str, float]
    """各维度偏移: ei/sn/tf/jp → float（实际施加到向量上的量）。"""

    tick: int
    """World tick。"""

    timestamp: str = ""
    """ISO 时间戳。"""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class SocialInfluenceTracker:
    """社会影响力追踪器。

    存储所有 SocialInfluenceRecord，提供查询 / 网络分析能力。
    """

    _records: list[SocialInfluenceRecord] = field(default_factory=list)

    def add_record(self, record: SocialInfluenceRecord) -> None:
        """添加一条影响力记录。"""
        self._records.append(record)
        logger.debug(
            "SocialInfluence: %s → %s (%s, mag=%.2f, shifts=%s)",
            record.influencer_name,
            record.influenced_name,
            record.interaction_type,
            record.magnitude,
            record.dimension_shifts,
        )

    def get_influences_on(self, agent_name: str) -> list[SocialInfluenceRecord]:
        """获取对指定 agent 的所有影响力记录（按时间先后排列）。"""
        return [r for r in self._records if r.influenced_name == agent_name]

    def get_influences_by(self, agent_name: str) -> list[SocialInfluenceRecord]:
        """获取指定 agent 施加的所有影响力记录。"""
        return [r for r in self._records if r.influencer_name == agent_name]

    def get_influence_network(self) -> dict[str, dict[str, float]]:
        """获取 agent 间影响力矩阵。

        Returns:
            {influencer: {influenced: total_impact, ...}, ...}
            其中 total_impact 为该方向所有互动 magnitude 之和。
        """
        network: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for r in self._records:
            network[r.influencer_name][r.influenced_name] += r.magnitude
        # 转回普通 dict
        return {k: dict(v) for k, v in network.items()}

    def get_top_influencers(self, agent_name: str, n: int = 5) -> list[tuple[str, float]]:
        """获取对 agent_name 影响最大的前 n 个 agent。

        Returns:
            [(influencer_name, total_magnitude), ...] 按总影响力降序排列。
        """
        totals: dict[str, float] = defaultdict(float)
        for r in self._records:
            if r.influenced_name == agent_name:
                totals[r.influencer_name] += r.magnitude

        sorted_influencers = sorted(totals.items(), key=lambda x: x[1], reverse=True)
        return sorted_influencers[:n]

    def get_interaction_count(self, agent_a: str, agent_b: str) -> int:
        """获取两 agent 间的互动次数（双向）。"""
        count = 0
        for r in self._records:
            if (r.influencer_name == agent_a and r.influenced_name == agent_b) or \
               (r.influencer_name == agent_b and r.influenced_name == agent_a):
                count += 1
        return count

    def clear(self) -> None:
        """清空所有记录（测试用）。"""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


# ===========================================================================
# 2. PersonalityVector — 增强人格向量
# ===========================================================================

@dataclass
class PersonalitySnapshot:
    """人格向量在某一时刻的快照（用于轨迹追踪）。"""

    tick: int
    ei: float
    sn: float
    tf: float
    jp: float
    mbti_type: str


@dataclass
class PersonalityVector:
    """增强人格向量 — 四维 MBTI 连续值 + 稳定性 + 漂移 + 轨迹。

    每个维度值范围 [-1.0, 1.0]，正值 = 第一极 (E/S/T/J)，负值 = 第二极 (I/N/F/P)。
    """

    ei: float = 0.0
    """外倾/内倾。"""

    sn: float = 0.0
    """感觉/直觉。"""

    tf: float = 0.0
    """思考/情感。"""

    jp: float = 0.0
    """判断/感知。"""

    stability_score: float = 1.0
    """稳定性 [0, 1] — 越高越稳定（近期漂移标准差小）。"""

    drift_total: float = 0.0
    """累积漂移总量（所有 shift 欧几里得距离之和）。"""

    original_type: str = ""
    """初始 MBTI 类型字符串。"""

    original_values: dict[str, float] = field(default_factory=dict)
    """初始四维值 {ei/sn/tf/jp: float}。"""

    # -- 内部追踪 --
    _recent_shift_magnitudes: list[float] = field(default_factory=list)
    """最近 N 次漂移的欧几里得距离（用于稳定性计算）。"""

    _trajectory: list[PersonalitySnapshot] = field(default_factory=list)
    """人格向量随时间变化的轨迹快照。"""

    def __post_init__(self) -> None:
        # 首次创建时记录初始值
        if not self.original_values:
            self.original_values = {
                "ei": self.ei,
                "sn": self.sn,
                "tf": self.tf,
                "jp": self.jp,
            }
        if not self.original_type:
            self.original_type = self.mbti_type()

    # ---- 工厂方法 ----

    @classmethod
    def from_personality_profile(cls, profile: PersonalityProfile) -> PersonalityVector:
        """从 PersonalityProfile 创建 PersonalityVector。

        Args:
            profile: 现有的人格档案。

        Returns:
            新 PersonalityVector，初始值取自 profile 的当前状态。
        """
        vec = cls(
            ei=profile.ei,
            sn=profile.sn,
            tf=profile.tf,
            jp=profile.jp,
            original_type=profile.type_code,
            original_values={
                "ei": profile.ei,
                "sn": profile.sn,
                "tf": profile.tf,
                "jp": profile.jp,
            },
        )
        return vec

    # ---- 类型与距离 ----

    def mbti_type(self) -> str:
        """根据当前四维值推导 MBTI 类型字符串（如 'INTJ'、'ENFP'）。"""
        return (
            MbtiDimension.EI.letter(self.ei)
            + MbtiDimension.SN.letter(self.sn)
            + MbtiDimension.TF.letter(self.tf)
            + MbtiDimension.JP.letter(self.jp)
        )

    def distance_to(self, other: PersonalityVector) -> float:
        """计算与另一个向量的欧几里得距离。

        Args:
            other: 另一个人格向量。

        Returns:
            四维空间中的欧几里得距离。
        """
        return math.sqrt(
            sum(
                (getattr(self, d) - getattr(other, d)) ** 2
                for d in _DIMS
            )
        )

    def drift_from_original(self) -> float:
        """计算当前向量距原始人格的欧几里得距离。

        Returns:
            漂移距离（0 表示未变化）。
        """
        return math.sqrt(
            sum(
                (getattr(self, d) - self.original_values[d]) ** 2
                for d in _DIMS
            )
        )

    # ---- 序列化 ----

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "ei": round(self.ei, 4),
            "sn": round(self.sn, 4),
            "tf": round(self.tf, 4),
            "jp": round(self.jp, 4),
            "stability_score": round(self.stability_score, 4),
            "drift_total": round(self.drift_total, 4),
            "original_type": self.original_type,
            "current_type": self.mbti_type(),
            "drift_from_original": round(self.drift_from_original(), 4),
            "original_values": {k: round(v, 4) for k, v in self.original_values.items()},
        }

    # ---- 内部 ----

    def _apply_shifts(self, shifts: dict[str, float], magnitude: float) -> None:
        """应用维度偏移并记录漂移量。

        Args:
            shifts: {dim: delta, ...} 各维度偏移量。
            magnitude: 本次漂移的欧几里得距离（用于稳定性追踪）。
        """
        for dim in _DIMS:
            delta = shifts.get(dim, 0.0)
            current = getattr(self, dim)
            setattr(self, dim, max(-1.0, min(1.0, current + delta)))

        self.drift_total += magnitude
        self._recent_shift_magnitudes.append(magnitude)
        # 只保留最近窗口
        if len(self._recent_shift_magnitudes) > _STABILITY_WINDOW * 2:
            self._recent_shift_magnitudes = self._recent_shift_magnitudes[-_STABILITY_WINDOW:]

    def _record_snapshot(self, tick: int) -> None:
        """记录当前状态的快照到轨迹中。"""
        snap = PersonalitySnapshot(
            tick=tick,
            ei=self.ei,
            sn=self.sn,
            tf=self.tf,
            jp=self.jp,
            mbti_type=self.mbti_type(),
        )
        self._trajectory.append(snap)

    def _compute_stability(self) -> None:
        """重新计算稳定性分数。

        公式: stability = 1.0 - (std(recent_shifts) / 0.1), clamped [0, 1]
        标准差越小，越稳定。
        """
        recent = self._recent_shift_magnitudes[-_STABILITY_WINDOW:]
        if len(recent) < 2:
            self.stability_score = 1.0
            return

        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std = math.sqrt(variance)
        score = 1.0 - (std / 0.1)
        self.stability_score = max(0.0, min(1.0, score))


# ===========================================================================
# 3. PersonalityDynamicsEngine — 人格演化引擎
# ===========================================================================

@dataclass
class PersonalityShift:
    """一次重大人格转变事件。

    当 agent 的 MBTI 类型发生变化且漂移距离超过阈值时生成。
    """

    agent_name: str
    """发生转变的 agent。"""

    old_type: str
    """旧 MBTI 类型。"""

    new_type: str
    """新 MBTI 类型。"""

    drift_distance: float
    """距原始人格的漂移距离。"""

    tick: int
    """发生转变的 tick。"""

    description: str = ""
    """转变描述。"""

    significance: float = 0.0
    """转变显著度 [0, 1]（基于漂移距离归一化）。"""

    def __post_init__(self) -> None:
        if self.significance == 0.0:
            # 自动计算显著度: drift_distance / 1.0（最大漂移 ≈ 2.83，四维各极值）
            self.significance = min(1.0, self.drift_distance / 1.5)


class PersonalityDynamicsEngine:
    """人格动力学引擎 — 追踪社会影响力 + 人格向量演化 + 重大转变检测。

    基于已有的 PersonalityEvolutionEngine，增强为三层系统：
    1. 记录每次社交互动对人格的影响
    2. 维护增强的人格向量（含稳定性、漂移）
    3. 检测跨 MBTI 类型的重大人格转变

    单例通过 get_personality_dynamics_engine() 获取。
    """

    def __init__(self, evolution_engine: PersonalityEvolutionEngine | None = None) -> None:
        """初始化人格动力学引擎。

        Args:
            evolution_engine: 已有的人格演化引擎。若为 None，自动获取单例。
        """
        self.evolution_engine = evolution_engine or get_personality_engine()
        self.vectors: dict[str, PersonalityVector] = {}
        self.influence_tracker = SocialInfluenceTracker()
        self.shifts: list[PersonalityShift] = []

        # Phase 24 ReciprocalAltruism 可选依赖
        self._altruism: Any | None = None
        if _HAS_ECONOMY and _ReciprocalAltruism is not None:
            self._altruism = _ReciprocalAltruism()

    # ---- 向量管理 ----

    def get_or_create_vector(self, agent_name: str) -> PersonalityVector:
        """获取或创建 agent 的增强人格向量。

        如果不存在，从底层 PersonalityEvolutionEngine 获取 PersonalityProfile 并转换。

        Args:
            agent_name: agent 名称。

        Returns:
            PersonalityVector 实例。
        """
        if agent_name not in self.vectors:
            profile = self.evolution_engine.get_or_create(agent_name)
            vec = PersonalityVector.from_personality_profile(profile)
            self.vectors[agent_name] = vec
            logger.info(
                "PersonalityDynamics: 为 %s 创建向量 %s (原始=%s)",
                agent_name,
                vec.mbti_type(),
                vec.original_type,
            )
        return self.vectors[agent_name]

    def get_vector(self, agent_name: str) -> PersonalityVector | None:
        """获取已有的人格向量（不自动创建）。"""
        return self.vectors.get(agent_name)

    # ---- 互动记录 ----

    def record_interaction(
        self,
        influencer: str,
        influenced: str,
        interaction_type: str,
        magnitude: float,
        tick: int,
    ) -> SocialInfluenceRecord:
        """记录一次互动并计算/应用人格维度漂移。

        漂移公式:
            dimension_shifts = base_vector[interaction_type] × magnitude × influence_factor

        influence_factor 受债务影响:
            - 若 influenced 欠 influencer 债务 → influence_factor > 1.0
            - 无债务 → 默认 1.0

        Args:
            influencer: 施加影响者。
            influenced: 被影响者。
            interaction_type: 互动类型 (dialogue/battle/help/trade/gift/wakeup)。
            magnitude: 互动强度 [0, 1]。
            tick: 当前 world tick。

        Returns:
            SocialInfluenceRecord — 创建的影响记录。

        Raises:
            ValueError: 未知的 interaction_type。
        """
        if interaction_type not in INTERACTION_BASE_VECTORS:
            raise ValueError(
                f"未知互动类型 '{interaction_type}'，"
                f"支持: {list(INTERACTION_BASE_VECTORS.keys())}"
            )

        base = INTERACTION_BASE_VECTORS[interaction_type]
        influence_factor = self._compute_influence_factor(influenced, influencer)
        magnitude = max(0.0, min(1.0, magnitude))

        # 计算实际维度偏移
        dimension_shifts: dict[str, float] = {}
        for dim in _DIMS:
            delta = base.get(dim, 0.0) * magnitude * influence_factor
            dimension_shifts[dim] = round(delta, 6)

        # 计算漂移量（欧几里得距离）
        shift_magnitude = math.sqrt(sum(v ** 2 for v in dimension_shifts.values()))

        # 应用到受影响 agent 的人格向量
        vec = self.get_or_create_vector(influenced)
        vec._apply_shifts(dimension_shifts, shift_magnitude)

        # 同时更新底层 engine 的 profile（保持同步）
        profile = self.evolution_engine.get(influenced)
        if profile is not None:
            for dim in _DIMS:
                current = getattr(profile, dim)
                setattr(profile, dim, max(-1.0, min(1.0, current + dimension_shifts[dim])))
            profile._recompute()

        # 创建并存储影响记录
        record = SocialInfluenceRecord(
            influencer_name=influencer,
            influenced_name=influenced,
            interaction_type=interaction_type,
            magnitude=magnitude,
            dimension_shifts=dimension_shifts,
            tick=tick,
        )
        self.influence_tracker.add_record(record)

        logger.debug(
            "PersonalityDynamics: tick=%d %s → %s (%s, mag=%.2f, drift=%.4f, vec=%.2f,%.2f,%.2f,%.2f)",
            tick,
            influencer,
            influenced,
            interaction_type,
            magnitude,
            shift_magnitude,
            vec.ei,
            vec.sn,
            vec.tf,
            vec.jp,
        )

        return record

    # ---- 步进 — 稳定性 + 转变检测 ----

    def step(self, tick: int) -> list[PersonalityShift]:
        """每 N tick 执行：重新计算稳定性 + 检测重大人格转变。

        Args:
            tick: 当前 world tick。

        Returns:
            本轮检测到的 PersonalityShift 列表。
        """
        new_shifts: list[PersonalityShift] = []

        for agent_name, vec in self.vectors.items():
            # 1. 重新计算稳定性
            vec._compute_stability()

            # 2. 记录轨迹快照
            vec._record_snapshot(tick)

            # 3. 检测重大转变
            drift = vec.drift_from_original()
            current_type = vec.mbti_type()
            if drift > _SHIFT_DRIFT_THRESHOLD and current_type != vec.original_type:
                # 避免重复记录同一类型转变（只在类型刚改变时触发）
                last_shift_type = None
                for s in reversed(self.shifts):
                    if s.agent_name == agent_name:
                        last_shift_type = s.new_type
                        break

                if last_shift_type != current_type:
                    shift = PersonalityShift(
                        agent_name=agent_name,
                        old_type=vec.original_type,
                        new_type=current_type,
                        drift_distance=drift,
                        tick=tick,
                        description=(
                            f"{agent_name} 从 {vec.original_type} 转变为 {current_type}，"
                            f"漂移距离 {drift:.3f}"
                        ),
                    )
                    self.shifts.append(shift)
                    new_shifts.append(shift)
                    logger.info(
                        "PersonalityDynamics: tick=%d 检测到 %s 的重大转变: %s → %s (drift=%.3f)",
                        tick,
                        agent_name,
                        shift.old_type,
                        shift.new_type,
                        drift,
                    )

        return new_shifts

    # ---- 轨迹 ----

    def get_personality_trajectory(
        self, agent_name: str
    ) -> list[dict[str, Any]]:
        """获取 agent 的人格向量历史轨迹（用于前端画雷达图）。

        Args:
            agent_name: agent 名称。

        Returns:
            [{tick, ei, sn, tf, jp, mbti_type}, ...] 按 tick 升序排列。
        """
        vec = self.vectors.get(agent_name)
        if vec is None:
            return []

        return [
            {
                "tick": snap.tick,
                "ei": round(snap.ei, 4),
                "sn": round(snap.sn, 4),
                "tf": round(snap.tf, 4),
                "jp": round(snap.jp, 4),
                "mbti_type": snap.mbti_type,
            }
            for snap in vec._trajectory
        ]

    # ---- 辅助 ----

    def _compute_influence_factor(self, influenced: str, influencer: str) -> float:
        """计算影响力因子（基于互惠利他债务）。

        若 influenced 欠 influencer 债务，影响力更大。

        Args:
            influenced: 被影响者（欠债方）。
            influencer: 施加影响者（债权方）。

        Returns:
            influence_factor [1.0, 2.0]。
        """
        if self._altruism is not None:
            try:
                debt = self._altruism.get_debt(influenced, influencer)
                if debt > 0:
                    # 债务归一化: debt / MAX_DEBT → [0, 1]，加到基础 1.0
                    normalized = min(1.0, debt / _MAX_DEBT_NORMALIZE)
                    return 1.0 + normalized
            except Exception:
                logger.warning(
                    "PersonalityDynamics: 查询债务失败 (%s→%s)，使用默认 influence_factor",
                    influenced,
                    influencer,
                    exc_info=True,
                )
        return _DEFAULT_INFLUENCE_FACTOR

    def set_altruism(self, altruism: Any) -> None:
        """注入外部 ReciprocalAltruism 实例（用于测试或手动绑定）。

        Args:
            altruism: ReciprocalAltruism 实例或兼容对象。
        """
        self._altruism = altruism

    # ---- 重置 ----

    def reset(self) -> None:
        """重置所有内部状态（测试用）。"""
        self.vectors.clear()
        self.influence_tracker.clear()
        self.shifts.clear()


# ===========================================================================
# 全局单例
# ===========================================================================

_dynamics_engine: PersonalityDynamicsEngine | None = None


def get_personality_dynamics_engine() -> PersonalityDynamicsEngine:
    """获取全局人格动力学引擎单例。"""
    global _dynamics_engine
    if _dynamics_engine is None:
        _dynamics_engine = PersonalityDynamicsEngine()
    return _dynamics_engine


def reset_personality_dynamics_engine() -> None:
    """重置全局人格动力学引擎。"""
    global _dynamics_engine
    _dynamics_engine = None

"""
Narrative Coherence Engine — Phase 28 核心模块
=============================================

受 EvoSpark (arXiv:2604.12776) 启发，解决长时距多智能体模拟中的两大障碍：
1. **Social Memory Stacking**: 冲突的关系状态在无解决机制下持续堆积
2. **Narrative-Spatial Dissonance**: 空间逻辑与演化剧情脱节

本模块提供三个核心组件：
- RelationConflictDetector: 检测 agent 对之间的关系记忆矛盾
- SpatialNarrativeBinder: 确保空间事件与叙事记录一致
- CoherenceReport: 世界级叙事健康评分

纯算法实现，无 LLM 调用。

集成点（本模块不实现，仅设计预留）:
- world/scheduler.py tick_once() → coherence.check() 每 N tick
- API endpoint: GET /api/narratives/coherence → CoherenceReport.to_dict()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

# 关系冲突阈值
MAX_RELATION_CONTRADICTIONS: int = 10
"""单个 agent 对最多记录的关系矛盾数，超出后裁剪。"""

RELATION_AMBIVALENCE_THRESHOLD: float = 0.6
"""affinity + rivalry 同时很高（归一化后均 > 此阈值）= 矛盾信号。"""

TEMPORAL_WINDOW_TICKS: int = 500
"""检测窗口：只考虑最近 N tick 内的事件。"""

# 空间一致性
MAX_SPATIAL_DISTANCE_PX: float = 500.0
"""agent 在事件发生时的位置与事件坐标的最大允许偏差（像素）。"""

SPATIAL_BINDING_LOOKBACK: int = 100
"""空间绑定检查的历史 tick 范围。"""

# 一致性评分权重
COHERENCE_WEIGHT_RELATION: float = 0.40
"""关系冲突在总评分中的权重。"""

COHERENCE_WEIGHT_SPATIAL: float = 0.40
"""空间不一致在总评分中的权重。"""

COHERENCE_WEIGHT_EVENT_DENSITY: float = 0.20
"""事件密度异常（过多或过少）的权重。"""

MIN_EVENTS_PER_AGENT: int = 2
"""每个 agent 预期的最低事件数（检测"叙事空洞"）。"""

MAX_EVENTS_PER_AGENT: int = 50
"""每个 agent 预期的最高事件数（检测"叙事过载"）。"""

COHERENCE_CHECK_INTERVAL: int = 50
"""叙事一致性检查间隔（tick 数）。"""

COHERENCE_HIGH_THRESHOLD: float = 0.7
"""健康阈值：评分 >= 此值表示叙事健康。"""

COHERENCE_LOW_THRESHOLD: float = 0.3
"""警告阈值：评分 <= 此值表示严重叙事问题。"""

MAX_RELATION_HISTORY: int = 3
"""每对 agent 记录的关系历史快照数（检测翻转/矛盾）。"""


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────


@dataclass
class RelationSnapshot:
    """一对 agent 在某个时刻的关系快照。"""

    agent_a: str
    agent_b: str
    tick: int
    affinity: float
    rivalry: float
    respect: float
    fear: float


@dataclass
class RelationConflict:
    """检测到的一个关系矛盾。"""

    agent_a: str
    agent_b: str
    conflict_type: str
    """矛盾类型: 'ambivalence' | 'flip' | 'one_sided'"""

    severity: float
    """严重程度 [0, 1]，越高越严重。"""

    description: str
    """人类可读的描述。"""

    involved_ticks: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_a": self.agent_a,
            "agent_b": self.agent_b,
            "conflict_type": self.conflict_type,
            "severity": round(self.severity, 4),
            "description": self.description,
            "involved_ticks": self.involved_ticks,
        }


@dataclass
class SpatialInconsistency:
    """检测到的一个空间叙事不一致。"""

    agent_name: str
    event_type: str
    event_tick: int
    event_location: tuple[float, float]
    agent_location: tuple[float, float]
    distance_px: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "event_tick": self.event_tick,
            "event_location": list(self.event_location),
            "agent_location": list(self.agent_location),
            "distance_px": round(self.distance_px, 1),
        }


@dataclass
class CoherenceReport:
    """叙事一致性健康报告。"""

    tick: int
    global_score: float
    """全局一致性评分 [0, 1]。"""

    relation_conflicts: list[RelationConflict] = field(default_factory=list)
    spatial_inconsistencies: list[SpatialInconsistency] = field(default_factory=list)

    # 分解评分
    relation_score: float = 1.0
    spatial_score: float = 1.0
    density_score: float = 1.0

    # 汇总
    total_agent_pairs_checked: int = 0
    total_events_checked: int = 0
    agent_count: int = 0

    # 诊断建议
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "global_score": round(self.global_score, 4),
            "relation_score": round(self.relation_score, 4),
            "spatial_score": round(self.spatial_score, 4),
            "density_score": round(self.density_score, 4),
            "relation_conflicts": [c.to_dict() for c in self.relation_conflicts],
            "spatial_inconsistencies": [s.to_dict() for s in self.spatial_inconsistencies],
            "total_agent_pairs_checked": self.total_agent_pairs_checked,
            "total_events_checked": self.total_events_checked,
            "agent_count": self.agent_count,
            "warnings": self.warnings,
        }

    def is_healthy(self) -> bool:
        """叙事是否健康（评分 >= 阈值）。"""
        return self.global_score >= COHERENCE_HIGH_THRESHOLD

    def is_critical(self) -> bool:
        """叙事是否处于危急状态（评分 <= 警告阈值）。"""
        return self.global_score <= COHERENCE_LOW_THRESHOLD


# ──────────────────────────────────────────────
# RelationConflictDetector — 关系冲突检测器
# ──────────────────────────────────────────────


class RelationConflictDetector:
    """检测 agent 对之间的关系记忆矛盾。

    三种矛盾类型：
    1. **ambivalence**: affinity 和 rivalry 同时很高 — 爱恨交织
    2. **flip**: affinity 在短时间内大幅翻转 — 关系剧变
    3. **one_sided**: A→B 的 affinity 与 B→A 的 affinity 严重不对称
    """

    # ── 关系矛盾检测 ──

    @staticmethod
    def detect_ambivalence(
        agent_a: str,
        agent_b: str,
        affinity: float,
        rivalry: float,
    ) -> RelationConflict | None:
        """检测"爱恨交织"矛盾：affinity 和 rivalry 同时很高。

        affinity 和 rivalry 需先归一化到 [0, 1]。
        """
        affinity_norm = _normalize_score(affinity, -100, 100)
        rivalry_norm = _normalize_score(rivalry, 0, 100)

        if affinity_norm > RELATION_AMBIVALENCE_THRESHOLD and rivalry_norm > RELATION_AMBIVALENCE_THRESHOLD:
            severity = min(affinity_norm, rivalry_norm)
            return RelationConflict(
                agent_a=agent_a,
                agent_b=agent_b,
                conflict_type="ambivalence",
                severity=round(severity, 4),
                description=(
                    f"{agent_a}↔{agent_b}: 爱恨交织 — "
                    f"affinity={affinity:.1f}, rivalry={rivalry:.1f}"
                ),
            )
        return None

    @staticmethod
    def detect_flip(
        agent_a: str,
        agent_b: str,
        history: list[RelationSnapshot],
    ) -> RelationConflict | None:
        """检测关系翻转：affinity 短时间内大幅反转。

        需要至少 2 个历史快照。比较最早和最新的 affinity。
        """
        if len(history) < 2:
            return None

        first = history[0]
        last = history[-1]

        first_norm = _normalize_score(first.affinity, -100, 100)
        last_norm = _normalize_score(last.affinity, -100, 100)

        flip_magnitude = abs(last_norm - first_norm)
        if flip_magnitude > 0.5 and _sign(first.affinity) != _sign(last.affinity):
            return RelationConflict(
                agent_a=agent_a,
                agent_b=agent_b,
                conflict_type="flip",
                severity=round(flip_magnitude, 4),
                description=(
                    f"{agent_a}↔{agent_b}: 关系翻转 — "
                    f"affinity {first.affinity:.1f}→{last.affinity:.1f} "
                    f"(tick {first.tick}→{last.tick})"
                ),
                involved_ticks=[first.tick, last.tick],
            )
        return None

    @staticmethod
    def detect_one_sided(
        agent_a: str,
        agent_b: str,
        affinity_a_to_b: float,
        affinity_b_to_a: float,
    ) -> RelationConflict | None:
        """检测单向关系：A 对 B 的感情与 B 对 A 严重不对称。"""
        a_norm = _normalize_score(affinity_a_to_b, -100, 100)
        b_norm = _normalize_score(affinity_b_to_a, -100, 100)

        asymmetry = abs(a_norm - b_norm)
        if asymmetry > 0.6:
            return RelationConflict(
                agent_a=agent_a,
                agent_b=agent_b,
                conflict_type="one_sided",
                severity=round(asymmetry, 4),
                description=(
                    f"{agent_a}→{agent_b} affinity={affinity_a_to_b:.1f}, "
                    f"{agent_b}→{agent_a} affinity={affinity_b_to_a:.1f} — 严重单向"
                ),
            )
        return None

    @staticmethod
    def detect_all(
        agent_pairs: list[tuple[str, str, float, float, float, float]],
        pair_histories: dict[tuple[str, str], list[RelationSnapshot]] | None = None,
    ) -> list[RelationConflict]:
        """对所有 agent 对执行完整矛盾检测。

        Args:
            agent_pairs: [(agent_a, agent_b, a→b_affinity, b→a_affinity, a→b_rivalry, b→a_rivalry), ...]
            pair_histories: {(a,b): [RelationSnapshot, ...]} 关系历史快照（可选）

        Returns:
            按严重程度降序排列的矛盾列表。
        """
        conflicts: list[RelationConflict] = []
        histories = pair_histories or {}

        for a, b, aff_ab, aff_ba, riv_ab, riv_ba in agent_pairs:
            # ambivalence: 检查双方
            for source, target, aff, riv in [
                (a, b, aff_ab, riv_ab),
                (b, a, aff_ba, riv_ba),
            ]:
                c = RelationConflictDetector.detect_ambivalence(source, target, aff, riv)
                if c:
                    conflicts.append(c)

            # flip
            key = tuple(sorted([a, b]))
            history = histories.get(key, [])
            c = RelationConflictDetector.detect_flip(a, b, history)
            if c:
                conflicts.append(c)

            # one_sided
            c = RelationConflictDetector.detect_one_sided(a, b, aff_ab, aff_ba)
            if c:
                conflicts.append(c)

        conflicts.sort(key=lambda c: c.severity, reverse=True)
        return conflicts[:MAX_RELATION_CONTRADICTIONS]


# ──────────────────────────────────────────────
# SpatialNarrativeBinder — 空间叙事绑定器
# ──────────────────────────────────────────────


class SpatialNarrativeBinder:
    """确保空间事件与叙事记录一致。

    核心检测：某 agent 在 tick T 被记录为在位置 (x,y) 发生了事件 E，
    但 agent 的实际历史位置在 tick T 附近与 (x,y) 距离超过阈值。
    """

    @staticmethod
    def check_event_location(
        agent_name: str,
        event_type: str,
        event_tick: int,
        event_location: tuple[float, float],
        agent_position_at_tick: tuple[float, float] | None,
    ) -> SpatialInconsistency | None:
        """检查单个事件的空间一致性。

        Args:
            agent_name: agent 名称。
            event_type: 事件类型（如 'dialogue', 'battle', 'discovery'）。
            event_tick: 事件发生的 tick。
            event_location: 事件记录的位置 (x, y)。
            agent_position_at_tick: agent 在该 tick 的实际位置（如果未知则 None）。

        Returns:
            SpatialInconsistency 或 None（位置一致或数据不足）。
        """
        if agent_position_at_tick is None:
            return None

        dx = event_location[0] - agent_position_at_tick[0]
        dy = event_location[1] - agent_position_at_tick[1]
        distance = (dx * dx + dy * dy) ** 0.5

        if distance > MAX_SPATIAL_DISTANCE_PX:
            return SpatialInconsistency(
                agent_name=agent_name,
                event_type=event_type,
                event_tick=event_tick,
                event_location=event_location,
                agent_location=agent_position_at_tick,
                distance_px=distance,
            )
        return None

    @staticmethod
    def check_batch(
        events: list[dict[str, Any]],
        agent_positions: dict[str, dict[int, tuple[float, float]]],
    ) -> list[SpatialInconsistency]:
        """批量检查事件空间一致性。

        Args:
            events: [{"agent_name", "event_type", "tick", "location": (x,y)}, ...]
            agent_positions: {agent_name: {tick: (x,y), ...}, ...}

        Returns:
            不一致事件列表。
        """
        inconsistencies: list[SpatialInconsistency] = []

        for evt in events:
            name = evt.get("agent_name", "")
            etype = evt.get("event_type", "unknown")
            tick = evt.get("tick", 0)
            loc = evt.get("location", (0, 0))

            pos_map = agent_positions.get(name, {})
            # 查找最接近该 tick 的位置记录
            actual_pos = _find_nearest_position(pos_map, tick)
            # 如果最近的记录也在窗口外，跳过
            if actual_pos is None:
                continue

            inc = SpatialNarrativeBinder.check_event_location(
                agent_name=name,
                event_type=etype,
                event_tick=tick,
                event_location=(float(loc[0]), float(loc[1])),
                agent_position_at_tick=actual_pos,
            )
            if inc:
                inconsistencies.append(inc)

        return inconsistencies


# ──────────────────────────────────────────────
# CoherenceEngine — 叙事一致性引擎
# ──────────────────────────────────────────────


class CoherenceEngine:
    """叙事一致性引擎 — 组合关系检测 + 空间检测 + 事件密度。

    提供 check() 方法供 scheduler 每 N tick 调用，
    生成 CoherenceReport 供 API 和导演面板消费。
    """

    def __init__(self) -> None:
        self._relation_detector = RelationConflictDetector()
        self._spatial_binder = SpatialNarrativeBinder()
        self._pair_histories: dict[tuple[str, str], list[RelationSnapshot]] = {}
        self._last_check_tick: int = 0

    # ── 关系历史追踪 ──

    def record_relation_snapshot(
        self,
        agent_a: str,
        agent_b: str,
        tick: int,
        affinity: float,
        rivalry: float,
        respect: float,
        fear: float,
    ) -> RelationSnapshot:
        """记录一对 agent 的关系快照，维护历史。"""
        snapshot = RelationSnapshot(
            agent_a=agent_a,
            agent_b=agent_b,
            tick=tick,
            affinity=affinity,
            rivalry=rivalry,
            respect=respect,
            fear=fear,
        )
        key = (agent_a, agent_b) if agent_a < agent_b else (agent_b, agent_a)
        if key not in self._pair_histories:
            self._pair_histories[key] = []
        self._pair_histories[key].append(snapshot)

        # 只保留最近 N 个快照
        if len(self._pair_histories[key]) > MAX_RELATION_HISTORY:
            self._pair_histories[key] = self._pair_histories[key][-MAX_RELATION_HISTORY:]

        return snapshot

    # ── 完整检查 ──

    def check(
        self,
        tick: int,
        agent_names: list[str],
        pairs_data: list[tuple[str, str, float, float, float, float]],
        events: list[dict[str, Any]] | None = None,
        agent_positions: dict[str, dict[int, tuple[float, float]]] | None = None,
    ) -> CoherenceReport:
        """执行完整叙事一致性检查。

        Args:
            tick: 当前世界 tick。
            agent_names: 所有 agent 名称列表。
            pairs_data: [(a, b, a→b_affinity, b→a_affinity, a→b_rivalry, b→a_rivalry), ...]
            events: 近期事件列表（可选，用于空间检查）。
            agent_positions: agent 位置历史（可选，用于空间检查）。

        Returns:
            CoherenceReport 包含全局评分和所有发现的问题。
        """
        self._last_check_tick = tick

        # 1. 关系冲突检测
        relation_conflicts = self._relation_detector.detect_all(
            pairs_data, self._pair_histories
        )

        # 2. 空间一致性检查
        spatial_inconsistencies: list[SpatialInconsistency] = []
        if events and agent_positions:
            spatial_inconsistencies = self._spatial_binder.check_batch(
                events, agent_positions
            )

        # 3. 计算分解评分
        n_pairs = max(len(pairs_data), 1)
        relation_score = max(0.0, 1.0 - len(relation_conflicts) / max(n_pairs, 1))

        n_events = max(len(events or []), 1)
        spatial_score = max(0.0, 1.0 - len(spatial_inconsistencies) / max(n_events, 1))

        density_score = self._compute_density_score(agent_names, events or [])

        # 4. 综合评分
        global_score = (
            relation_score * COHERENCE_WEIGHT_RELATION
            + spatial_score * COHERENCE_WEIGHT_SPATIAL
            + density_score * COHERENCE_WEIGHT_EVENT_DENSITY
        )
        global_score = round(max(0.0, min(1.0, global_score)), 4)

        # 5. 生成警告
        warnings = self._generate_warnings(
            global_score, relation_conflicts, spatial_inconsistencies
        )

        return CoherenceReport(
            tick=tick,
            global_score=global_score,
            relation_conflicts=relation_conflicts,
            spatial_inconsistencies=spatial_inconsistencies,
            relation_score=round(relation_score, 4),
            spatial_score=round(spatial_score, 4),
            density_score=round(density_score, 4),
            total_agent_pairs_checked=n_pairs,
            total_events_checked=n_events,
            agent_count=len(agent_names),
            warnings=warnings,
        )

    # ── 事件密度 ──

    @staticmethod
    def _compute_density_score(
        agent_names: list[str],
        events: list[dict[str, Any]],
    ) -> float:
        """计算事件密度健康评分。

        检测两种异常：
        - 叙事空洞：agent 事件数远低于预期
        - 叙事过载：agent 事件数远高于预期
        """
        if not agent_names:
            return 1.0

        # 按 agent 统计事件
        event_counts: dict[str, int] = dict.fromkeys(agent_names, 0)
        for evt in events:
            name = evt.get("agent_name", "")
            if name in event_counts:
                event_counts[name] += 1

        # 计算偏离度
        total_penalty = 0.0
        for count in event_counts.values():
            if count < MIN_EVENTS_PER_AGENT:
                penalty = (MIN_EVENTS_PER_AGENT - count) / MIN_EVENTS_PER_AGENT
                total_penalty += min(penalty, 1.0)
            elif count > MAX_EVENTS_PER_AGENT:
                penalty = (count - MAX_EVENTS_PER_AGENT) / MAX_EVENTS_PER_AGENT
                total_penalty += min(penalty, 1.0)

        if len(agent_names) == 0:
            return 1.0

        avg_penalty = total_penalty / len(agent_names)
        return round(max(0.0, 1.0 - avg_penalty), 4)

    # ── 警告生成 ──

    @staticmethod
    def _generate_warnings(
        global_score: float,
        relation_conflicts: list[RelationConflict],
        spatial_inconsistencies: list[SpatialInconsistency],
    ) -> list[str]:
        """生成人类可读的诊断警告。"""
        warnings: list[str] = []

        if global_score < COHERENCE_LOW_THRESHOLD:
            warnings.append(f"🔴 全局叙事一致性危急 (score={global_score:.2f})")
        elif global_score < COHERENCE_HIGH_THRESHOLD:
            warnings.append(f"🟡 全局叙事一致性偏低 (score={global_score:.2f})")

        ambivalence_count = sum(1 for c in relation_conflicts if c.conflict_type == "ambivalence")
        flip_count = sum(1 for c in relation_conflicts if c.conflict_type == "flip")
        one_sided_count = sum(1 for c in relation_conflicts if c.conflict_type == "one_sided")

        if ambivalence_count > 0:
            warnings.append(f"爱恨交织: {ambivalence_count} 对 agent 同时持有高亲和+高竞争")
        if flip_count > 0:
            warnings.append(f"关系翻转: {flip_count} 对 agent 近期经历了关系剧变")
        if one_sided_count > 0:
            warnings.append(f"单向关系: {one_sided_count} 对 agent 存在严重感情不对称")

        if spatial_inconsistencies:
            warnings.append(
                f"空间不一致: {len(spatial_inconsistencies)} 个事件的位置记录与实际不符"
            )

        return warnings

    # ── 查询 ──

    def should_check(self, tick: int) -> bool:
        """判断是否应在此 tick 执行一致性检查。"""
        return (tick - self._last_check_tick) >= COHERENCE_CHECK_INTERVAL

    def get_pair_history(self, agent_a: str, agent_b: str) -> list[RelationSnapshot]:
        """获取一对 agent 的关系历史快照。"""
        key = (agent_a, agent_b) if agent_a < agent_b else (agent_b, agent_a)
        return self._pair_histories.get(key, [])

    def reset(self) -> None:
        """重置所有内部状态。"""
        self._pair_histories.clear()
        self._last_check_tick = 0


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────

_engine: CoherenceEngine | None = None


def get_coherence_engine() -> CoherenceEngine:
    """获取全局叙事一致性引擎单例。

    首次调用时自动创建。用于 scheduler / API 端点访问。

    Returns:
        CoherenceEngine 单例。
    """
    global _engine
    if _engine is None:
        _engine = CoherenceEngine()
    return _engine


def reset_coherence_engine() -> None:
    """重置全局叙事一致性引擎（测试专用）。"""
    global _engine
    _engine = None


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """将值限制在 [lo, hi] 范围内。"""
    return max(lo, min(hi, value))


def _normalize_score(value: float, lo: float, hi: float) -> float:
    """将 [lo, hi] 范围的分数归一化到 [0, 1]。"""
    if hi <= lo:
        return 0.5
    return _clamp((value - lo) / (hi - lo))


def _sign(value: float) -> int:
    """返回值的符号：-1, 0, 1。"""
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _find_nearest_position(
    pos_map: dict[int, tuple[float, float]],
    target_tick: int,
) -> tuple[float, float] | None:
    """在位置历史中找到最接近 target_tick 的位置记录。

    Args:
        pos_map: {tick: (x, y)} 位置历史。
        target_tick: 目标 tick。

    Returns:
        (x, y) 或 None（如果窗口内无记录）。
    """
    if not pos_map:
        return None

    best_tick: int | None = None
    best_dist: int = SPATIAL_BINDING_LOOKBACK + 1

    for tick in pos_map:
        dist = abs(tick - target_tick)
        if dist < best_dist:
            best_dist = dist
            best_tick = tick

    if best_tick is not None and best_dist <= SPATIAL_BINDING_LOOKBACK:
        return pos_map[best_tick]
    return None

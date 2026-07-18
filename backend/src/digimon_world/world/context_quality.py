"""
Agent 上下文质量与可靠性工程 — Phase 25 核心模块
================================================

论文依据: arXiv:2607.14275 "AI Agents Do Not Fail Alone: The Context Fails First"
(2026-07-18)。核心发现：context engineering quality 是 agent 可靠性的独立先行指标
——上下文弱时 agent 漂移、幻觉、误用工具。

三大组件:
1. ContextHealthMonitor — 每个 tick 对每个 agent 生成 ContextQualitySnapshot
2. ContextIssue — 诊断上下文问题（staleness/relevance/coherence/overload/plan_drift）
3. ContextOptimizer — 策略建议（不自动执行），推荐 repeat/compress/restore/revalidate/prune

集成:
- 从 digimon_world.agents.digimon_agent 导入 DigimonAgent (类型标注)
- 读取 Phase 18 (MemoryAutonomy)、Phase 19 (PlanPersistenceEngine)、
  Phase 20 (WorldModel) 数据
- 所有外部依赖用 try/except ImportError + Optional 类型标注，模块独立可测

设计要点:
- 纯 Python dataclass + 算法逻辑，不调 LLM
- 含 docstring + type hints
- 对齐 Phase 1-24 的 API 惯例（dataclass、get_* 工厂、单例模式）
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 可选导入: 外部模块（模块独立可测）
# ──────────────────────────────────────────────

try:
    from ..agents.digimon_agent import DigimonAgent as _DigimonAgent
    _HAS_AGENT = True
except ImportError:
    _DigimonAgent = None  # type: ignore[assignment]
    _HAS_AGENT = False

try:
    from ..agents.plan_persistence import PlanPersistenceEngine, PlanStatus
    _HAS_PLAN = True
except ImportError:
    PlanPersistenceEngine = None  # type: ignore[assignment]
    PlanStatus = None  # type: ignore[assignment]
    _HAS_PLAN = False

try:
    from ..memory.world_model import WorldModel as _WorldModel
    _HAS_WORLD_MODEL = True
except ImportError:
    _WorldModel = None  # type: ignore[assignment]
    _HAS_WORLD_MODEL = False


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

# 综合健康评分权重
WEIGHT_MEMORY_STALENESS = 0.20     # 记忆新鲜度
WEIGHT_MEMORY_RELEVANCE = 0.20     # 记忆-计划关联度
WEIGHT_PLAN_CURRENCY = 0.20        # 计划时效性
WEIGHT_WORLD_MODEL_COVERAGE = 0.15 # 世界模型覆盖
WEIGHT_COHERENCE = 0.15            # 整体一致性
WEIGHT_CONTEXT_LOAD = 0.10         # 上下文负载（负向）

# 诊断阈值 (aligned with sibling test expectations)
STALENESS_WARNING_THRESHOLD = 0.7
STALENESS_CRITICAL_THRESHOLD = 0.9
RELEVANCE_WARNING_THRESHOLD = 0.3
RELEVANCE_CRITICAL_THRESHOLD = 0.1
PLAN_CURRENCY_WARNING_THRESHOLD = 0.3
PLAN_CURRENCY_CRITICAL_THRESHOLD = 0.1
COHERENCE_WARNING_THRESHOLD = 0.5
COHERENCE_CRITICAL_THRESHOLD = 0.4
CONTEXT_SIZE_WARNING = 50_000
CONTEXT_SIZE_CRITICAL = 100_000
WORLD_MODEL_COVERAGE_WARNING = 0.05
WORLD_MODEL_COVERAGE_CRITICAL = 0.01

# 记忆年龄归一化窗口（tick 数）
MEMORY_AGE_NORMALIZE_TICKS = 100

# 最近记忆窗口（用于相关性计算）
RECENT_MEMORY_WINDOW = 10

# Token 估算参数
CHARS_PER_TOKEN = 4
TOKENS_PER_MEMORY_OVERHEAD = 10
TOKENS_PER_RULE = 20
PLAN_TOKENS_OVERHEAD = 50

# 历史快照保留数
MAX_SNAPSHOT_HISTORY = 200


# ──────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────

@dataclass
class ContextQualitySnapshot:
    """Agent 在每个 tick 的上下文质量快照。

    基于 arXiv:2607.14275 的 context engineering quality 指标体系，
    将 agent 的记忆流、计划持久化、世界模型综合评估为一个 health score。
    """

    agent_name: str
    tick: int
    memory_count: int = 0
    memory_staleness: float = 0.0
    memory_relevance: float = 0.0
    plan_currency: float = 0.0
    world_model_coverage: float = 0.0
    context_size_estimate: int = 0
    coherence_score: float = 0.0
    composite_health: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "tick": self.tick,
            "memory_count": self.memory_count,
            "memory_staleness": round(self.memory_staleness, 4),
            "memory_relevance": round(self.memory_relevance, 4),
            "plan_currency": round(self.plan_currency, 4),
            "world_model_coverage": round(self.world_model_coverage, 4),
            "context_size_estimate": self.context_size_estimate,
            "coherence_score": round(self.coherence_score, 4),
            "composite_health": round(self.composite_health, 2),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextQualitySnapshot":
        return cls(
            agent_name=data["agent_name"],
            tick=data["tick"],
            memory_count=data.get("memory_count", 0),
            memory_staleness=data.get("memory_staleness", 0.0),
            memory_relevance=data.get("memory_relevance", 0.0),
            plan_currency=data.get("plan_currency", 0.0),
            world_model_coverage=data.get("world_model_coverage", 0.0),
            context_size_estimate=data.get("context_size_estimate", 0),
            coherence_score=data.get("coherence_score", 0.0),
            composite_health=data.get("composite_health", 0.0),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class ContextIssue:
    """上下文质量诊断发现的问题。"""

    severity: Literal["warning", "critical"]
    category: Literal["staleness", "relevance", "coherence", "overload", "plan_drift"]
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
        }


@dataclass
class OptimizationAction:
    """上下文优化建议（策略建议，不自动执行）。

    映射关系:
    - staleness  → repeat_memories   (Phase 18 MemoryRehearsal)
    - overload   → compress_memories (Phase 7  MemoryStream.compress_memories)
    - plan_drift → restore_plan      (Phase 19 PlanPersistenceEngine.resume)
    - coherence  → revalidate_rules  (Phase 20 WorldModel.extract_rules)
    - relevance  → prune_irrelevant  (记忆重要性筛选)
    """

    action_type: Literal[
        "repeat_memories", "compress_memories", "restore_plan",
        "revalidate_rules", "prune_irrelevant",
    ]
    priority: int  # 1-5, 5=最高优先级
    target_system: str
    estimated_improvement: float  # 预估 composite_health 提升幅度 (0-100)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "priority": self.priority,
            "target_system": self.target_system,
            "estimated_improvement": round(self.estimated_improvement, 2),
        }


# ──────────────────────────────────────────────
# ContextHealthMonitor
# ──────────────────────────────────────────────

class ContextHealthMonitor:
    """Agent 上下文健康监控器。

    每个 tick 对 agent 生成 ContextQualitySnapshot，诊断潜在问题。

    用法:
        monitor = ContextHealthMonitor()
        snap = monitor.snapshot(agent, tick=100)
        issues = monitor.diagnose(snap)
        history = monitor.history("亚古兽", limit=10)
    """

    def __init__(self, max_history: int = MAX_SNAPSHOT_HISTORY) -> None:
        self._history: dict[str, list[ContextQualitySnapshot]] = defaultdict(list)
        self.max_history = max_history

    # ── 核心 API ────────────────────────────

    def snapshot(self, agent: Any, tick: int) -> ContextQualitySnapshot:
        """从 agent 的 memory_stream, plan_persistence, world_model
        提取数据生成上下文质量快照。

        Args:
            agent: DigimonAgent 实例（或任何兼容对象）
            tick: 当前世界 tick

        Returns:
            ContextQualitySnapshot
        """
        agent_name = getattr(agent, "name", "unknown")

        # 1. 记忆维度
        memory_count = self._get_memory_count(agent)
        memory_staleness = self._compute_memory_staleness(agent, tick)
        memory_relevance = self._compute_memory_relevance(agent)

        # 2. 计划维度
        plan_currency = self._compute_plan_currency(agent, tick)

        # 3. 世界模型维度
        world_model_coverage = self._compute_world_model_coverage(agent)

        # 4. 上下文负载
        context_size_estimate = self._estimate_context_size(agent)

        # 5. 认知一致性
        coherence_score = self._compute_coherence(
            memory_relevance, plan_currency, world_model_coverage,
        )

        # 6. 综合健康评分
        composite_health = self._compute_composite_health(
            memory_staleness=memory_staleness,
            memory_relevance=memory_relevance,
            plan_currency=plan_currency,
            world_model_coverage=world_model_coverage,
            coherence_score=coherence_score,
            context_size_estimate=context_size_estimate,
        )

        snap = ContextQualitySnapshot(
            agent_name=agent_name,
            tick=tick,
            memory_count=memory_count,
            memory_staleness=round(memory_staleness, 4),
            memory_relevance=round(memory_relevance, 4),
            plan_currency=round(plan_currency, 4),
            world_model_coverage=round(world_model_coverage, 4),
            context_size_estimate=context_size_estimate,
            coherence_score=round(coherence_score, 4),
            composite_health=round(composite_health, 2),
        )

        # 记录到历史
        hist = self._history[agent_name]
        hist.append(snap)
        while len(hist) > self.max_history:
            hist.pop(0)

        logger.debug(
            "ContextQuality snapshot: %s tick=%d health=%.1f "
            "(stale=%.2f relev=%.2f plan=%.2f cov=%.2f coh=%.2f size=%d)",
            agent_name, tick, composite_health,
            memory_staleness, memory_relevance, plan_currency,
            world_model_coverage, coherence_score, context_size_estimate,
        )
        return snap

    def diagnose(self, snapshot: ContextQualitySnapshot) -> list[ContextIssue]:
        """根据快照诊断上下文质量问题。

        Args:
            snapshot: 由 snapshot() 生成的上下文质量快照

        Returns:
            ContextIssue 列表（按严重程度排序：critical 在前）
        """
        issues: list[ContextIssue] = []

        # staleness
        if snapshot.memory_staleness >= STALENESS_CRITICAL_THRESHOLD:
            issues.append(ContextIssue(
                severity="critical", category="staleness",
                description=f"记忆严重过时 (staleness={snapshot.memory_staleness:.2f})，"
                            f"大部分记忆已超过 {MEMORY_AGE_NORMALIZE_TICKS} tick",
            ))
        elif snapshot.memory_staleness >= STALENESS_WARNING_THRESHOLD:
            issues.append(ContextIssue(
                severity="warning", category="staleness",
                description=f"记忆开始老化 (staleness={snapshot.memory_staleness:.2f})，"
                            "建议触发记忆复述",
            ))

        # relevance
        if snapshot.memory_relevance <= RELEVANCE_CRITICAL_THRESHOLD:
            issues.append(ContextIssue(
                severity="critical", category="relevance",
                description=f"记忆与计划严重脱节 (relevance={snapshot.memory_relevance:.2f})",
            ))
        elif snapshot.memory_relevance <= RELEVANCE_WARNING_THRESHOLD:
            issues.append(ContextIssue(
                severity="warning", category="relevance",
                description=f"记忆与计划关联度偏低 (relevance={snapshot.memory_relevance:.2f})",
            ))

        # plan_drift
        if snapshot.plan_currency <= PLAN_CURRENCY_CRITICAL_THRESHOLD:
            issues.append(ContextIssue(
                severity="critical", category="plan_drift",
                description=f"计划严重过期 (currency={snapshot.plan_currency:.2f})",
            ))
        elif snapshot.plan_currency <= PLAN_CURRENCY_WARNING_THRESHOLD:
            issues.append(ContextIssue(
                severity="warning", category="plan_drift",
                description=f"计划时效性下降 (currency={snapshot.plan_currency:.2f})",
            ))

        # overload
        if snapshot.context_size_estimate >= CONTEXT_SIZE_CRITICAL:
            issues.append(ContextIssue(
                severity="critical", category="overload",
                description=f"上下文严重过载 (size={snapshot.context_size_estimate})",
            ))
        elif snapshot.context_size_estimate >= CONTEXT_SIZE_WARNING:
            issues.append(ContextIssue(
                severity="warning", category="overload",
                description=f"上下文偏大 (size={snapshot.context_size_estimate})，建议压缩",
            ))

        # coherence
        if snapshot.coherence_score <= COHERENCE_CRITICAL_THRESHOLD:
            issues.append(ContextIssue(
                severity="critical", category="coherence",
                description=f"认知一致性极低 (coherence={snapshot.coherence_score:.2f})",
            ))
        elif snapshot.coherence_score <= COHERENCE_WARNING_THRESHOLD:
            issues.append(ContextIssue(
                severity="warning", category="coherence",
                description=f"认知一致性偏低 (coherence={snapshot.coherence_score:.2f})",
            ))

        # world_model_coverage (低覆盖 + 多经验 → 需学规则)
        if (snapshot.world_model_coverage <= WORLD_MODEL_COVERAGE_CRITICAL
                and snapshot.memory_count > 20):
            issues.append(ContextIssue(
                severity="warning", category="coherence",
                description=f"世界模型覆盖不足 (coverage={snapshot.world_model_coverage:.4f})",
            ))

        issues.sort(key=lambda i: (0 if i.severity == "critical" else 1, i.category))
        return issues

    def history(
        self, agent_name: str, limit: int = 0,
    ) -> list[ContextQualitySnapshot]:
        """返回某 agent 最近 N 条上下文质量快照。

        Args:
            agent_name: agent 名称
            limit: 返回上限（0=全部，默认0）

        Returns:
            快照列表（按 tick 升序）
        """
        snaps = self._history.get(agent_name, [])
        return snaps[-limit:] if limit > 0 else list(snaps)

    def latest_snapshot(self, agent_name: str) -> Optional[ContextQualitySnapshot]:
        """返回某 agent 最近一次快照，无记录时返回 None。"""
        snaps = self._history.get(agent_name, [])
        return snaps[-1] if snaps else None

    @property
    def all_agents(self) -> list[str]:
        """返回所有有快照记录的 agent 名称列表。"""
        return list(self._history.keys())

    # ── 内部方法 ────────────────────────────

    @staticmethod
    def _get_memory_count(agent: Any) -> int:
        if hasattr(agent, "memory") and hasattr(agent.memory, "entries"):
            return len(agent.memory.entries)
        return 0

    @staticmethod
    def _compute_memory_staleness(agent: Any, tick: int) -> float:
        entries = []
        if hasattr(agent, "memory") and hasattr(agent.memory, "entries"):
            entries = agent.memory.entries
        if not entries:
            return 0.0

        staleness_values: list[float] = []

        # 优先用遗忘引擎的 strength 数据
        if hasattr(agent, "memory_autonomy") and agent.memory_autonomy is not None:
            try:
                fe = agent.memory_autonomy.forgetting_engine
                for h in fe.memory_health.values():
                    nid = h.memory.node_id
                    if nid is not None:
                        s = fe.get_strength(nid)
                        staleness_values.append(1.0 - s)
            except Exception:
                pass

        # 兜底: 基于 tick 年龄
        if not staleness_values:
            for entry in entries:
                age = max(0, tick - entry.tick_index)
                normalized_age = min(1.0, age / MEMORY_AGE_NORMALIZE_TICKS)
                staleness_values.append(normalized_age)

        return sum(staleness_values) / len(staleness_values) if staleness_values else 0.0

    @staticmethod
    def _compute_memory_relevance(agent: Any) -> float:
        plan_text = getattr(agent, "current_plan", None) or ""
        if not plan_text:
            return 0.5

        entries = []
        if hasattr(agent, "memory") and hasattr(agent.memory, "entries"):
            entries = agent.memory.entries
        if not entries:
            return 0.0

        recent = entries[-RECENT_MEMORY_WINDOW:]
        plan_keywords = _extract_keywords(plan_text)
        if not plan_keywords:
            return 0.5

        scores: list[float] = []
        for mem in recent:
            mem_keywords = _extract_keywords(mem.description)
            if not mem_keywords:
                scores.append(0.0)
                continue
            overlap = len(plan_keywords & mem_keywords)
            denom = min(len(plan_keywords), len(mem_keywords)) + 1
            scores.append(overlap / denom)

        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def _compute_plan_currency(agent: Any, tick: int) -> float:
        # 尝试获取 plan engine（支持多种属性名）
        engine = None
        for attr in ("plan_engine", "plan_persistence"):
            if hasattr(agent, attr):
                engine = getattr(agent, attr)
                break
        if engine is None and hasattr(agent, "_get_plan_engine"):
            try:
                engine = agent._get_plan_engine()
            except Exception:
                pass

        if engine is None:
            return 0.3  # 默认：无 checkpoint 时

        if hasattr(engine, "get_active"):
            try:
                active = engine.get_active(getattr(agent, "name", ""))
                if active is not None:
                    tick_created = getattr(active, "tick_created", tick)
                    # 计划年龄归一化: 50 tick = 完全过期
                    age = (tick - tick_created) / 50.0
                    return max(0.0, min(1.0, 1.0 - age))
            except Exception:
                pass

        return 0.3

    @staticmethod
    def _compute_world_model_coverage(agent: Any) -> float:
        world_model = getattr(agent, "world_model", None)
        if world_model is None:
            return 0.0
        # 优先用 get_snapshot() (Phase 21 agent_insights 兼容)
        if hasattr(world_model, "get_snapshot"):
            try:
                snap_data = world_model.get_snapshot()
                if isinstance(snap_data, dict):
                    rules = snap_data.get("rules_count", 0)
                    episodes = snap_data.get("episodes_count", 1)
                    return rules / max(episodes, 1)
            except Exception:
                pass
        # 兜底: 直接访问 episodic/semantic
        try:
            episodes = world_model.episodic.count() if hasattr(world_model.episodic, "count") else 0
            rules = world_model.semantic.count() if hasattr(world_model.semantic, "count") else 0
            if episodes > 0:
                return rules / episodes
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _estimate_context_size(agent: Any) -> int:
        """估算 token 数。支持两种模式：详细估算（有 entries 时逐条计算）
        和快速估算（仅 memory_count 时用倍率）。"""
        # 优先详细估算
        if hasattr(agent, "memory") and hasattr(agent.memory, "entries"):
            tokens = 0
            for entry in agent.memory.entries:
                desc_len = len(getattr(entry, "description", ""))
                tokens += (desc_len // CHARS_PER_TOKEN) + TOKENS_PER_MEMORY_OVERHEAD
            plan_text = getattr(agent, "current_plan", None) or ""
            if plan_text:
                tokens += (len(plan_text) // CHARS_PER_TOKEN) + PLAN_TOKENS_OVERHEAD
            if _HAS_WORLD_MODEL:
                try:
                    wm = getattr(agent, "world_model", None)
                    if wm is not None:
                        rc = wm.semantic.count() if hasattr(wm.semantic, "count") else 0
                        tokens += rc * TOKENS_PER_RULE
                except Exception:
                    pass
            return max(0, tokens)
        # 快速估算
        mc = ContextHealthMonitor._get_memory_count(agent)
        return mc * 200 + 500 + 300

    @staticmethod
    def _compute_coherence(
        memory_relevance: float,
        plan_currency: float,
        world_model_coverage: float,
    ) -> float:
        """认知一致性 = 三维度的简单均值（与测试 fake agent 对齐）。"""
        return (memory_relevance + plan_currency + world_model_coverage) / 3.0

    @staticmethod
    def _compute_composite_health(
        memory_staleness: float,
        memory_relevance: float,
        plan_currency: float,
        world_model_coverage: float,
        coherence_score: float,
        context_size_estimate: int,
    ) -> float:
        freshness = 1.0 - memory_staleness
        if context_size_estimate <= CONTEXT_SIZE_WARNING:
            context_load_factor = 0.0
        elif context_size_estimate >= CONTEXT_SIZE_CRITICAL:
            context_load_factor = 1.0
        else:
            context_load_factor = (
                (context_size_estimate - CONTEXT_SIZE_WARNING)
                / (CONTEXT_SIZE_CRITICAL - CONTEXT_SIZE_WARNING)
            )
        score = (
            WEIGHT_MEMORY_STALENESS * freshness
            + WEIGHT_MEMORY_RELEVANCE * memory_relevance
            + WEIGHT_PLAN_CURRENCY * plan_currency
            + WEIGHT_WORLD_MODEL_COVERAGE * world_model_coverage
            + WEIGHT_COHERENCE * coherence_score
            - WEIGHT_CONTEXT_LOAD * context_load_factor
        )
        return max(0.0, min(100.0, score * 100.0))


# ──────────────────────────────────────────────
# ContextOptimizer
# ──────────────────────────────────────────────

class ContextOptimizer:
    """上下文优化器 — 根据快照和诊断问题生成策略建议。

    策略建议不自动执行，由上层调度器决定是否采纳。
    映射关系对应 Phases 7, 18, 19, 20 的已有能力。

    用法:
        optimizer = ContextOptimizer()
        actions = optimizer.recommend(snapshot, issues)
    """

    def recommend(
        self,
        snapshot: ContextQualitySnapshot,
        issues: list[ContextIssue],
    ) -> list[OptimizationAction]:
        """根据快照和诊断问题生成优化建议。

        Args:
            snapshot: 上下文质量快照
            issues: 诊断出的问题列表

        Returns:
            OptimizationAction 列表（按 priority 降序）
        """
        # 去重：同一 category 只取最高 severity 的 issue
        seen: dict[str, ContextIssue] = {}
        for issue in issues:
            if issue.category not in seen:
                seen[issue.category] = issue
            elif (issue.severity == "critical"
                  and seen[issue.category].severity == "warning"):
                seen[issue.category] = issue

        actions: list[OptimizationAction] = []
        for category, issue in seen.items():
            action = self._map_issue_to_action(snapshot, issue)
            if action:
                actions.append(action)

        actions.sort(key=lambda a: a.priority, reverse=True)
        return actions

    @staticmethod
    def _map_issue_to_action(
        snapshot: ContextQualitySnapshot,
        issue: ContextIssue,
    ) -> OptimizationAction | None:
        is_critical = issue.severity == "critical"

        mapping: dict[str, tuple[str, int, str]] = {
            "staleness": (
                "repeat_memories",
                5 if is_critical else 3,
                "MemoryAutonomy.forgetting_engine → MemoryRehearsal (Phase 18)",
            ),
            "overload": (
                "compress_memories",
                5 if is_critical else 4,
                "MemoryStream.compress_memories (Phase 7)",
            ),
            "plan_drift": (
                "restore_plan",
                5 if is_critical else 3,
                "PlanPersistenceEngine.resume (Phase 19)",
            ),
            "coherence": (
                "revalidate_rules",
                5 if is_critical else 2,
                "WorldModel.extract_rules(force=True) (Phase 20)",
            ),
            "relevance": (
                "prune_irrelevant",
                4 if is_critical else 2,
                "MemoryStream: 清理与当前计划无关的低重要性记忆",
            ),
        }

        entry = mapping.get(issue.category)
        if entry is None:
            return None

        action_type, priority, target = entry
        improvement = _estimate_improvement(snapshot, issue.category, is_critical)

        return OptimizationAction(
            action_type=action_type,  # type: ignore[arg-type]
            priority=priority,
            target_system=target,
            estimated_improvement=improvement,
        )


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _extract_keywords(text: str) -> set[str]:
    """从文本中提取关键词集合（不依赖分词库）。

    提取: 2+ 字中文词，3+ 字母英文词。
    """
    import re
    keywords: set[str] = set()
    for match in re.finditer(r'[\u4e00-\u9fff]{2,}', text):
        keywords.add(match.group())
    for match in re.finditer(r'[a-zA-Z]{3,}', text.lower()):
        keywords.add(match.group())
    return keywords


def _estimate_improvement(
    snapshot: ContextQualitySnapshot,
    category: str,
    is_critical: bool = False,
) -> float:
    """估算优化后的 composite_health 提升幅度。"""
    base_mult = 1.5 if is_critical else 1.0

    if category == "staleness":
        gain = (snapshot.memory_staleness - 0.2) * WEIGHT_MEMORY_STALENESS * 100 * base_mult
    elif category == "relevance":
        gain = (0.6 - snapshot.memory_relevance) * WEIGHT_MEMORY_RELEVANCE * 100 * base_mult
    elif category == "plan_drift":
        gain = (0.7 - snapshot.plan_currency) * WEIGHT_PLAN_CURRENCY * 100 * base_mult
    elif category == "coherence":
        gain = (0.6 - snapshot.coherence_score) * WEIGHT_COHERENCE * 100 * base_mult
    elif category == "overload":
        if snapshot.context_size_estimate > CONTEXT_SIZE_WARNING:
            gain = WEIGHT_CONTEXT_LOAD * 100 * base_mult
        else:
            gain = 5.0
    else:
        gain = 5.0

    return max(0.0, min(50.0, gain))


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────

_monitor: Optional[ContextHealthMonitor] = None
_optimizer: Optional[ContextOptimizer] = None


def get_health_monitor() -> ContextHealthMonitor:
    """获取全局 ContextHealthMonitor 单例。"""
    global _monitor
    if _monitor is None:
        _monitor = ContextHealthMonitor()
    return _monitor


def get_optimizer() -> ContextOptimizer:
    """获取全局 ContextOptimizer 单例。"""
    global _optimizer
    if _optimizer is None:
        _optimizer = ContextOptimizer()
    return _optimizer


def reset_context_quality() -> None:
    """重置全局单例（测试用）。"""
    global _monitor, _optimizer
    _monitor = None
    _optimizer = None

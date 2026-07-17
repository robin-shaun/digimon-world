"""
Agent 内省聚合引擎 — Phase 21 核心模块
=====================================

聚合 Phase 18 (MemoryAutonomy)、Phase 19 (PlanPersistence)、Phase 20 (WorldModel)
三大系统数据，生成统一的 agent 内省报告。

功能:
1. AgentInsightEngine — 内省引擎，聚合三大维度评分
2. 全局单例 — get_insight_engine() / reset_insight_engine()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 内省报告数据模型
# ──────────────────────────────────────────────


@dataclass
class DimensionResult:
    """单维度内省结果。"""

    score: float
    details: dict[str, Any] = field(default_factory=dict)
    top_weak: Optional[list[dict[str, Any]]] = None


@dataclass
class InsightReport:
    """聚合内省报告。"""

    agent_name: str
    timestamp: str
    overall_score: float
    dimensions: dict[str, Optional[dict[str, Any]]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "timestamp": self.timestamp,
            "overall_score": self.overall_score,
            "dimensions": self.dimensions,
        }


# ──────────────────────────────────────────────
# AgentInsightEngine
# ──────────────────────────────────────────────


class AgentInsightEngine:
    """Agent 内省引擎 — 聚合三大认知系统数据生成统一报告。

    用法:
        engine = AgentInsightEngine(agent_name="亚古兽")
        report = engine.assess(memory_autonomy, plan_engine, world_model)
    """

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    # ── 核心入口 ──────────────────────────────

    def assess(
        self,
        memory_autonomy: Any,
        plan_engine: Any,
        world_model: Any,
    ) -> dict[str, Any]:
        """聚合三大系统数据，返回内省报告。

        Args:
            memory_autonomy: MemoryAutonomy 实例 (有 diagnose())，可为 None
            plan_engine: PlanPersistenceEngine 实例 (有 get_history())，可为 None
            world_model: WorldModel 实例 (有 get_snapshot())，可为 None

        Returns:
            内省报告 dict (见模块 docstring)
        """
        dimensions: dict[str, Optional[dict[str, Any]]] = {}
        scores: list[float] = []

        # ── 维度 1: 记忆健康 ──
        if memory_autonomy is not None:
            try:
                diagnosis = memory_autonomy.diagnose()
                mem_score = self.memory_health_score(diagnosis)
                top_weak_raw = diagnosis.get("top_weak", [])
                top_weak = [
                    {"content": w.get("description", ""), "strength": w.get("strength", 0.0)}
                    for w in (top_weak_raw or [])
                ]
                dimensions["memory_health"] = {
                    "score": mem_score,
                    "details": {
                        "total": diagnosis.get("total_memories", 0),
                        "strong": diagnosis.get("strong_count", 0),
                        "weak": diagnosis.get("weak_count", 0),
                        "stale": diagnosis.get("stale_count", 0),
                        "half_life_ticks": int(
                            diagnosis.get("forgetting_half_life_seconds", 0)
                        ),
                    },
                    "top_weak": top_weak,
                }
                scores.append(mem_score)
                logger.debug(
                    "memory_health score=%.1f for %s", mem_score, self.agent_name,
                )
            except Exception:
                logger.exception(
                    "memory_health assessment failed for %s", self.agent_name,
                )
                dimensions["memory_health"] = None
        else:
            dimensions["memory_health"] = None

        # ── 维度 2: 计划执行 ──
        if plan_engine is not None:
            try:
                history = plan_engine.get_history(self.agent_name)
                plan_stats = self.plan_success_rate(history)
                plan_score = round(
                    min(100.0, plan_stats["success_rate"] * 100.0), 1
                )
                dimensions["plan_execution"] = {
                    "score": plan_score,
                    "details": plan_stats,
                }
                scores.append(plan_score)
                logger.debug(
                    "plan_execution score=%.1f for %s",
                    plan_score, self.agent_name,
                )
            except Exception:
                logger.exception(
                    "plan_execution assessment failed for %s", self.agent_name,
                )
                dimensions["plan_execution"] = None
        else:
            dimensions["plan_execution"] = None

        # ── 维度 3: 世界模型 ──
        if world_model is not None:
            try:
                snapshot = world_model.get_snapshot()
                wm_score = self.world_model_maturity(snapshot)
                dimensions["world_model"] = {
                    "score": wm_score,
                    "details": {
                        "rules_count": snapshot.get("rules_count", 0),
                        "episodes_count": snapshot.get("episodes_count", 0),
                        "avg_confidence": snapshot.get("avg_confidence", 0.0),
                    },
                }
                scores.append(wm_score)
                logger.debug(
                    "world_model score=%.1f for %s", wm_score, self.agent_name,
                )
            except Exception:
                logger.exception(
                    "world_model assessment failed for %s", self.agent_name,
                )
                dimensions["world_model"] = None
        else:
            dimensions["world_model"] = None

        # ── 综合评分: 只计算可用维度 ──
        if scores:
            overall_score = round(sum(scores) / len(scores), 1)
        else:
            overall_score = 0.0

        return {
            "agent_name": self.agent_name,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "overall_score": overall_score,
            "dimensions": dimensions,
        }

    # ── 评分算法 ──────────────────────────────

    @staticmethod
    def memory_health_score(diagnosis: dict[str, Any]) -> float:
        """0-100 记忆健康评分。

        公式: (strong / total) * 70 + 时效性奖励 (最多 30)
        - strong: 强度 > 0.7 的记忆
        - total: 总记忆数
        - 时效性奖励: 如果 stale 占比低则加分 (最多 30)

        若 total == 0 则返回 0。
        """
        total = diagnosis.get("total_memories", 0)
        if total == 0:
            return 0.0

        strong = diagnosis.get("strong_count", 0)
        stale = diagnosis.get("stale_count", 0)

        # 基础分: 强记忆占比
        base = (strong / total) * 70.0

        # 时效性奖励: 过期记忆越少越好
        stale_ratio = stale / total
        if stale_ratio <= 0.05:
            freshness_bonus = 30.0
        elif stale_ratio <= 0.15:
            freshness_bonus = 20.0
        elif stale_ratio <= 0.30:
            freshness_bonus = 10.0
        else:
            freshness_bonus = 0.0

        return round(min(100.0, base + freshness_bonus), 1)

    @staticmethod
    def plan_success_rate(history: list[Any]) -> dict[str, Any]:
        """统计计划执行成功率。

        Args:
            history: PlanCheckpoint 对象列表

        Returns:
            {"completed": int, "active": int, "abandoned": int,
             "total": int, "success_rate": float}
        """
        completed = 0
        active = 0
        abandoned = 0

        for cp in history:
            status_name = getattr(cp, "status", None)
            if status_name is None:
                continue
            # PlanStatus enum: .name gives the string
            s = status_name.name if hasattr(status_name, "name") else str(status_name)
            s_lower = s.lower()
            if s_lower == "completed":
                completed += 1
            elif s_lower == "active":
                active += 1
            elif s_lower in ("abandoned", "superseded"):
                abandoned += 1

        total = len(history)
        if total == 0:
            return {
                "completed": 0, "active": 0, "abandoned": 0,
                "total": 0, "success_rate": 0.0,
            }

        success_rate = completed / total

        return {
            "completed": completed,
            "active": active,
            "abandoned": abandoned,
            "total": total,
            "success_rate": round(success_rate, 3),
        }

    @staticmethod
    def world_model_maturity(snapshot: dict[str, Any]) -> float:
        """0-100 世界模型成熟度评分。

        公式: 规则数 * 15 + 情节数 * 0.5, cap 100。
        """
        rules = snapshot.get("rules_count", 0)
        episodes = snapshot.get("episodes_count", 0)

        raw = rules * 15.0 + episodes * 0.5
        return round(min(100.0, raw), 1)


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────

_insight_engine: Optional[AgentInsightEngine] = None


def get_insight_engine(agent_name: str = "default") -> AgentInsightEngine:
    """获取或创建 AgentInsightEngine 实例。

    注意：此单例按 last-used agent_name 缓存，适合单 agent 场景。
    多 agent 场景应直接实例化 AgentInsightEngine(name) 或
    每个 agent 调用前先 reset。

    Args:
        agent_name: agent 名称，默认 "default"

    Returns:
        AgentInsightEngine 实例
    """
    global _insight_engine
    if _insight_engine is None:
        _insight_engine = AgentInsightEngine(agent_name=agent_name)
    elif _insight_engine.agent_name != agent_name:
        _insight_engine = AgentInsightEngine(agent_name=agent_name)
    return _insight_engine


def reset_insight_engine() -> None:
    """重置全局内省引擎（测试用）。"""
    global _insight_engine
    _insight_engine = None

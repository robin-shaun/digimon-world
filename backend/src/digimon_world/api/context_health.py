"""
上下文质量 API — Phase 25 Task 3
================================

提供 ContextQualitySnapshot 的诊断和概览接口:

- GET /api/digimon/{name}/context-health — 单只数码兽的上下文健康详情
- GET /api/context/overview — 整个世界层面的上下文健康概览

与 context_quality.py 集成，通过 get_health_monitor() / get_optimizer() 访问。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..world import get_world
from ..world.context_quality import (
    ContextQualitySnapshot,
    get_health_monitor,
    get_optimizer,
)

# ── 上下文概览路由 (prefix="/api") — 被 app.py import 为 context_health_router ──
router = APIRouter(prefix="/api", tags=["context_quality"])

# ── 数码兽上下文健康路由 (prefix="/api/digimon") — 被 app.py import 为 digimon_context_health_router ──
digimon_context_health_router = APIRouter(prefix="/api/digimon", tags=["context_quality"])


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _snapshot_to_dimensions(snap: ContextQualitySnapshot) -> dict[str, Any]:
    """将快照转换为维度字典，用于 API 响应。"""
    return {
        "staleness": snap.memory_staleness,
        "relevance": snap.memory_relevance,
        "currency": snap.plan_currency,
        "coverage": snap.world_model_coverage,
        "coherence": snap.coherence_score,
        "size": snap.context_size_estimate,
    }


def _health_distribution(snapshots: list[ContextQualitySnapshot]) -> dict[str, int]:
    """按 composite_health 阈值统计分布。

    阈值:
        < 30  → critical
        < 60  → warning
        >= 60 → healthy
    """
    critical = 0
    warning = 0
    healthy = 0
    for snap in snapshots:
        score = snap.composite_health
        if score < 30:
            critical += 1
        elif score < 60:
            warning += 1
        else:
            healthy += 1
    return {"critical": critical, "warning": warning, "healthy": healthy}


# ---------------------------------------------------------------------------
# 路由: GET /api/digimon/{name}/context-health
# ---------------------------------------------------------------------------

@digimon_context_health_router.get("/{name}/context-health")
def get_context_health(name: str) -> dict[str, Any]:
    """返回指定数码兽的最新上下文质量快照、诊断问题和优化建议。

    先通过 WorldState 验证数码兽是否存在，
    再从 ContextHealthMonitor 获取最新快照，
    若无快照则返回 404。
    """
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")

    monitor = get_health_monitor()
    snapshot = monitor.latest_snapshot(name)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No context health snapshot exists for '{name}' yet. "
                    "Snapshots are generated each tick — wait for the scheduler to run.",
        )

    issues = monitor.diagnose(snapshot)
    optimizer = get_optimizer()
    recommendations = optimizer.recommend(snapshot, issues)

    return {
        "agent": snapshot.agent_name,
        "tick": snapshot.tick,
        "composite_health": snapshot.composite_health,
        "dimensions": _snapshot_to_dimensions(snapshot),
        "issues": [issue.to_dict() for issue in issues],
        "recommendations": [rec.to_dict() for rec in recommendations],
    }


# ---------------------------------------------------------------------------
# 路由: GET /api/context/overview
# ---------------------------------------------------------------------------

@router.get("/context/overview")
def get_context_overview() -> dict[str, Any]:
    """返回整个世界层面的上下文健康概览。

    列出所有有快照记录的 agent，按 composite_health 升序
    （最差的排最前），并计算平均健康度、最差 5 名及健康分布。
    """
    monitor = get_health_monitor()
    agent_names = monitor.all_agents

    if not agent_names:
        return {
            "total_agents": 0,
            "average_health": 0.0,
            "worst_5": [],
            "health_distribution": {"critical": 0, "warning": 0, "healthy": 0},
        }

    snapshots: list[ContextQualitySnapshot] = []
    for name in agent_names:
        snap = monitor.latest_snapshot(name)
        if snap is not None:
            snapshots.append(snap)

    # 按 composite_health 升序（最差排第一）
    snapshots.sort(key=lambda s: s.composite_health)

    total = len(snapshots)
    average_health = round(
        sum(s.composite_health for s in snapshots) / total, 2
    ) if total > 0 else 0.0

    worst_5 = [
        {
            "agent": s.agent_name,
            "composite_health": s.composite_health,
            "tick": s.tick,
        }
        for s in snapshots[:5]
    ]

    return {
        "total_agents": total,
        "average_health": average_health,
        "worst_5": worst_5,
        "health_distribution": _health_distribution(snapshots),
    }


__all__ = ["router", "digimon_context_health_router"]

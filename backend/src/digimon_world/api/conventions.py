"""
共享惯例 API — Phase 22 Task 2
==============================

提供 ConventionPool 的查询接口,让前端能查看:
- 当前活跃的共享惯例 (术语/行为/仪式)
- 单条惯例的详细信息 (包括所有采用者)
- 某只数码兽已采用的所有惯例

与 shared_conventions.py 中的 ConventionPool 单例集成,
通过 get_convention_pool() 访问。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..world import get_world
from ..world.shared_conventions import Convention, get_convention_pool

# ── 惯例路由 (prefix="/api/conventions") ──
router = APIRouter(prefix="/api/conventions", tags=["conventions"])

# ── 数码兽惯例路由 (prefix="/api/digimon") ──
digimon_conventions_router = APIRouter(prefix="/api/digimon", tags=["conventions"])


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _convention_to_dict(conv: Convention) -> dict[str, Any]:
    """将 Convention 数据类序列化为 JSON 友好的字典。

    datetime 字段转为 ISO 8601 字符串,
    计算属性 (adoption_count, is_active) 一并输出。
    """
    def _iso(dt: datetime) -> str:
        return dt.isoformat()

    return {
        "convention_id": conv.convention_id,
        "term": conv.term,
        "category": conv.category,
        "source_agents": list(conv.source_agents),
        "adopter_agents": list(conv.adopter_agents),
        "first_seen": _iso(conv.first_seen),
        "last_used": _iso(conv.last_used),
        "use_count": conv.use_count,
        "strength": round(conv.strength, 3),
        "half_life_seconds": conv.half_life_seconds,
        "adoption_count": conv.adoption_count,
        "is_active": conv.is_active,
    }


# ---------------------------------------------------------------------------
# 路由: GET /api/conventions
# ---------------------------------------------------------------------------

@router.get("")
def list_conventions(
    sort_by: str = "adoption_count",
    category: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """返回活跃惯例列表 + 惯例池统计。

    Query params:
        sort_by:  排序方式 — "adoption_count" | "strength" | "use_count" | "recent"
        category: 按类别过滤 — "term" | "behavior" | "ritual"
        limit:    返回数量上限 (默认 50)
    """
    pool = get_convention_pool()
    # 验证 sort_by
    allowed = {"adoption_count", "strength", "use_count", "recent"}
    if sort_by not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by '{sort_by}'. Must be one of: {', '.join(sorted(allowed))}",
        )

    if category:
        conventions = pool.get_by_category(category)
        if sort_by == "strength":
            conventions.sort(key=lambda c: c.strength, reverse=True)
        elif sort_by == "use_count":
            conventions.sort(key=lambda c: c.use_count, reverse=True)
        elif sort_by == "recent":
            conventions.sort(key=lambda c: c.last_used, reverse=True)
        else:
            conventions.sort(key=lambda c: c.adoption_count, reverse=True)
        conventions = conventions[:limit]
    else:
        conventions = pool.get_active(sort_by=sort_by, limit=limit)

    return {
        "stats": pool.stats(),
        "count": len(conventions),
        "conventions": [_convention_to_dict(c) for c in conventions],
    }


# ---------------------------------------------------------------------------
# 路由: GET /api/conventions/{convention_id}
# ---------------------------------------------------------------------------

@router.get("/{convention_id}")
def get_convention(convention_id: str) -> dict[str, Any]:
    """返回单条惯例的完整详情,包括所有采用者列表。"""
    pool = get_convention_pool()
    conv = pool.get(convention_id)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Convention '{convention_id}' not found",
        )
    return _convention_to_dict(conv)


# ---------------------------------------------------------------------------
# 路由: GET /api/digimon/{name}/conventions
# ---------------------------------------------------------------------------

@digimon_conventions_router.get("/{name}/conventions")
def get_digimon_conventions(name: str) -> dict[str, Any]:
    """返回指定数码兽已采用的所有惯例。

    先通过 WorldState 验证数码兽是否存在,
    再从 ConventionPool 中检索其惯例。
    """
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")

    pool = get_convention_pool()
    conventions = pool.get_by_agent(name)
    return {
        "digimon": name,
        "species": agent.species,
        "count": len(conventions),
        "conventions": [_convention_to_dict(c) for c in conventions],
    }


__all__ = ["digimon_conventions_router", "router"]

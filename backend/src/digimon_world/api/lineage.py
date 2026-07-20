"""
世代传承 API — Phase 30
========================

提供族谱查询和孵化管理接口:
- GET /api/lineage/stats      — 世代统计
- GET /api/lineage/tree       — 世界族谱总览
- GET /api/lineage/{name}     — 某数码兽的家族树

与 world/lineage.py 中的 LineageTracker 单例集成，
通过 get_lineage_tracker() 访问。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..world.egg_incubation import get_hatchery
from ..world.lineage import get_lineage_tracker

logger = logging.getLogger(__name__)

# ── 族谱路由 (prefix="/api/lineage") ──
router = APIRouter(prefix="/api/lineage", tags=["lineage"])


# ⚠️ 固定路由必须在参数化路由之前定义，否则 /stats 会被 /{name} 捕获


# ---------------------------------------------------------------------------
# 端点: 世代统计
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_lineage_stats() -> dict[str, Any]:
    """获取世代统计信息。

    返回: 总代数、最深代数、每代个体数、最多产数码兽、始祖列表。
    """
    tracker = get_lineage_tracker()
    stats = tracker.stats()

    # 附加孵化器统计
    hatchery = get_hatchery()
    hatchery_stats = hatchery.stats()

    return {
        "lineage": stats,
        "hatchery": hatchery_stats,
    }


# ---------------------------------------------------------------------------
# 端点: 世界族谱总览
# ---------------------------------------------------------------------------


@router.get("/tree")
async def get_world_tree() -> dict[str, Any]:
    """获取世界族谱总览。

    返回:
    - records: 所有亲子关系记录列表
    - families: 按始祖分组的家族列表
    - hatchery: 孵化器当前状态
    """
    tracker = get_lineage_tracker()
    stats = tracker.stats()
    all_records = tracker.all_records()

    # 按家族（始祖）分组
    founders = stats.get("founders", [])
    families: list[dict[str, Any]] = []
    for founder in founders:
        descendants = tracker.get_descendants(founder)
        families.append({
            "founder": founder,
            "generation": tracker.get_generation(founder),
            "descendants_count": len(descendants),
            "descendants": descendants[:20],  # 截断以防过长
        })

    # 孵化器状态
    hatchery = get_hatchery()
    hatchery_stats = hatchery.stats()
    incubating = [e.to_dict() for e in hatchery.incubating_eggs()]

    return {
        "stats": stats,
        "total_records": len(all_records),
        "families": families,
        "hatchery": {
            "stats": hatchery_stats,
            "incubating": incubating,
        },
    }


# ---------------------------------------------------------------------------
# 端点: 单个数码兽家族树 (必须在 /stats 和 /tree 之后)
# ---------------------------------------------------------------------------


@router.get("/{name}")
async def get_family_tree(name: str) -> dict[str, Any]:
    """获取某数码兽的家族树。

    返回: parents, children, siblings, generation, descendants_count。
    如果 name 不在族谱中，返回 404。
    """
    tracker = get_lineage_tracker()
    tree = tracker.get_family_tree(name)

    # 如果 generation 为 None 且无父母记录 → 可能不存在于族谱中
    if tree["generation"] is None and tree["parents"] is None and not tree["children"] and not tree["siblings"]:
        # 但仍可能是始祖（Gen 0 在 set_founders 后） — 检查 generation_of
        gen = tracker.get_generation(name)
        if gen is None:
            raise HTTPException(status_code=404, detail=f"数码兽 '{name}' 不在族谱中")

    # 附加孵化中的蛋（如果此数码兽是父母之一）
    hatchery = get_hatchery()
    tree["eggs_as_parent"] = [e.to_dict() for e in hatchery.eggs_from_parent(name)]

    # 附加已孵化的后代蛋
    hatched_eggs = [
        h.to_dict() for h in hatchery.hatched_results()
        if h.parent_a == name or h.parent_b == name
    ]
    tree["hatched_eggs"] = hatched_eggs

    return tree

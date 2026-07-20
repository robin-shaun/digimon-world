"""
WorldAlmanac API — Phase 29
===========================

提供数码世界年鉴的查询接口，让前端能查看:
- 所有已归档章节的摘要列表 + 实时快照
- 单个章节的完整详情 (快照、精选事件、趋势、名人堂)
- 当前时刻的实时世界快照 (未归档)

与 world/world_almanac.py 中的 WorldAlmanac 单例集成，
通过 get_almanac() 访问。

设计要点:
- WorldSnapshot / AlmanacChapter 等均为 dataclass，需手动序列化为 dict
- 路由前缀由 APIRouter 统一管理，路径装饰器中不重复前缀
- /current 端点必须排在 /{epoch} 之前，避免 FastAPI 将 "current" 当作 epoch 参数
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..world import get_registry, get_world
from ..world.events import get_world_tick
from ..world.world_almanac import (
    AlmanacChapter,
    CuratedEvent,
    HallOfFame,
    HallOfFameEntry,
    TrendReport,
    WorldAlmanac,
    WorldSnapshot,
)

# ── 年鉴路由 (prefix="/api/almanac") ──
router = APIRouter(prefix="/api/almanac", tags=["almanac"])

# ── 模块级单例 ──
_almanac: WorldAlmanac | None = None


def get_almanac() -> WorldAlmanac:
    """获取全局 WorldAlmanac 单例。

    首次调用时自动创建。用于 scheduler / API 端点访问。
    """
    global _almanac
    if _almanac is None:
        _almanac = WorldAlmanac()
    return _almanac


# ---------------------------------------------------------------------------
# 序列化工具
# ---------------------------------------------------------------------------


def _snapshot_to_dict(snap: WorldSnapshot) -> dict[str, Any]:
    """将 WorldSnapshot dataclass 序列化为 JSON 友好的字典。"""
    return {
        "tick": snap.tick,
        "world_time": snap.world_time,
        "total_digimon": snap.total_digimon,
        "active_digimon": snap.active_digimon,
        "dormant_digimon": snap.dormant_digimon,
        "avg_energy": snap.avg_energy,
        "total_knowledge_items": snap.total_knowledge_items,
        "total_conventions": snap.total_conventions,
        "faction_count": snap.faction_count,
        "avg_coherence_score": snap.avg_coherence_score,
        "personality_distribution": snap.personality_distribution,
        "region_populations": snap.region_populations,
        "evolution_distribution": snap.evolution_distribution,
    }


def _event_to_dict(evt: CuratedEvent) -> dict[str, Any]:
    """将 CuratedEvent dataclass 序列化为字典。"""
    return {
        "event_type": evt.event_type,
        "title": evt.title,
        "description": evt.description,
        "tick": evt.tick,
        "world_time": evt.world_time,
        "significance": evt.significance,
        "participants": evt.participants,
        "location": evt.location,
    }


def _trends_to_dict(trends: TrendReport | None) -> dict[str, Any] | None:
    """将 TrendReport dataclass 序列化为字典。"""
    if trends is None:
        return None
    return {
        "personality_shifts": trends.personality_shifts,
        "knowledge_growth": trends.knowledge_growth,
        "energy_trend": trends.energy_trend,
        "faction_changes": trends.faction_changes,
        "population_change": trends.population_change,
        "coherence_trend": trends.coherence_trend,
    }


def _hall_entry_to_dict(entry: HallOfFameEntry) -> dict[str, Any]:
    """将 HallOfFameEntry dataclass 序列化为字典。"""
    return {
        "name": entry.name,
        "value": entry.value,
        "detail": entry.detail,
    }


def _hall_of_fame_to_dict(hall: HallOfFame | None) -> dict[str, Any] | None:
    """将 HallOfFame dataclass 序列化为字典。"""
    if hall is None:
        return None
    return {
        "top_fighters": [_hall_entry_to_dict(e) for e in hall.top_fighters],
        "top_inventors": [_hall_entry_to_dict(e) for e in hall.top_inventors],
        "top_socializers": [_hall_entry_to_dict(e) for e in hall.top_socializers],
        "top_altruists": [_hall_entry_to_dict(e) for e in hall.top_altruists],
        "most_evolved": [_hall_entry_to_dict(e) for e in hall.most_evolved],
    }


def _chapter_to_dict(chapter: AlmanacChapter) -> dict[str, Any]:
    """将 AlmanacChapter dataclass 完整序列化为字典。

    包含所有嵌套 dataclass 的递归序列化:
    WorldSnapshot, list[CuratedEvent], TrendReport, HallOfFame。
    """
    return {
        "epoch": chapter.epoch,
        "tick_start": chapter.tick_start,
        "tick_end": chapter.tick_end,
        "world_time_start": chapter.world_time_start,
        "world_time_end": chapter.world_time_end,
        "snapshot": _snapshot_to_dict(chapter.snapshot),
        "top_events": [_event_to_dict(e) for e in chapter.top_events],
        "trends": _trends_to_dict(chapter.trends),
        "hall_of_fame": _hall_of_fame_to_dict(chapter.hall_of_fame),
        "generated_at": chapter.generated_at,
        "event_count": chapter.event_count,
        "narrative_summary": chapter.narrative_summary,
    }


def _chapter_summary_to_dict(chapter: AlmanacChapter) -> dict[str, Any]:
    """将章节精简为摘要字典 (不含完整快照/事件/趋势/名人堂详情)。"""
    return {
        "epoch": chapter.epoch,
        "tick_start": chapter.tick_start,
        "tick_end": chapter.tick_end,
        "world_time_start": chapter.world_time_start,
        "world_time_end": chapter.world_time_end,
        "event_count": chapter.event_count,
        "narrative_summary": chapter.narrative_summary,
        "generated_at": chapter.generated_at,
    }


# ---------------------------------------------------------------------------
# 辅助: 从世界状态收集数据
# ---------------------------------------------------------------------------


def _build_digimon_data(world) -> list[dict[str, Any]]:
    """从当前世界状态提取数码兽数据，转为 WorldAlmanac 消费格式。

    提取字段: name, energy, personality (mbti), region_id, evolution (stage),
    battle_victories, memory_count, knowledge_invented, energy_donated,
    evolution_score, knowledge_citations。
    """
    agents = world.all()
    digimon_data: list[dict[str, Any]] = []
    for a in agents:
        # 防御性读取: 使用 getattr 处理可能缺失的属性
        memory_stream = getattr(a, "memory_stream", None)
        memory_count = (
            len(memory_stream.memories)
            if memory_stream and hasattr(memory_stream, "memories")
            else 0
        )

        stage_obj = getattr(a, "stage", None)
        stage_value = (
            stage_obj.value if stage_obj and hasattr(stage_obj, "value") else "rookie"
        )

        digimon_data.append({
            "name": a.name,
            "energy": {"current": getattr(a, "energy", 100)},
            "personality": {"mbti": getattr(a, "mbti_type", "UNKN")},
            "region_id": a.region_id,
            "evolution": {"stage": stage_value},
            "battle_victories": getattr(a, "battle_victories", 0),
            "memory_count": memory_count,
            "knowledge_invented": getattr(a, "invention_count", 0),
            "energy_donated": 0.0,
            "evolution_score": getattr(a, "evolution_score", 0),
            "knowledge_citations": getattr(a, "knowledge_citations", 0),
        })
    return digimon_data


def _build_snapshot_data() -> dict[str, Any]:
    """构建世界快照元数据 (knowledge / conventions / factions / coherence)。

    尝试从各子系统导入并收集数据，导入失败则使用默认值。
    """
    snapshot_data: dict[str, Any] = {
        "total_knowledge_items": 0,
        "total_conventions": 0,
        "faction_count": 0,
        "avg_coherence_score": 0.0,
    }

    # 知识经济: 统计知识池条目数
    try:
        from ..economy.knowledge_economy import get_knowledge_pool

        pool = get_knowledge_pool()
        snapshot_data["total_knowledge_items"] = (
            len(pool.items) if hasattr(pool, "items") else 0
        )
    except Exception:
        pass

    # 共享惯例: 统计活跃惯例数
    try:
        from ..world.shared_conventions import get_convention_pool

        cp = get_convention_pool()
        snapshot_data["total_conventions"] = (
            len(cp.active) if hasattr(cp, "active") else 0
        )
    except Exception:
        pass

    # 派系注册表: 统计派系数
    try:
        registry = get_registry()
        snapshot_data["faction_count"] = len(registry.all_factions())
    except Exception:
        pass

    # 叙事一致性: 获取最近评分
    try:
        from ..world.narrative_coherence import get_coherence_engine

        ce = get_coherence_engine()
        snapshot_data["avg_coherence_score"] = getattr(ce, "last_score", 0.0)
    except Exception:
        pass

    return snapshot_data


# ---------------------------------------------------------------------------
# 路由: GET /api/almanac  (列表 + 实时快照)
# ---------------------------------------------------------------------------


@router.get("/")
def list_chapters() -> dict[str, Any]:
    """返回所有已归档章节的摘要列表，以及当前实时世界快照。

    章节按 epoch 升序排列，每条仅包含概要字段。
    如果世界正在运行，同时返回 current_snapshot (未归档)。
    """
    almanac = get_almanac()
    chapters = almanac.list_chapters()

    # 尝试构建当前实时快照
    current_snapshot: dict[str, Any] | None = None
    try:
        world = get_world()
        tick = get_world_tick()
        world_time = f"Day {tick // 1440 + 1}, {(tick % 1440) // 60:02d}:{tick % 60:02d}"
        digimon_data = _build_digimon_data(world)
        snapshot_data = _build_snapshot_data()

        snap = almanac.get_current_snapshot(tick, world_time, snapshot_data, digimon_data)
        current_snapshot = _snapshot_to_dict(snap)
    except Exception:
        # 世界未初始化或其他错误时，不返回快照
        pass

    return {
        "total_chapters": len(chapters),
        "chapters": [_chapter_summary_to_dict(c) for c in chapters],
        "current_snapshot": current_snapshot,
    }


# ---------------------------------------------------------------------------
# 路由: GET /api/almanac/current  (实时快照)
# ---------------------------------------------------------------------------
# 注意: 此路由必须在 GET /{epoch} 之前定义，
# 否则 FastAPI 会将 "current" 匹配为 epoch 路径参数。


@router.get("/current")
def get_current_snapshot() -> dict[str, Any]:
    """返回当前时刻的世界实时快照 (未归档)。

    从世界状态中收集数码兽数据、事件列表、快照元数据，
    调用 WorldAlmanac.get_current_snapshot() 构建 WorldSnapshot 并序列化返回。
    """
    almanac = get_almanac()
    world = get_world()

    tick = get_world_tick()
    world_time = f"Day {tick // 1440 + 1}, {(tick % 1440) // 60:02d}:{tick % 60:02d}"

    # 数码兽数据
    digimon_data = _build_digimon_data(world)

    # 快照元数据
    snapshot_data = _build_snapshot_data()

    # 构建实时快照
    snap = almanac.get_current_snapshot(tick, world_time, snapshot_data, digimon_data)

    # 附带近期事件列表 (世界事件流)
    events = world.events if hasattr(world, "events") else []
    recent_events: list[dict[str, Any]] = []
    for evt in events[-20:]:  # 最近 20 个事件
        if isinstance(evt, dict):
            recent_events.append({
                "type": evt.get("type", "unknown"),
                "tick": evt.get("tick", 0),
                "world_time": evt.get("world_time", evt.get("at", "")),
                "significance": evt.get("significance", 0),
                "description": evt.get("description", evt.get("line", "")),
            })

    return {
        "snapshot": _snapshot_to_dict(snap),
        "tick": tick,
        "world_time": world_time,
        "digimon_count": len(digimon_data),
        "recent_events": recent_events,
    }


# ---------------------------------------------------------------------------
# 路由: GET /api/almanac/{epoch}  (单章节详情)
# ---------------------------------------------------------------------------


@router.get("/{epoch}")
def get_chapter(epoch: int) -> dict[str, Any]:
    """返回指定 epoch 的年鉴章节完整详情。

    包含: 世界快照、精选事件 Top 20、趋势报告、名人堂、叙事摘要。
    若 epoch 不存在则返回 404。
    """
    almanac = get_almanac()
    chapter = almanac.get_chapter(epoch)
    if chapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Almanac chapter for epoch {epoch} not found. "
            f"Available epochs: {list(almanac._chapters.keys())}",
        )
    return _chapter_to_dict(chapter)


__all__ = ["get_almanac", "router"]

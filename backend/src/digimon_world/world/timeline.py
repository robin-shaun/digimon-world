"""
TimelineSystem - 数码世界大事记时间线
=====================================

世界的事件流(world.events)里什么都有:每一次移动、每一次观察、每一枚
digital_bit 落袋……绝大多数是高频噪声,对"看故事"的人毫无意义。TimelineSystem
从这条洪流里筛出**重大事件**——进化、战斗、天灾、节日、剧情、跨世界之门、初遇、
叙事告警——把它们格式化成带图标 + 可读标题的时间线条目,最新在前返回。

设计要点:
- 纯查询、纯内存、无副作用:read-only 地扫一遍 world.events,不改世界状态。
- 每条条目的 id == 它在 world.events 里的原始索引 → 稳定、可回溯到源事件。
- 只收录 SIGNIFICANT_TYPES 里的类型,其余(moved/observed/bit_earned/dialogue…)
  一律滤掉。
- 每种类型有自己的标题格式化器 + 图标;缺字段时优雅兜底,不抛异常。
- limit 夹到 [1, MAX_LIMIT],再不越过实际条数。

典型用法::

    ts = TimelineSystem()
    ts.build(world, limit=50)   # -> list[dict],最新在前
    ts.to_dict(world)           # GET /api/timeline 用: {count, total_events, events}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .world_state import WorldState


# limit 上限(防止一次拉回过多条目)
MAX_LIMIT: int = 200

# 收录进时间线的重大事件类型(其余一律视作噪声滤掉)
SIGNIFICANT_TYPES: frozenset[str] = frozenset({
    "evolution",          # 进化
    "battle",             # 战斗
    "disaster",           # 天灾降临
    "festival",           # 节日
    "story_event",        # 剧情事件
    "digital_gate",       # 跨世界之门
    "first_meet",         # 两只数码兽初遇
    "narrative_warning",  # 叙事一致性告警
})

# 每种类型的图标(前端时间线显示用)
_ICONS: dict[str, str] = {
    "evolution": "✨",
    "battle": "⚔️",
    "disaster": "🌋",
    "festival": "🎏",
    "story_event": "📜",
    "digital_gate": "🌀",
    "first_meet": "🤝",
    "narrative_warning": "⚠️",
}


def _title_evolution(e: dict[str, Any]) -> str:
    return str(e.get("description") or "一只数码兽进化了")


def _title_battle(e: dict[str, Any]) -> str:
    attacker = e.get("attacker", "?")
    defender = e.get("defender", "?")
    winner = e.get("winner")
    if winner:
        return f"{attacker} vs {defender}:{winner} 获胜"
    return f"{attacker} vs {defender}:平局"


def _title_disaster(e: dict[str, Any]) -> str:
    label = e.get("label") or "天灾"
    return f"{label}降临数码世界"


def _title_festival(e: dict[str, Any]) -> str:
    label = e.get("label") or "节日"
    return f"{label}举行"


def _title_story_event(e: dict[str, Any]) -> str:
    return str(e.get("description") or "剧情推进")


def _title_digital_gate(e: dict[str, Any]) -> str:
    agent = e.get("agent", "?")
    direction = e.get("direction")
    to_world = e.get("to_world", "?")
    from_world = e.get("from_world", "?")
    if direction == "arrive":
        return f"{agent} 穿过数码之门抵达 {to_world}"
    return f"{agent} 穿过数码之门离开 {from_world}"


def _title_first_meet(e: dict[str, Any]) -> str:
    return str(e.get("description") or "两只数码兽初次相遇")


def _title_narrative_warning(e: dict[str, Any]) -> str:
    return str(e.get("description") or "叙事一致性告警")


# 类型 -> 标题格式化器
_TITLE_BUILDERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "evolution": _title_evolution,
    "battle": _title_battle,
    "disaster": _title_disaster,
    "festival": _title_festival,
    "story_event": _title_story_event,
    "digital_gate": _title_digital_gate,
    "first_meet": _title_first_meet,
    "narrative_warning": _title_narrative_warning,
}


class TimelineSystem:
    """从世界事件流里提炼重大事件时间线(纯查询)。"""

    def build(self, world: "WorldState", limit: int = 50) -> list[dict[str, Any]]:
        """扫一遍 world.events,过滤 + 格式化重大事件,最新在前返回。

        Args:
            world: 世界状态(只读)。
            limit: 最多返回多少条;夹到 [1, MAX_LIMIT]。

        Returns:
            时间线条目列表,最新在前。每条:
            {id, type, icon, title, importance, event(原始事件)}。
        """
        n = max(1, min(limit, MAX_LIMIT))

        entries: list[dict[str, Any]] = []
        # 倒序扫描 → 天然最新在前,凑够 n 条即停。
        for idx in range(len(world.events) - 1, -1, -1):
            event = world.events[idx]
            etype = event.get("type")
            if etype not in SIGNIFICANT_TYPES:
                continue
            entries.append(self._format(idx, etype, event))
            if len(entries) >= n:
                break
        return entries

    def _format(self, idx: int, etype: str, event: dict[str, Any]) -> dict[str, Any]:
        """把一条原始事件格式化成时间线条目。"""
        builder = _TITLE_BUILDERS.get(etype)
        title = builder(event) if builder else str(event.get("description") or etype)
        return {
            "id": idx,
            "type": etype,
            "icon": _ICONS.get(etype, "•"),
            "title": title,
            "importance": event.get("importance", 5),
            "event": event,
        }

    def to_dict(self, world: "WorldState", limit: int = 50) -> dict[str, Any]:
        """时间线载荷(GET /api/timeline 用)。

        Returns:
            {count(重大事件收录数), total_events(事件流总数,含噪声), events:[...]}。
        """
        events = self.build(world, limit=limit)
        return {
            "count": len(events),
            "total_events": len(world.events),
            "events": events,
        }


# ---- 进程级单例 ----
_timeline_system: "TimelineSystem | None" = None


def get_timeline_system() -> TimelineSystem:
    """获取(或延迟初始化)时间线系统单例。"""
    global _timeline_system
    if _timeline_system is None:
        _timeline_system = TimelineSystem()
    return _timeline_system


def reset_timeline_system() -> None:
    """重置时间线系统(测试用)。"""
    global _timeline_system
    _timeline_system = None


__all__ = [
    "MAX_LIMIT",
    "SIGNIFICANT_TYPES",
    "TimelineSystem",
    "get_timeline_system",
    "reset_timeline_system",
]

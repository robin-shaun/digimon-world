"""
Timeline - 世界大事记时间线
============================

数码世界每天都在发生成百上千件小事(移动、观察、休息、捡到 bit……),但真正
值得写进"史书"的只有那几类**重大事件**: 进化、战斗、天灾、节日、剧情点火、
跨世界之门、初次相遇、叙事失控告警。本模块把散落在 ``world_state.events`` 里
的原始事件流,过滤 + 归类 + 格式化成一条**面向展示**的时间线。

设计取向 —— **按需推导, 不另存状态**:
经济 / 排行榜 / 关系那几个接口都是"实时从 world 里算",时间线沿用同样的路子。
``world_state.events`` 已经是唯一的事件真相源,时间线只是它的一个**视图**:
读取 → 只留重大类型 → 每条配上图标/标题/重要度 → 倒序(最新在前)返回。
这样不会出现"事件写了两份、两份还不一致"的老问题。

重大事件类型(``SIGNIFICANT_TYPES``)及其呈现,见 ``_FORMATTERS``。其余高频噪声
(moved / observed / rested / positions / bit_earned / dialogue……)一律过滤掉。

典型用法::

    timeline = get_timeline_system()
    entries = timeline.build(world)          # -> list[dict], 最新在前
    payload = timeline.to_dict(world, limit=50)  # GET /api/timeline 用
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from .world_state import WorldState


# ---- 重大事件类型 → 展示图标 ----
# 只有出现在这里的 type 才会进时间线;其余(moved/observed/rested/positions/
# bit_earned/dialogue/item_*/landmark_effect/step_error/echo/snapshot)全部滤掉。
EVENT_ICONS: dict[str, str] = {
    "evolution": "✨",
    "battle": "⚔️",
    "disaster": "🌪️",
    "disaster_ended": "🌤️",
    "festival": "🎉",
    "story_event": "📖",
    "digital_gate": "🌀",
    "first_meet": "🤝",
    "narrative_warning": "⚠️",
    "faction_create": "🚩",
}

# 时间线只收录这些类型(即 EVENT_ICONS 的键集合)
SIGNIFICANT_TYPES: frozenset[str] = frozenset(EVENT_ICONS)

# 默认返回条数上限
DEFAULT_LIMIT: int = 50
# 硬上限(防止前端传个超大 limit 把整段历史拖出来)
MAX_LIMIT: int = 200


# ---- 各类型的标题格式化器 ----
# 每个 formatter 接收原始事件 dict,返回一句人类可读的标题。
# 拿不到理想字段时都有兜底,绝不抛异常(见 _title)。
def _fmt_evolution(ev: dict[str, Any]) -> str:
    # evolution 事件的 description 已是"XX 进化成了 YY"式文案,直接用
    desc = ev.get("description")
    if desc:
        return str(desc)
    name = ev.get("agent") or ev.get("name") or "某只数码兽"
    return f"{name} 发生了进化"


def _fmt_battle(ev: dict[str, Any]) -> str:
    attacker = ev.get("attacker", "?")
    defender = ev.get("defender", "?")
    winner = ev.get("winner")
    if winner:
        return f"{attacker} vs {defender} — {winner} 获胜({ev.get('rounds', '?')} 回合)"
    return f"{attacker} vs {defender} — 平局"


def _fmt_disaster(ev: dict[str, Any]) -> str:
    label = ev.get("label") or ev.get("disaster") or "天灾"
    return f"{label}降临数码世界"


def _fmt_disaster_ended(ev: dict[str, Any]) -> str:
    label = ev.get("label") or ev.get("disaster") or "天灾"
    return f"{label}平息了"


def _fmt_festival(ev: dict[str, Any]) -> str:
    label = ev.get("label") or ev.get("festival") or "节日"
    return f"{label}举行"


def _fmt_digital_gate(ev: dict[str, Any]) -> str:
    agent = ev.get("agent", "某只数码兽")
    direction = ev.get("direction")
    if direction == "depart":
        return f"{agent} 穿过数码之门离开了 {ev.get('from_world', '?')}"
    if direction == "arrive":
        return f"{agent} 穿过数码之门抵达 {ev.get('to_world', '?')}"
    return f"{agent} 触发了数码之门"


def _fmt_faction_create(ev: dict[str, Any]) -> str:
    return str(ev.get("description") or "一个新派系诞生了")


# 有 description 字段的(story_event / first_meet / narrative_warning)直接透传
_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "evolution": _fmt_evolution,
    "battle": _fmt_battle,
    "disaster": _fmt_disaster,
    "disaster_ended": _fmt_disaster_ended,
    "festival": _fmt_festival,
    "digital_gate": _fmt_digital_gate,
    "faction_create": _fmt_faction_create,
}


def _title(ev: dict[str, Any]) -> str:
    """把一个原始事件 dict 格式化成一句标题(带兜底,永不抛异常)。"""
    etype = ev.get("type", "event")
    formatter = _FORMATTERS.get(etype)
    if formatter is not None:
        try:
            return formatter(ev)
        except Exception:
            pass
    # 无专用 formatter:优先用 description,再兜底成类型名
    desc = ev.get("description")
    if desc:
        return str(desc)
    return etype


class TimelineSystem:
    """世界大事记: 从 ``world_state.events`` 推导出一条重大事件时间线。

    无自有状态 —— 每次 ``build`` / ``to_dict`` 都实时读 ``world.events``,
    过滤出 ``SIGNIFICANT_TYPES``,格式化成展示条目。这样时间线永远与世界
    事件日志一致,不会漂移。
    """

    def build(
        self, world: "WorldState", limit: int = DEFAULT_LIMIT
    ) -> list[dict[str, Any]]:
        """构造时间线条目列表(最新在前)。

        每条条目字段:
        - ``id``:          事件在 ``world.events`` 里的原始索引(稳定,可作 key)
        - ``type``:        事件类型
        - ``icon``:        展示图标(emoji)
        - ``title``:       一句话摘要
        - ``description``: 原始 description(可能为 None)
        - ``importance``:  重要度(缺省 5)
        - ``at``:          时间戳 ISO 串(可能为 None)

        Args:
            world: 世界状态(读其 ``events``)。
            limit: 返回条数上限(会夹到 [1, MAX_LIMIT])。
        """
        n = max(1, min(limit, MAX_LIMIT))
        entries: list[dict[str, Any]] = []
        # enumerate 保留原始索引作为稳定 id;倒序取最新 n 条
        for idx, ev in enumerate(world.events):
            etype = ev.get("type")
            if etype not in SIGNIFICANT_TYPES:
                continue
            entries.append({
                "id": idx,
                "type": etype,
                "icon": EVENT_ICONS.get(etype, "•"),
                "title": _title(ev),
                "description": ev.get("description"),
                "importance": ev.get("importance", 5),
                "at": ev.get("at"),
            })
        # 最新在前
        entries.reverse()
        return entries[:n]

    def to_dict(
        self, world: "WorldState", limit: int = DEFAULT_LIMIT
    ) -> dict[str, Any]:
        """时间线整体状态(GET /api/timeline 用)。

        Returns:
            ``{"count": 收录条数, "total_events": 世界事件总数, "events": [...]}``。
            ``count`` 是过滤后的重大事件数,``total_events`` 是原始事件总数
            (含被过滤掉的噪声),两者之差即噪声量。
        """
        events = self.build(world, limit=limit)
        return {
            "count": len(events),
            "total_events": len(world.events),
            "events": events,
        }


# ---- 进程级单例 ----
_timeline_system: Optional[TimelineSystem] = None


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
    "DEFAULT_LIMIT",
    "EVENT_ICONS",
    "MAX_LIMIT",
    "SIGNIFICANT_TYPES",
    "TimelineSystem",
    "get_timeline_system",
    "reset_timeline_system",
]

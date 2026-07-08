"""
StoryDirector - 全局剧情事件
============================

数码世界不只是数码兽各过各的日子,还得有"大事发生"。本模块维护一批全局剧情
事件,每个事件带一个触发条件(扫描世界状态 + 关系表)。条件满足时事件"点火",
写入 world_state.events 并广播给所有数码兽的记忆。

参考 Stanford Generative Agents 里 Isabella 办派对那种"涌现叙事",这里把它做成
显式的规则引擎: 世界演化到某个临界点 → 剧情自动展开。

内置事件:
- dark_tower_awakening: 黑暗龙卷山异常波动。触发条件: 3+ 只数码兽皆已进化到 champion。
- creators_return:       创世神归来。触发条件: 关系表所有分数之和 > 200(世界足够羁绊)。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 30 tick 调一次)。
- 每个事件只触发一次(fired 标记),避免重复刷屏。
- 触发时通过 inject_fn 回调注入(默认直接 append 到 world_state.events),
  与 /api/director/inject_event 走同一条注入路径,前端 / Director 视角统一可见。

典型用法:

    director = StoryDirector()
    director.check_trigger(world, tracker)   # 扫描,满足则点火
"""

from __future__ import annotations

from typing import Any, Callable, Optional

# scheduler 每隔多少 tick 扫描一次剧情触发条件
CHECK_INTERVAL_TICKS: int = 30

# 触发阈值(避免魔数散落)
CHAMPION_COUNT_THRESHOLD: int = 3      # dark_tower: 需要至少 3 只 champion
RELATIONSHIP_SUM_THRESHOLD: float = 200.0  # creators_return: 关系总和阈值


class StoryEvent:
    """一个全局剧情事件: 条件 + 描述 + 点火状态。

    Attributes:
        event_id: 事件唯一标识
        description: 剧情文案
        importance: 重要度(注入 world 事件时带上)
        condition: (world_state, tracker) -> bool,返回 True 即满足触发条件
        fired: 是否已触发过(只触发一次)
    """

    def __init__(
        self,
        event_id: str,
        description: str,
        condition: Callable[[Any, Any], bool],
        importance: int = 9,
    ) -> None:
        self.event_id = event_id
        self.description = description
        self.condition = condition
        self.importance = importance
        self.fired = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "description": self.description,
            "importance": self.importance,
            "fired": self.fired,
        }


# ---- 内置事件的触发条件 ----
def _cond_dark_tower(world_state: Any, tracker: Any) -> bool:
    """3+ 只数码兽已进化到 champion(完全体)→ 黑暗塔苏醒。"""
    champions = 0
    for agent in world_state.all():
        stage = getattr(agent, "stage", None)
        stage_val = getattr(stage, "value", stage)
        if stage_val == "champion":
            champions += 1
    return champions >= CHAMPION_COUNT_THRESHOLD


def _cond_creators_return(world_state: Any, tracker: Any) -> bool:
    """关系表所有分数之和 > 200 → 世界羁绊足够深,创世神归来。"""
    total = sum(pair["score"] for pair in tracker.all_pairs())
    return total > RELATIONSHIP_SUM_THRESHOLD


def _default_events() -> list[StoryEvent]:
    """构造内置初始事件列表。"""
    return [
        StoryEvent(
            event_id="dark_tower_awakening",
            description="黑暗龙卷山传来异常波动,黑暗塔正在苏醒……",
            condition=_cond_dark_tower,
            importance=9,
        ),
        StoryEvent(
            event_id="creators_return",
            description="数码世界的羁绊达到顶点,创世神即将归来。",
            condition=_cond_creators_return,
            importance=10,
        ),
    ]


class StoryDirector:
    """剧情导演: 扫描世界状态,满足条件的剧情事件自动点火。"""

    def __init__(
        self,
        events: Optional[list[StoryEvent]] = None,
        inject_fn: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> None:
        # 剧情事件表(默认内置两个)
        self._events: list[StoryEvent] = events if events is not None else _default_events()
        # 注入回调: 默认在 check_trigger 时直接 append 到 world_state.events
        self._inject_fn = inject_fn

    @property
    def events(self) -> list[StoryEvent]:
        return self._events

    def check_trigger(self, world_state: Any, tracker: Any) -> list[StoryEvent]:
        """扫描所有未点火事件,条件满足则触发。

        触发动作:
        - 标记 fired = True(只触发一次)
        - 构造事件字典,append 到 world_state.events
        - 若挂了 inject_fn,再调一次(与 /api/director/inject_event 同路径)

        Returns:
            本次新点火的事件列表(可能为空)。
        """
        newly_fired: list[StoryEvent] = []
        for event in self._events:
            if event.fired:
                continue
            try:
                triggered = event.condition(world_state, tracker)
            except Exception:
                # 条件函数出错不应拖垮整个扫描
                triggered = False
            if not triggered:
                continue

            event.fired = True
            payload = {
                "type": "story_event",
                "event_id": event.event_id,
                "description": event.description,
                "importance": event.importance,
                "source": "story_director",
            }
            # 写入世界事件日志
            world_state.events.append(payload)
            # 走 inject 路径(广播 / 持久化 / Director 可见)
            if self._inject_fn is not None:
                try:
                    self._inject_fn(payload)
                except Exception:
                    pass
            newly_fired.append(event)

        return newly_fired


# ---- 进程级单例 ----
_director: Optional[StoryDirector] = None


def get_director() -> StoryDirector:
    """获取(或延迟初始化)剧情导演单例。"""
    global _director
    if _director is None:
        _director = StoryDirector()
    return _director


def reset_director() -> None:
    """重置剧情导演(测试用)。"""
    global _director
    _director = None

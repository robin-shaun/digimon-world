"""世界模拟层: 地图、地区、事件、状态、调度。

参考 Stanford: 他们的 environment/frontend_server 维护一个 world_state,
由 backend_server 的 persona 持续修改,前端订阅变化。

本模块包含:
- WorldState: 整个世界的全局状态(可序列化,持久化) — Phase 1 已实现
- Region: 一个地区(如文件岛) — Phase 1 已实现
- WorldClock: 世界时钟(独立于现实时间) — Phase 2 新增
- WorldScheduler: 周期驱动所有 agent.step() — Phase 2 新增

详细设计: docs/DESIGN.md 第 2 节
"""
from .clock import WorldClock
from .relationships import RelationshipTracker, get_tracker, reset_tracker
from .scheduler import DEFAULT_TICK_SECONDS, WorldScheduler
from .world_state import (
    DEFAULT_REGIONS,
    FILE_ISLAND,
    INFINITY_MOUNTAIN,
    Region,
    WorldState,
    get_world,
    reset_world,
)

__all__ = [
    "DEFAULT_REGIONS",
    "DEFAULT_TICK_SECONDS",
    "FILE_ISLAND",
    "INFINITY_MOUNTAIN",
    "Region",
    "RelationshipTracker",
    "WorldClock",
    "WorldScheduler",
    "WorldState",
    "get_tracker",
    "get_world",
    "reset_tracker",
    "reset_world",
]
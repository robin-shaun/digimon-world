"""世界模拟层: 地图、地区、事件、状态。

参考 Stanford: 他们的 environment/frontend_server 维护一个 world_state,
由 backend_server 的 persona 持续修改,前端订阅变化。

本模块计划包含:
- WorldState: 整个世界的全局状态(可序列化,持久化) — Phase 1 已实现
- Region: 一个地区(如文件岛) — Phase 1 已实现
- Location: 一个具体地点 — Phase 4 实现
- Event: 世界事件(战斗、对话、进化、天气) — Phase 1 简化版
- Clock: 世界时间(独立于现实时间) — Phase 1 简化版

详细设计: docs/DESIGN.md 第 2 节
"""

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
    "FILE_ISLAND",
    "INFINITY_MOUNTAIN",
    "Region",
    "WorldState",
    "get_world",
    "reset_world",
]

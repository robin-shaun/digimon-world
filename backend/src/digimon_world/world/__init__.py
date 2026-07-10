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
from . import persistence
from .clock import WorldClock
from .disasters import (
    Disaster,
    DisasterSystem,
    get_disaster_system,
    reset_disaster_system,
)
from .economy import (
    EconomySystem,
    get_economy_system,
    reset_economy_system,
)
from .events import StoryDirector, StoryEvent, get_director, reset_director
from .factions import Faction, FactionRegistry, get_registry, reset_registry
from .festivals import (
    DAYS_PER_FESTIVAL,
    Festival,
    FestivalSystem,
    get_festival_system,
    reset_festival_system,
)
from .landmarks import (
    DEFAULT_LANDMARKS,
    Landmark,
    LandmarkEffect,
    LandmarkSystem,
    get_landmark_system,
    reset_landmark_system,
)
from .multiverse import (
    PRIME_WORLD_ID,
    MultiverseManager,
    get_multiverse,
    reset_multiverse,
)
from .relationships import RelationshipTracker, get_tracker, reset_tracker
from .scheduler import DEFAULT_TICK_SECONDS, WorldScheduler
from .seasons import (
    DAYS_PER_SEASON,
    Season,
    SeasonSystem,
    get_season_system,
    reset_season_system,
)
from .timeline import (
    TimelineSystem,
    get_timeline_system,
    reset_timeline_system,
)
from .vitality import VitalitySnapshot, compute_vitality
from .weather import (
    Weather,
    WeatherSystem,
    get_weather_system,
    reset_weather_system,
)
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
    "DAYS_PER_FESTIVAL",
    "DAYS_PER_SEASON",
    "DEFAULT_REGIONS",
    "DEFAULT_TICK_SECONDS",
    "DEFAULT_LANDMARKS",
    "EconomySystem",
    "FILE_ISLAND",
    "INFINITY_MOUNTAIN",
    "PRIME_WORLD_ID",
    "Faction",
    "FactionRegistry",
    "Festival",
    "FestivalSystem",
    "Landmark",
    "LandmarkEffect",
    "LandmarkSystem",
    "MultiverseManager",
    "Region",
    "RelationshipTracker",
    "Season",
    "SeasonSystem",
    "StoryDirector",
    "StoryEvent",
    "TimelineSystem",
    "VitalitySnapshot",
    "Weather",
    "WeatherSystem",
    "WorldClock",
    "WorldScheduler",
    "WorldState",
    "compute_vitality",
    "persistence",
    "get_director",
    "get_economy_system",
    "get_festival_system",
    "get_landmark_system",
    "get_multiverse",
    "get_registry",
    "get_season_system",
    "get_timeline_system",
    "get_tracker",
    "get_weather_system",
    "get_world",
    "reset_director",
    "reset_festival_system",
    "reset_landmark_system",
    "reset_multiverse",
    "reset_registry",
    "reset_season_system",
    "reset_timeline_system",
    "reset_tracker",
    "reset_weather_system",
    "reset_world",
]
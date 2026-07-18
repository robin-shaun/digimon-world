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
from .affect_propagation import (
    CPM_CHANGE_THRESHOLD,
    AffectPropagationEngine,
)
from .dark_gears import (
    DarkGear,
    DarkGearSystem,
    get_dark_gear_system,
    reset_dark_gear_system,
)
from .daynight import (
    DayNightSystem,
    DayPeriod,
    get_daynight_system,
    reset_daynight_system,
)
from .ecology import (
    EcologySystem,
    get_ecology_system,
    reset_ecology_system,
)
from .environmental_events import (
    EnvironmentalEventSystem,
    get_env_events_system,
    reset_env_events_system,
)
from .economy import (
    EconomySystem,
    get_economy_system,
)
from ..economy import get_energy_economy, reset_energy_economy
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
from .narrator import (
    NarratorSystem,
    get_narrator,
    reset_narrator,
)
from .relational_circle import (
    AffectVector,
    RelationalCircle,
    RelationalDistance,
)
from .personality_engine import (
    MBTI_COMPATIBILITY,
    MbtiDimension,
    PersonalityEvolutionEngine,
    PersonalityProfile,
    get_personality_engine,
    reset_personality_engine,
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
from .shared_conventions import (
    Convention,
    ConventionDetector,
    ConventionPool,
    ConventionPropagation,
    get_convention_pool,
    get_convention_propagation,
    reset_convention_pool,
)
from .thinking_cost import (
    BASE_DRAIN_PER_TICK,
    DORMANCY_THRESHOLD,
    ENERGY_MAX,
    ENERGY_MIN,
    LLM_COST_DIVISOR,
    RECOVER_EAT,
    RECOVER_REST,
    RECOVER_SOCIAL,
    THINK_THRESHOLD,
    CognitiveEnergyPool,
    EnergyLedger,  # noqa: F401 — re-exported via __all__
    get_energy_ledger,
)
from .snapshots import (
    SnapshotManager,
    SnapshotMeta,
    get_snapshot_manager,
    reset_snapshot_manager,
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
    ENDLESS_OCEAN,
    FILE_ISLAND,
    INFINITY_MOUNTAIN,
    Region,
    SERVER_CONTINENT,
    SPIRAL_MOUNTAIN,
    SubRegion,
    VILLAGE_OF_BEGINNINGS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
    WorldState,
    get_world,
    reset_world,
)

__all__ = [
    "AffectPropagationEngine",
    "BASE_DRAIN_PER_TICK",
    "CognitiveEnergyPool",
    "Convention",
    "ConventionDetector",
    "ConventionPool",
    "ConventionPropagation",
    "CPM_CHANGE_THRESHOLD",
    "DAYS_PER_FESTIVAL",
    "DAYS_PER_SEASON",
    "DEFAULT_REGIONS",
    "DEFAULT_TICK_SECONDS",
    "DEFAULT_LANDMARKS",
    "DORMANCY_THRESHOLD",
    "ENERGY_MAX",
    "ENERGY_MIN",
    "EnergyLedger",
    "AffectVector",
    "DarkGear",
    "DarkGearSystem",
    "DayPeriod",
    "DayNightSystem",
    "EcologySystem",
    "EconomySystem",
    "EnvironmentalEventSystem",
    "FILE_ISLAND",
    "ENDLESS_OCEAN",
    "INFINITY_MOUNTAIN",
    "PRIME_WORLD_ID",
    "Faction",
    "FactionRegistry",
    "Festival",
    "FestivalSystem",
    "Landmark",
    "LandmarkEffect",
    "LandmarkSystem",
    "LLM_COST_DIVISOR",
    "MbtiDimension",
    "MBTI_COMPATIBILITY",
    "MultiverseManager",
    "NarratorSystem",
    "PersonalityEvolutionEngine",
    "PersonalityProfile",
    "PRIME_WORLD_ID",
    "Region",
    "RECOVER_EAT",
    "RECOVER_REST",
    "RECOVER_SOCIAL",
    "SubRegion",
    "SERVER_CONTINENT",
    "SPIRAL_MOUNTAIN",
    "VILLAGE_OF_BEGINNINGS",
    "WORLD_HEIGHT",
    "WORLD_WIDTH",
    "RelationalCircle",
    "RelationalDistance",
    "RelationshipTracker",
    "Season",
    "SeasonSystem",
    "SnapshotManager",
    "SnapshotMeta",
    "StoryDirector",
    "StoryEvent",
    "THINK_THRESHOLD",
    "TimelineSystem",
    "VitalitySnapshot",
    "Weather",
    "WeatherSystem",
    "WorldClock",
    "WorldScheduler",
    "WorldState",
    "compute_vitality",
    "persistence",
    "get_convention_pool",
    "get_convention_propagation",
    "get_dark_gear_system",
    "get_daynight_system",
    "get_director",
    "get_ecology_system",
    "get_economy_system",
    "get_energy_economy",
    "get_energy_ledger",
    "get_env_events_system",
    "get_festival_system",
    "get_landmark_system",
    "get_multiverse",
    "get_narrator",
    "get_personality_engine",
    "get_registry",
    "get_snapshot_manager",
    "get_season_system",
    "get_timeline_system",
    "get_tracker",
    "get_weather_system",
    "get_world",
    "reset_convention_pool",
    "reset_dark_gear_system",
    "reset_daynight_system",
    "reset_director",
    "reset_ecology_system",
    "reset_energy_economy",
    "reset_env_events_system",
    "reset_festival_system",
    "reset_landmark_system",
    "reset_multiverse",
    "reset_narrator",
    "reset_personality_engine",
    "reset_registry",
    "reset_season_system",
    "reset_snapshot_manager",
    "reset_timeline_system",
    "reset_tracker",
    "reset_weather_system",
    "reset_world",
]
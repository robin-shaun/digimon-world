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
from ..economy import get_energy_economy, reset_energy_economy
from . import persistence
from .affect_propagation import (
    CPM_CHANGE_THRESHOLD,
    AffectPropagationEngine,
)
from .clock import WorldClock
from .context_quality import (
    ContextHealthMonitor,
    ContextIssue,
    ContextOptimizer,
    ContextQualitySnapshot,
    get_health_monitor,
    get_optimizer,
    reset_context_quality,
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
from .economy import (
    EconomySystem,
    get_economy_system,
)
from .environmental_events import (
    EnvironmentalEventSystem,
    get_env_events_system,
    reset_env_events_system,
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
from .narrative_coherence import (
    COHERENCE_CHECK_INTERVAL,
    CoherenceEngine,
    CoherenceReport,
    RelationConflict,
    RelationConflictDetector,
    SpatialInconsistency,
    SpatialNarrativeBinder,
    get_coherence_engine,
    reset_coherence_engine,
)
from .narrator import (
    NarratorSystem,
    get_narrator,
    reset_narrator,
)
from .personality_engine import (
    MBTI_COMPATIBILITY,
    MbtiDimension,
    PersonalityEvolutionEngine,
    PersonalityProfile,
    get_personality_engine,
    reset_personality_engine,
)
from .relational_circle import (
    AffectVector,
    RelationalCircle,
    RelationalDistance,
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
from .self_model import (
    SELF_ASSESSMENT_ADJUSTMENT_RATE,
    SELF_MODEL_DIMS,
    SelfAssessmentResult,
    SelfEvaluator,
    SelfModel,
    SelfModelRegistry,
    get_self_model_registry,
    reset_self_model_registry,
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
from .snapshots import (
    SnapshotManager,
    SnapshotMeta,
    get_snapshot_manager,
    reset_snapshot_manager,
)
from .theory_of_mind import (
    MentalStateModel,
    StrategicReasoning,
    StrategyPrediction,
    TheoryOfMindRegistry,
    get_theory_of_mind_registry,
    reset_theory_of_mind_registry,
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
    EnergyLedger,  # — re-exported via __all__
    get_energy_ledger,
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
    SERVER_CONTINENT,
    SPIRAL_MOUNTAIN,
    VILLAGE_OF_BEGINNINGS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
    Region,
    SubRegion,
    WorldState,
    get_world,
    reset_world,
)

__all__ = [
    "BASE_DRAIN_PER_TICK",
    # Phase 28: Narrative Coherence
    "COHERENCE_CHECK_INTERVAL",
    "CPM_CHANGE_THRESHOLD",
    "DAYS_PER_FESTIVAL",
    "DAYS_PER_SEASON",
    "DEFAULT_LANDMARKS",
    "DEFAULT_REGIONS",
    "DEFAULT_TICK_SECONDS",
    "DORMANCY_THRESHOLD",
    "ENDLESS_OCEAN",
    "ENERGY_MAX",
    "ENERGY_MIN",
    "FILE_ISLAND",
    "INFINITY_MOUNTAIN",
    "LLM_COST_DIVISOR",
    "MBTI_COMPATIBILITY",
    "PRIME_WORLD_ID",
    "PRIME_WORLD_ID",
    "RECOVER_EAT",
    "RECOVER_REST",
    "RECOVER_SOCIAL",
    # Phase 28: Self Model
    "SELF_ASSESSMENT_ADJUSTMENT_RATE",
    "SELF_MODEL_DIMS",
    "SERVER_CONTINENT",
    "SPIRAL_MOUNTAIN",
    "THINK_THRESHOLD",
    "VILLAGE_OF_BEGINNINGS",
    "WORLD_HEIGHT",
    "WORLD_WIDTH",
    "AffectPropagationEngine",
    "AffectVector",
    "CognitiveEnergyPool",
    "CoherenceEngine",
    "CoherenceReport",
    "ContextHealthMonitor",
    "ContextIssue",
    "ContextOptimizer",
    "ContextQualitySnapshot",
    "Convention",
    "ConventionDetector",
    "ConventionPool",
    "ConventionPropagation",
    "DarkGear",
    "DarkGearSystem",
    "DayNightSystem",
    "DayPeriod",
    "EcologySystem",
    "EconomySystem",
    "EnergyLedger",
    "EnvironmentalEventSystem",
    "Faction",
    "FactionRegistry",
    "Festival",
    "FestivalSystem",
    "Landmark",
    "LandmarkEffect",
    "LandmarkSystem",
    "MbtiDimension",
    # Phase 28: Theory of Mind
    "MentalStateModel",
    "MultiverseManager",
    "NarratorSystem",
    "PersonalityEvolutionEngine",
    "PersonalityProfile",
    "Region",
    "RelationConflict",
    "RelationConflictDetector",
    "RelationalCircle",
    "RelationalDistance",
    "RelationshipTracker",
    "Season",
    "SeasonSystem",
    "SelfAssessmentResult",
    "SelfEvaluator",
    "SelfModel",
    "SelfModelRegistry",
    "SnapshotManager",
    "SnapshotMeta",
    "SpatialInconsistency",
    "SpatialNarrativeBinder",
    "StoryDirector",
    "StoryEvent",
    "StrategicReasoning",
    "StrategyPrediction",
    "SubRegion",
    "TheoryOfMindRegistry",
    "TimelineSystem",
    "VitalitySnapshot",
    "Weather",
    "WeatherSystem",
    "WorldClock",
    "WorldScheduler",
    "WorldState",
    "compute_vitality",
    "get_coherence_engine",
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
    "get_health_monitor",
    "get_landmark_system",
    "get_multiverse",
    "get_narrator",
    "get_optimizer",
    "get_personality_engine",
    "get_registry",
    "get_season_system",
    "get_self_model_registry",
    "get_snapshot_manager",
    "get_theory_of_mind_registry",
    "get_timeline_system",
    "get_tracker",
    "get_weather_system",
    "get_world",
    "persistence",
    "reset_coherence_engine",
    "reset_context_quality",
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
    "reset_self_model_registry",
    "reset_snapshot_manager",
    "reset_theory_of_mind_registry",
    "reset_timeline_system",
    "reset_tracker",
    "reset_weather_system",
    "reset_world",
]

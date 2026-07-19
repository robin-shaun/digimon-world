"""智能体层: 数码兽 / NPC / 被选召的孩子。

参考 Stanford: reverie/backend_server/persona/persona.py
本模块的核心是 DigimonAgent,实现 Observe → Memory → Reflect → Plan → Act 循环。

详细设计: docs/DESIGN.md 第 3 节
"""
from .agent_insights import AgentInsightEngine, get_insight_engine, reset_insight_engine
from .badges import Badge, BadgeSystem
from .chosen_child import ChosenChildAgent, Crest
from .dialogue import Dialogue
from .digimon_agent import DigimonAgent
from .evolution import (
    EVOLUTION_CHAIN,
    EvolutionReason,
    EvolutionRequirement,
    EvolutionResult,
    EvolutionSystem,
    is_final_stage,
    next_stage,
)
from .healing import (
    HealingSystem,
    get_healing_system,
    reset_healing_system,
)
from .meme import (
    CATEGORY_SPREAD_RATE,
    Meme,
    MemeCategory,
    MemePool,
)
from .planner import Planner
from .reflector import Reflection, Reflector

__all__ = [
    "CATEGORY_SPREAD_RATE",
    "EVOLUTION_CHAIN",
    "AgentInsightEngine",
    "Badge",
    "BadgeSystem",
    "ChosenChildAgent",
    "Crest",
    "Dialogue",
    "DigimonAgent",
    "EvolutionReason",
    "EvolutionRequirement",
    "EvolutionResult",
    "EvolutionSystem",
    "HealingSystem",
    "Meme",
    "MemeCategory",
    "MemePool",
    "Planner",
    "Reflection",
    "Reflector",
    "get_healing_system",
    "get_insight_engine",
    "is_final_stage",
    "next_stage",
    "reset_healing_system",
    "reset_insight_engine",
]

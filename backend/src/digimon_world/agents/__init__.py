"""智能体层: 数码兽 / NPC / 被选召的孩子。

参考 Stanford: reverie/backend_server/persona/persona.py
本模块的核心是 DigimonAgent,实现 Observe → Memory → Reflect → Plan → Act 循环。

详细设计: docs/DESIGN.md 第 3 节
"""
from .digimon_agent import DigimonAgent
from .chosen_child import ChosenChildAgent, Crest
from .dialogue import Dialogue
from .evolution import (
    EVOLUTION_CHAIN,
    EvolutionReason,
    EvolutionRequirement,
    EvolutionResult,
    EvolutionSystem,
    is_final_stage,
    next_stage,
)
from .badges import Badge, BadgeSystem
from .healing import (
    HealingSystem,
    get_healing_system,
    reset_healing_system,
)
from .meme import (
    Meme,
    MemeCategory,
    MemePool,
    CATEGORY_SPREAD_RATE,
)
from .planner import Planner
from .reflector import Reflection, Reflector

__all__ = [
    "Badge",
    "BadgeSystem",
    "CATEGORY_SPREAD_RATE",
    "ChosenChildAgent",
    "Crest",
    "DigimonAgent",
    "Dialogue",
    "Meme",
    "MemeCategory",
    "MemePool",
    "Planner",
    "Reflection",
    "Reflector",
    "EvolutionSystem",
    "EvolutionResult",
    "EvolutionReason",
    "EvolutionRequirement",
    "EVOLUTION_CHAIN",
    "is_final_stage",
    "next_stage",
    "HealingSystem",
    "get_healing_system",
    "reset_healing_system",
]

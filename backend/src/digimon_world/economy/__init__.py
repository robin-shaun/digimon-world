from .energy_economy import EnergyEconomy, EnergyTransfer, ReciprocalAltruism
from .knowledge_economy import (
    InventedSkill,
    KnowledgeItem,
    KnowledgePool,
    KnowledgePropagation,
    TechNode,
    TechTree,
    get_knowledge_pool,
    reset_knowledge_pool,
)

__all__ = [
    "EnergyEconomy",
    "EnergyTransfer",
    "InventedSkill",
    "KnowledgeItem",
    "KnowledgePool",
    "KnowledgePropagation",
    "ReciprocalAltruism",
    "TechNode",
    "TechTree",
    "get_energy_economy",
    "get_knowledge_pool",
    "reset_energy_economy",
    "reset_knowledge_pool",
]

# ---- 进程级单例 ----
_economy_instance: EnergyEconomy | None = None


def get_energy_economy() -> EnergyEconomy:
    """获取(或延迟初始化)能量经济系统单例。

    首次调用时从全局 WorldState 构造 EnergyEconomy。
    """
    global _economy_instance
    if _economy_instance is None:
        from ..world.world_state import get_world
        _economy_instance = EnergyEconomy(get_world())
    return _economy_instance


def reset_energy_economy() -> None:
    """重置能量经济系统(测试用)。"""
    global _economy_instance
    _economy_instance = None

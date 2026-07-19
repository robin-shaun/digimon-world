from .energy_economy import EnergyEconomy, EnergyTransfer, ReciprocalAltruism

__all__ = [
    "EnergyEconomy",
    "EnergyTransfer",
    "ReciprocalAltruism",
    "get_energy_economy",
    "reset_energy_economy",
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

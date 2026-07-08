"""智能体层: 数码兽 / NPC / 被选召的孩子。

参考 Stanford: reverie/backend_server/persona/persona.py
本模块的核心是 DigimonAgent,实现 Observe → Memory → Reflect → Plan → Act 循环。

详细设计: docs/DESIGN.md 第 3 节
"""
from .digimon_agent import DigimonAgent
from .reflector import Reflection, Reflector

__all__ = ["DigimonAgent", "Reflection", "Reflector"]

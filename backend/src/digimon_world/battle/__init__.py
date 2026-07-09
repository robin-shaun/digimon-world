"""
战斗系统 (Battle System)
========================

回合制战斗骨架,参考 docs/DESIGN.md 第 5 节。

Phase 3 第一步(本 commit):
- 数值/类型定义 (types)
- 伤害计算 + 属性克制 (damage)
- 脚本式战斗引擎 (engine) —— 确定性,暂不接 LLM

Phase 3 后半:战斗 AI 换成 LLM 决策。
"""

from .damage import DamageCalculator, is_strong_against
from .engine import BattleEngine
from .sparring import SparParticipant, SparResult, spar
from .types import (
    ActionType,
    BattleAction,
    BattleResult,
    BattleState,
)

__all__ = [
    "ActionType",
    "BattleAction",
    "BattleState",
    "BattleResult",
    "DamageCalculator",
    "is_strong_against",
    "BattleEngine",
    "spar",
    "SparResult",
    "SparParticipant",
]

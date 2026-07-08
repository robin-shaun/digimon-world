"""
战斗系统的数据类型定义
======================

参考 docs/DESIGN.md 第 5.1 节:
- 行动选项: 攻击 / 防御 / 技能 / 逃跑 / 道具
- HP 归零 = 战斗失败(不真死,数字兽消散)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    """一回合可选的行动类型。"""

    ATTACK = "attack"    # 普通攻击
    DEFEND = "defend"    # 防御(减伤)
    SKILL = "skill"      # 使用技能(消耗 EP)
    FLEE = "flee"        # 逃跑
    ITEM = "item"        # 使用道具


@dataclass
class BattleAction:
    """一只数码兽在某回合做出的行动。"""

    actor_name: str                       # 行动者名字
    action_type: ActionType               # 行动类型
    skill_name: Optional[str] = None      # 若为技能,技能名;否则 None


@dataclass
class BattleState:
    """战斗进行中的状态快照(逐回合更新)。"""

    round: int                            # 当前回合数(从 1 开始)
    attacker: str                         # 本回合攻击方名字
    defender: str                         # 本回合防御方名字
    attacker_hp: int                      # 攻击方剩余 HP
    defender_hp: int                      # 防御方剩余 HP
    log: list[str] = field(default_factory=list)  # 战斗文字日志


@dataclass
class BattleResult:
    """战斗结束后的结果。"""

    winner_name: Optional[str]            # 胜者名字;平局 / 超时则为 None
    rounds: int                           # 总回合数
    final_hp: dict[str, int]              # 各方最终 HP: {name: hp}

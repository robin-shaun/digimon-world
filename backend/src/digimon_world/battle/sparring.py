"""
训练/切磋系统 (Sparring System)
================================

参考 docs/DESIGN.md 第 5 节的补充: 除了你死我活的正式战斗,数码兽之间还有
"友好切磋" —— 用于日常训练、增进感情,不计入胜负、不影响社交关系。

与正式战斗 (BattleEngine) 的区别:
- 不产生胜者,不给任何一方 battle_victories +1
- 不降低好感 / 不改动社交关系 (record_battle 不调用)
- 双方都受益: 心情 (happiness) +5, 经验 (experience) +2

设计要点:
- 切磋结果封装为 SparResult,与 API 层解耦,方便单测。
- 直接改动 agent.stats.happiness / experience,happiness 夹紧到 [0, 100],
  experience 不封顶。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..agents.digimon_agent import DigimonAgent

# 切磋一次双方各自获得的收益
SPAR_HAPPINESS_GAIN: int = 5
SPAR_EXPERIENCE_GAIN: int = 2

# happiness 上限 (与 needs 里的 0-100 心情区间一致)
HAPPINESS_MAX: int = 100
HAPPINESS_MIN: int = 0


@dataclass
class SparParticipant:
    """切磋后单只数码兽的收益快照。"""

    name: str
    happiness: int        # 切磋后的心情值
    experience: int       # 切磋后的经验值
    happiness_gain: int   # 本次心情增量
    experience_gain: int  # 本次经验增量


@dataclass
class SparResult:
    """一场友好切磋的结果 (无胜负)。"""

    attacker: SparParticipant
    defender: SparParticipant

    def to_dict(self) -> dict:
        """API 友好的字典。"""
        return {
            "friendly": True,
            "attacker": self.attacker.__dict__,
            "defender": self.defender.__dict__,
        }


def _apply_spar_gains(agent: DigimonAgent) -> SparParticipant:
    """给单只数码兽结算切磋收益: happiness +5 (夹紧), experience +2。"""
    new_happiness = min(
        HAPPINESS_MAX,
        max(HAPPINESS_MIN, agent.stats.happiness + SPAR_HAPPINESS_GAIN),
    )
    agent.stats.happiness = new_happiness
    agent.stats.experience += SPAR_EXPERIENCE_GAIN

    # 写一条记忆流,让切磋成为数码兽记得住的日常 (importance 较低)
    agent.observe(
        {
            "type": "sparring",
            "detail": "友好切磋,心情与经验都有提升",
        }
    )

    return SparParticipant(
        name=agent.name,
        happiness=agent.stats.happiness,
        experience=agent.stats.experience,
        happiness_gain=SPAR_HAPPINESS_GAIN,
        experience_gain=SPAR_EXPERIENCE_GAIN,
    )


def spar(attacker: DigimonAgent, defender: DigimonAgent) -> SparResult:
    """跑一场友好切磋。

    不产生胜者、不加 battle_victories、不改社交关系;双方各自
    心情 +5、经验 +2。

    Args:
        attacker: 发起方
        defender: 陪练方

    Returns:
        SparResult(双方收益快照)。
    """
    return SparResult(
        attacker=_apply_spar_gains(attacker),
        defender=_apply_spar_gains(defender),
    )

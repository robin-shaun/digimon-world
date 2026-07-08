"""
伤害计算 + 属性克制
==================

参考 docs/DESIGN.md 第 4.3 / 5.1 节。

公式(本 commit 硬编码,不走 LLM):
    base = attacker.attack - defender.defense // 2
    技能加成: +20%
    属性克制加成: 克制方 x1.5,自由种 x1.0
    最终伤害 = max(1, base * attr_mult)  (至少 1 点)
"""

from __future__ import annotations

from ..agents.digimon_agent import DigimonAgent, DigimonAttribute

# 技能相对普通攻击的加成倍率
SKILL_BONUS: float = 1.2
# 属性克制倍率
STRONG_MULTIPLIER: float = 1.5
NORMAL_MULTIPLIER: float = 1.0

# 属性克制关系: key 克制 value(参考 DESIGN.md 第 4.3 节)
#   疫苗种 (vaccine) 克制 病毒种 (virus)
#   数据种 (data)    克制 疫苗种 (vaccine)
#   病毒种 (virus)   克制 数据种 (data)
#   自由种 (free)    无克制
_STRONG_AGAINST: dict[DigimonAttribute, DigimonAttribute] = {
    DigimonAttribute.VACCINE: DigimonAttribute.VIRUS,
    DigimonAttribute.DATA: DigimonAttribute.VACCINE,
    DigimonAttribute.VIRUS: DigimonAttribute.DATA,
}


def is_strong_against(a: DigimonAttribute, d: DigimonAttribute) -> bool:
    """属性 a 是否克制属性 d。

    自由种(free)既不克制别人,也不被别人克制,恒返回 False。
    """
    return _STRONG_AGAINST.get(a) == d


class DamageCalculator:
    """伤害计算器(静态方法容器)。"""

    @staticmethod
    def calc_damage(
        attacker: DigimonAgent,
        defender: DigimonAgent,
        skill: str | None = None,
    ) -> int:
        """计算一次攻击对 defender 造成的伤害。

        Args:
            attacker: 攻击方
            defender: 防御方
            skill: 技能名;非 None 时施加 +20% 加成(本 commit 硬编码)

        Returns:
            伤害值,最少 1 点。
        """
        # 基础伤害: 攻击 - 防御的一半
        base = attacker.stats.attack - defender.stats.defense // 2

        # 技能加成
        if skill is not None:
            base = base * SKILL_BONUS

        # 属性克制加成
        if is_strong_against(attacker.attribute, defender.attribute):
            attr_mult = STRONG_MULTIPLIER
        else:
            attr_mult = NORMAL_MULTIPLIER

        damage = int(base * attr_mult)
        return max(1, damage)

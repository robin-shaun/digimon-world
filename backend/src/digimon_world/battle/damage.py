"""
伤害计算 + 属性克制 (Phase 8: 三角逆克制)
=============================================

参考 docs/DESIGN.md 第 4.3 / 5.1 节。

属性克制三角 (vaccine / data / virus):
    vaccine → virus:  1.5x
    virus   → data:   1.5x
    data    → vaccine: 1.5x
    逆克制: 0.75x
    同属性: 1.0x
    自由种(free): 对所有属性都是 1.0x,也不被任何属性克制

公式:
    base = attacker.attack - defender.defense // 2
    技能加成: +20%
    属性克制加成: 套用上述倍率
    最终伤害 = max(1, base * attr_mult)
"""

from __future__ import annotations

from ..agents.digimon_agent import DigimonAgent, DigimonAttribute

# 技能相对普通攻击的加成倍率
SKILL_BONUS: float = 1.2
# 属性克制倍率 (Phase 8: 三角克制)
STRONG_MULTIPLIER: float = 1.5   # 克制方
WEAK_MULTIPLIER: float = 0.75    # 被克制方
NORMAL_MULTIPLIER: float = 1.0   # 同属性 / free

# 属性克制关系: key 克制 value
_STRONG_AGAINST: dict[DigimonAttribute, DigimonAttribute] = {
    DigimonAttribute.VACCINE: DigimonAttribute.VIRUS,
    DigimonAttribute.DATA: DigimonAttribute.VACCINE,
    DigimonAttribute.VIRUS: DigimonAttribute.DATA,
}


def is_strong_against(a: DigimonAttribute, d: DigimonAttribute) -> bool:
    """属性 a 是否克制属性 d。自由种(free)恒返回 False。"""
    return _STRONG_AGAINST.get(a) == d


def get_attribute_multiplier(
    attacker_attr: DigimonAttribute, defender_attr: DigimonAttribute
) -> float:
    """获取属性克制倍率。

    Returns:
        1.5 (克制), 0.75 (被克), 1.0 (同属性 / 自由种)
    """
    # 自由种: 无克制关系
    if attacker_attr == DigimonAttribute.FREE or defender_attr == DigimonAttribute.FREE:
        return NORMAL_MULTIPLIER

    # 同属性
    if attacker_attr == defender_attr:
        return NORMAL_MULTIPLIER

    # 克制
    if is_strong_against(attacker_attr, defender_attr):
        return STRONG_MULTIPLIER

    # 被克制 (逆克制)
    return WEAK_MULTIPLIER


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
            skill: 技能名;非 None 时施加 +20% 加成

        Returns:
            伤害值,最少 1 点。
        """
        # 基础伤害: 攻击 - 防御的一半
        base = attacker.stats.attack - defender.stats.defense // 2

        # 技能加成
        if skill is not None:
            base = base * SKILL_BONUS

        # 属性克制加成 (Phase 8: 三角逆克制)
        attr_mult = get_attribute_multiplier(attacker.attribute, defender.attribute)

        damage = int(base * attr_mult)
        return max(1, damage)


__all__ = [
    "SKILL_BONUS",
    "STRONG_MULTIPLIER",
    "WEAK_MULTIPLIER",
    "NORMAL_MULTIPLIER",
    "DamageCalculator",
    "get_attribute_multiplier",
    "is_strong_against",
]

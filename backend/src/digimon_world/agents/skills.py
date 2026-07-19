"""
技能系统 (Skill System)
=======================

每只数码兽在每个进化阶段拥有一组预设技能 (参考数码宝贝动画的招式设定)。

技能三要素:
- power: 威力 (影响伤害/效果强度)
- cost: EP 消耗 (energy point, 见 DigimonStats.ep)
- type: 技能类型 (物理 / 火焰 / 冰冻 / 特殊 …)

用法::

    from digimon_world.agents.skills import skills_for

    skills = skills_for("Agumon", EvolutionStage.ROOKIE)
    # -> [Skill(name="小型火焰", ...), ...]

阶段越高技能越强,前一阶段的招式通常会被更强的版本取代。

参考 docs/DESIGN.md 第 5 节 "技能系统"。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .digimon_agent import EvolutionStage

# ----------------------------------------------------------------------------
# 技能类型
# ----------------------------------------------------------------------------

class SkillType(StrEnum):
    """技能类型 (与 DigimonAttribute 的克制关系解耦,独立分类)。"""

    PHYSICAL = "physical"    # 物理近战
    FIRE = "fire"            # 火焰
    ICE = "ice"              # 冰冻
    SPECIAL = "special"      # 特殊 / 能量


# ----------------------------------------------------------------------------
# Skill dataclass
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Skill:
    """一个技能。

    Attributes:
        name: 招式名 (中文,贴合动画)
        type: 技能类型 (SkillType)
        power: 威力,越高伤害越大
        cost: 释放消耗的 EP
    """

    name: str
    type: SkillType
    power: int
    cost: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.value,
            "power": self.power,
            "cost": self.cost,
        }


# ----------------------------------------------------------------------------
# 技能图鉴: species -> stage -> [Skill, ...]
# ----------------------------------------------------------------------------
#
# 亚古兽 (Agumon) 进化线招式:
#   ROOKIE     小型火焰 (Baby Flame)
#   CHAMPION   超级火焰 (Nova Blast)         — 暴龙兽
#   MEGA       盖亚能量炮 / 战斗龙卷风         — 战斗暴龙兽
#
# 加布兽 (Gabumon) 进化线招式:
#   ROOKIE     爆炎火焰弹 (Blue Blaster) / 妖狐火焰
#   CHAMPION   绝对冷冻气 (Sub-Zero Ice Punch) — 加鲁鲁兽
#   ULTIMATE   三叉戟臂 (Trident Arm) / 凯撒锐爪
#   MEGA       战斧斯坦纳 (Wolf Claw / Metal Wolf Claw) — 钢铁加鲁鲁兽
# ----------------------------------------------------------------------------

DIGIMON_SKILLS: dict[str, dict[EvolutionStage, list[Skill]]] = {
    "Agumon": {
        EvolutionStage.ROOKIE: [
            Skill(name="小型火焰", type=SkillType.FIRE, power=25, cost=8),
        ],
        EvolutionStage.CHAMPION: [
            Skill(name="超级火焰", type=SkillType.FIRE, power=55, cost=18),
        ],
        EvolutionStage.ULTIMATE: [
            Skill(name="三叉戟臂", type=SkillType.PHYSICAL, power=72, cost=28),
            Skill(name="究极破坏炮", type=SkillType.SPECIAL, power=85, cost=35),
        ],
        EvolutionStage.MEGA: [
            Skill(name="盖亚能量炮", type=SkillType.SPECIAL, power=95, cost=40),
            Skill(name="战斗龙卷风", type=SkillType.PHYSICAL, power=70, cost=25),
        ],
    },
    "Gabumon": {
        EvolutionStage.ROOKIE: [
            Skill(name="爆炎火焰弹", type=SkillType.FIRE, power=22, cost=8),
            Skill(name="妖狐火焰", type=SkillType.FIRE, power=28, cost=12),
        ],
        EvolutionStage.CHAMPION: [
            Skill(name="绝对冷冻气", type=SkillType.ICE, power=58, cost=20),
        ],
        EvolutionStage.ULTIMATE: [
            Skill(name="凯撒锐爪", type=SkillType.PHYSICAL, power=75, cost=30),
            Skill(name="圆月弯刀", type=SkillType.PHYSICAL, power=65, cost=25),
        ],
        EvolutionStage.MEGA: [
            Skill(name="战斧斯坦纳", type=SkillType.PHYSICAL, power=92, cost=38),
        ],
    },
}


# ----------------------------------------------------------------------------
# 查询辅助
# ----------------------------------------------------------------------------

def skills_for(species: str, stage: EvolutionStage) -> list[Skill]:
    """返回某 species 在某 stage 的技能列表。

    找不到 (未收录的 species 或该阶段无招式) 时返回空列表。
    """
    return list(DIGIMON_SKILLS.get(species, {}).get(stage, []))


def all_skills_for(species: str) -> list[Skill]:
    """返回某 species 全阶段所有技能 (按进化顺序展开)。"""
    stage_map = DIGIMON_SKILLS.get(species, {})
    order = [
        EvolutionStage.BABY_I,
        EvolutionStage.BABY_II,
        EvolutionStage.ROOKIE,
        EvolutionStage.CHAMPION,
        EvolutionStage.ULTIMATE,
        EvolutionStage.MEGA,
    ]
    result: list[Skill] = []
    for stage in order:
        result.extend(stage_map.get(stage, []))
    return result


def find_skill(species: str, name: str) -> Skill | None:
    """按招式名查找某 species 的技能,找不到返回 None。"""
    for skill in all_skills_for(species):
        if skill.name == name:
            return skill
    return None


__all__ = [
    "DIGIMON_SKILLS",
    "Skill",
    "SkillType",
    "all_skills_for",
    "find_skill",
    "skills_for",
]

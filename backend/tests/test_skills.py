"""
技能系统单元测试
================

覆盖:
- skills_for 按 species / stage 返回预设技能
- 亚古兽 / 加布兽 各阶段招式内容与数值
- find_skill 按名查找

运行: cd backend && source .venv/bin/activate && pytest tests/test_skills.py -v
"""

from __future__ import annotations

from digimon_world.agents.digimon_agent import EvolutionStage
from digimon_world.agents.skills import (
    Skill,
    SkillType,
    all_skills_for,
    find_skill,
    skills_for,
)


def test_skills_for_agumon_stages():
    """亚古兽各阶段招式: ROOKIE 小型火焰 / CHAMPION 超级火焰 / MEGA 盖亚能量炮+战斗龙卷风。"""
    rookie = skills_for("Agumon", EvolutionStage.ROOKIE)
    assert [s.name for s in rookie] == ["小型火焰"]
    assert rookie[0].type == SkillType.FIRE

    champion = skills_for("Agumon", EvolutionStage.CHAMPION)
    assert [s.name for s in champion] == ["超级火焰"]

    mega = skills_for("Agumon", EvolutionStage.MEGA)
    assert [s.name for s in mega] == ["盖亚能量炮", "战斗龙卷风"]
    # MEGA 招式威力应高于 CHAMPION
    assert all(s.power > champion[0].power for s in mega)


def test_skills_for_gabumon_stages():
    """加布兽各阶段招式: 爆炎火焰弹/妖狐火焰 → 绝对冷冻气 → 战斧斯坦纳。"""
    rookie = skills_for("Gabumon", EvolutionStage.ROOKIE)
    assert [s.name for s in rookie] == ["爆炎火焰弹", "妖狐火焰"]

    champion = skills_for("Gabumon", EvolutionStage.CHAMPION)
    assert [s.name for s in champion] == ["绝对冷冻气"]
    assert champion[0].type == SkillType.ICE

    mega = skills_for("Gabumon", EvolutionStage.MEGA)
    assert [s.name for s in mega] == ["战斧斯坦纳"]

    # 每个技能 cost 都是正数
    for skill in all_skills_for("Gabumon"):
        assert skill.cost > 0


def test_skills_for_unknown_and_find_skill():
    """未收录 species 返回空列表; find_skill 按名精确查找。"""
    assert skills_for("UnknownMon", EvolutionStage.ROOKIE) == []
    assert skills_for("Agumon", EvolutionStage.BABY_I) == []

    found = find_skill("Agumon", "盖亚能量炮")
    assert isinstance(found, Skill)
    assert found.power == 95
    assert found.type == SkillType.SPECIAL

    assert find_skill("Agumon", "不存在的招式") is None

"""
数码兽图鉴 (Pokédex) API
========================

一份**静态**的数码兽资料库,与运行中的世界 (WorldState) 解耦:
无论世界里当前存活哪几只、进化到哪一阶段,图鉴始终提供 8 只初始
数码兽的完整设定 (进化链 / 属性 / 招式 / 描述),供前端 evolution.html
渲染"进化图鉴"页。

数据组织::

    DigimonEntry            一条图鉴 (一条完整进化线)
      ├─ species            物种 id (小写,如 "agumon",与 world 种子一致)
      ├─ name               中文名 (成长期形态名)
      ├─ attribute          属性 (vaccine/data/virus/free) → 克制关系
      ├─ element            元素主题 (fire/ice/bird… 供前端着色)
      ├─ crest              纹章/象征 (勇气/友情…)
      ├─ description        一句话设定
      └─ evolution_chain    [EvolutionForm, …] 成长期→究极体 4 阶

属性克制 (与 battle/damage.py 一致):
    疫苗 vaccine → 病毒 virus → 数据 data → 疫苗 vaccine,自由 free 无克制。

接口:
- GET /api/pokedex            → 图鉴列表 (精简)
- GET /api/pokedex/{species}  → 单条图鉴完整详情 (含属性克制说明)

详细设计: docs/DESIGN.md 第 4 节 (进化) / 第 4.3 节 (属性克制)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

from ..agents.digimon_agent import DigimonAttribute
from ..battle.damage import _STRONG_AGAINST

router = APIRouter(prefix="/api/pokedex", tags=["pokedex"])


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvolutionForm:
    """进化链上的一个形态。"""

    stage: str          # 阶段 id: rookie / champion / ultimate / mega
    name: str           # 中文名
    en: str             # 英文名 (原作 roman 名)
    tier: str           # 阶段中文标签 (成长期 / 成熟期 / 完全体 / 究极体)
    emoji: str          # 展示用 emoji
    skills: list[str] = field(default_factory=list)  # 代表招式

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "name": self.name,
            "en": self.en,
            "tier": self.tier,
            "emoji": self.emoji,
            "skills": list(self.skills),
        }


@dataclass(frozen=True)
class DigimonEntry:
    """一条图鉴 = 一条完整进化线。"""

    species: str                 # 物种 id (小写)
    name: str                    # 中文名 (成长期形态)
    attribute: DigimonAttribute  # 属性
    element: str                 # 元素主题 (前端着色用)
    crest: str                   # 纹章 / 象征
    description: str             # 设定描述
    evolution_chain: list[EvolutionForm]

    def summary(self) -> dict[str, Any]:
        """列表用的精简视图。"""
        rookie = self.evolution_chain[0]
        mega = self.evolution_chain[-1]
        return {
            "species": self.species,
            "name": self.name,
            "attribute": self.attribute.value,
            "element": self.element,
            "crest": self.crest,
            "emoji": rookie.emoji,
            "mega_name": mega.name,
            "stages": len(self.evolution_chain),
        }

    def to_dict(self) -> dict[str, Any]:
        """详情用的完整视图 (含属性克制说明)。"""
        strong = _STRONG_AGAINST.get(self.attribute)
        weak_from = next(
            (a for a, d in _STRONG_AGAINST.items() if d == self.attribute),
            None,
        )
        return {
            "species": self.species,
            "name": self.name,
            "attribute": self.attribute.value,
            "element": self.element,
            "crest": self.crest,
            "description": self.description,
            "evolution_chain": [f.to_dict() for f in self.evolution_chain],
            "type_matchup": {
                "attribute": self.attribute.value,
                "strong_against": strong.value if strong else None,
                "weak_against": weak_from.value if weak_from else None,
                "note": _ATTRIBUTE_NOTES[self.attribute],
            },
        }


# 属性说明 (前端 tooltip / 文案用)
_ATTRIBUTE_NOTES: dict[DigimonAttribute, str] = {
    DigimonAttribute.VACCINE: "疫苗种,对病毒种造成 1.5 倍伤害,惧数据种。",
    DigimonAttribute.DATA: "数据种,对疫苗种造成 1.5 倍伤害,惧病毒种。",
    DigimonAttribute.VIRUS: "病毒种,对数据种造成 1.5 倍伤害,惧疫苗种。",
    DigimonAttribute.FREE: "自由种,不克制也不被克制,始终 1.0 倍伤害。",
}


# ---------------------------------------------------------------------------
# 内置图鉴数据: 8 只初始数码兽 (经典 Adventure 被选召孩子的搭档)
# ---------------------------------------------------------------------------

_POKEDEX: list[DigimonEntry] = [
    DigimonEntry(
        species="agumon",
        name="亚古兽",
        attribute=DigimonAttribute.VACCINE,
        element="fire",
        crest="勇气",
        description="小型恐龙型数码兽,勇敢好战,口吐火焰。勇气纹章的持有者,是许多冒险故事的主角。",
        evolution_chain=[
            EvolutionForm("rookie", "亚古兽", "Agumon", "成长期", "🦖", ["小型火焰"]),
            EvolutionForm("champion", "暴龙兽", "Greymon", "成熟期", "🐲", ["超级火焰"]),
            EvolutionForm("ultimate", "机械暴龙兽", "MetalGreymon", "完全体", "🤖", ["超究极火焰", "大地破坏炮"]),
            EvolutionForm("mega", "战斗暴龙兽", "WarGreymon", "究极体", "🐉", ["盖亚能量炮", "战斗龙卷风"]),
        ],
    ),
    DigimonEntry(
        species="gabumon",
        name="加布兽",
        attribute=DigimonAttribute.DATA,
        element="ice",
        crest="友情",
        description="披着加鲁鲁兽毛皮的爬虫型数码兽,性格害羞但内心忠诚。友情纹章的持有者。",
        evolution_chain=[
            EvolutionForm("rookie", "加布兽", "Gabumon", "成长期", "🦊", ["爆炎火焰弹", "妖狐火焰"]),
            EvolutionForm("champion", "加鲁鲁兽", "Garurumon", "成熟期", "🐺", ["绝对冷冻气"]),
            EvolutionForm("ultimate", "银河卡机狼", "WereGarurumon", "完全体", "🥋", ["狼爪拳", "疾风踢"]),
            EvolutionForm("mega", "钢铁加鲁鲁兽", "MetalGarurumon", "究极体", "❄️", ["战斧斯坦纳", "绝对零度爆"]),
        ],
    ),
    DigimonEntry(
        species="biyomon",
        name="比丘兽",
        attribute=DigimonAttribute.VACCINE,
        element="bird",
        crest="爱心",
        description="鸟型数码兽,温柔体贴,能操纵火焰之翼。爱心纹章的持有者。",
        evolution_chain=[
            EvolutionForm("rookie", "比丘兽", "Biyomon", "成长期", "🐦", ["魔法之火"]),
            EvolutionForm("champion", "鸟龙兽", "Birdramon", "成熟期", "🦅", ["火焰之翼"]),
            EvolutionForm("ultimate", "大鸟兽", "Garudamon", "完全体", "🦉", ["神鸟冲击波"]),
            EvolutionForm("mega", "凤凰兽", "Phoenixmon", "究极体", "🔥", ["星辰之火", "苍炎烈焰"]),
        ],
    ),
    DigimonEntry(
        species="tentomon",
        name="甲虫兽",
        attribute=DigimonAttribute.VACCINE,
        element="thunder",
        crest="知识",
        description="昆虫型数码兽,聪明好学,身体能积蓄电荷放出电击。知识纹章的持有者。",
        evolution_chain=[
            EvolutionForm("rookie", "甲虫兽", "Tentomon", "成长期", "🐞", ["电击"]),
            EvolutionForm("champion", "昆虫兽", "Kabuterimon", "成熟期", "🪲", ["高频电磁波"]),
            EvolutionForm("ultimate", "兜虫兽", "MegaKabuterimon", "完全体", "🦗", ["角冲击"]),
            EvolutionForm("mega", "大力金刚兽", "HerculesKabuterimon", "究极体", "⚡", ["巨型电磁炮", "兆亿伏电击"]),
        ],
    ),
    DigimonEntry(
        species="palmon",
        name="花仙兽",
        attribute=DigimonAttribute.DATA,
        element="grass",
        crest="纯真",
        description="植物型数码兽,头顶花朵,能释放毒藤与花粉。纯真纹章的持有者。",
        evolution_chain=[
            EvolutionForm("rookie", "花仙兽", "Palmon", "成长期", "🌱", ["有毒常春藤"]),
            EvolutionForm("champion", "仙人掌兽", "Togemon", "成熟期", "🌵", ["千针万毒手"]),
            EvolutionForm("ultimate", "花仙女兽", "Lillymon", "完全体", "🌸", ["花之炮"]),
            EvolutionForm("mega", "玫瑰兽", "Rosemon", "究极体", "🌹", ["荆棘鞭笞", "玫瑰喷射"]),
        ],
    ),
    DigimonEntry(
        species="gomamon",
        name="哥玛兽",
        attribute=DigimonAttribute.VACCINE,
        element="water",
        crest="诚实",
        description="海兽型数码兽,乐观爱玩,能召唤鱼群助战。诚实纹章的持有者。",
        evolution_chain=[
            EvolutionForm("rookie", "哥玛兽", "Gomamon", "成长期", "🦭", ["鱼群攻击"]),
            EvolutionForm("champion", "独角鲸兽", "Ikkakumon", "成熟期", "🦣", ["鱼雷飞弹"]),
            EvolutionForm("ultimate", "祖顿兽", "Zudomon", "完全体", "🔨", ["雷神之锤"]),
            EvolutionForm("mega", "神海兽", "Vikemon", "究极体", "🌊", ["北极风暴", "巨力铁拳"]),
        ],
    ),
    DigimonEntry(
        species="patamon",
        name="巴达兽",
        attribute=DigimonAttribute.DATA,
        element="holy",
        crest="希望",
        description="哺乳型数码兽,大耳能飞,天真烂漫。希望纹章的持有者,进化为神圣的天使系数码兽。",
        evolution_chain=[
            EvolutionForm("rookie", "巴达兽", "Patamon", "成长期", "🐹", ["空气炮"]),
            EvolutionForm("champion", "天使兽", "Angemon", "成熟期", "😇", ["天堂之拳"]),
            EvolutionForm("ultimate", "神圣天使兽", "MagnaAngemon", "完全体", "🕊️", ["圣光斩"]),
            EvolutionForm("mega", "炽天使兽", "Seraphimon", "究极体", "👼", ["七道光芒", "神圣之球"]),
        ],
    ),
    DigimonEntry(
        species="tailmon",
        name="妖精兽",
        attribute=DigimonAttribute.VACCINE,
        element="light",
        crest="光明",
        description="兽型数码兽,身手敏捷,尾环蕴含神圣之力。光明纹章的持有者,进化为圣洁的女神系数码兽。",
        evolution_chain=[
            EvolutionForm("rookie", "妖精兽", "Tailmon", "成长期", "🐱", ["猫爪拳"]),
            EvolutionForm("champion", "天女兽", "Angewomon", "成熟期", "👸", ["神圣之箭", "天堂之光"]),
            EvolutionForm("ultimate", "神圣天女兽", "Ofanimon", "完全体", "💫", ["圣洁救赎"]),
            EvolutionForm("mega", "圣龙兽", "Holydramon", "究极体", "🐉", ["神圣火焰"]),
        ],
    ),
]

# species → entry 的索引 (查详情用)
_INDEX: dict[str, DigimonEntry] = {e.species: e for e in _POKEDEX}


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@router.get("")
def list_pokedex() -> dict[str, Any]:
    """图鉴列表 (精简: 物种 / 名字 / 属性 / 元素 / 纹章 / 究极体名)。"""
    return {
        "count": len(_POKEDEX),
        "entries": [e.summary() for e in _POKEDEX],
    }


@router.get("/{species}")
def get_pokedex_entry(species: str) -> dict[str, Any]:
    """单条图鉴完整详情 (进化链 + 招式 + 描述 + 属性克制)。"""
    entry = _INDEX.get(species.lower())
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"Pokédex entry '{species}' not found"
        )
    return entry.to_dict()


__all__ = ["router", "DigimonEntry", "EvolutionForm"]

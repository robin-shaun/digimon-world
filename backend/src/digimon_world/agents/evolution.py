"""
进化系统 (Evolution System)
===========================

数码兽 6 阶段进化链 (参考数码宝贝动画世界观):

    BABY_I  →  BABY_II  →  ROOKIE  →  CHAMPION  →  ULTIMATE  →  MEGA

Phase 8: 物种特定进化树 + 8 枚徽章 + 经典动画路线

徽章系统 (8 Crests):
- courage (勇气): Agumon 线
- friendship (友情): Gabumon 线
- love (爱心): Biyomon / Palmon 线
- knowledge (知识): Tentomon 线
- sincerity (诚实): Gomamon 线
- purity (纯真): Palmon 线
- hope (希望): Patamon 线
- light (光明): Tailmon 线

进化条件:
- 成熟期 (ROOKIE → CHAMPION): 无徽章要求,仅 battle + bond
- 完全体 (CHAMPION → ULTIMATE): 需要对应徽章
- 究极体 (ULTIMATE → MEGA): 需要徽章 + 特殊事件触发
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .digimon_agent import DigimonAgent, DigimonStats, EvolutionStage


# ============================================================================
# 徽章系统 (Crests)
# ============================================================================

class Crest(str, Enum):
    """8 枚被选召孩子的徽章。"""
    COURAGE = "courage"         # 勇气 - 亚古兽
    FRIENDSHIP = "friendship"   # 友情 - 加布兽
    LOVE = "love"               # 爱心 - 比丘兽/巴鲁兽
    KNOWLEDGE = "knowledge"     # 知识 - 甲虫兽
    SINCERITY = "sincerity"     # 诚实 - 哥玛兽
    PURITY = "purity"           # 纯真 - 巴鲁兽
    HOPE = "hope"               # 希望 - 巴达兽
    LIGHT = "light"             # 光明 - 迪路兽


# ============================================================================
# 物种特定进化链
# ============================================================================

@dataclass
class SpeciesEvolution:
    """某个物种在当前阶段的进化信息。"""
    next_species: str       # 进化后物种名
    crest: Optional[Crest] = None  # 进化所需徽章


# 物种 → 每阶段进化信息 (按物种的 species_id)
# 成熟期 (ROOKIE → CHAMPION): 不需要徽章
# 完全体 (CHAMPION → ULTIMATE): 需要对应徽章
# 究极体 (ULTIMATE → MEGA): 需要徽章 + 特殊事件

SPECIES_EVOLUTION_TREE: dict[str, dict[EvolutionStage, SpeciesEvolution]] = {
    # ── 亚古兽线: 勇气徽章 ──
    "agumon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="greymon",       # 暴龙兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="metal_greymon",  # 机械暴龙兽
            crest=Crest.COURAGE,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="war_greymon",    # 战斗暴龙兽
            crest=Crest.COURAGE,
        ),
    },
    # ── 加布兽线: 友情徽章 ──
    "gabumon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="garurumon",      # 加鲁鲁兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="were_garurumon", # 兽人加鲁鲁
            crest=Crest.FRIENDSHIP,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="metal_garurumon", # 钢铁加鲁鲁
            crest=Crest.FRIENDSHIP,
        ),
    },
    # ── 比丘兽线: 爱心徽章 ──
    "biyomon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="birdramon",      # 巴多拉兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="garudamon",      # 伽楼达兽
            crest=Crest.LOVE,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="hououmon",       # 凤凰兽
            crest=Crest.LOVE,
        ),
    },
    # ── 甲虫兽线: 知识徽章 ──
    "tentomon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="kabuterimon",    # 比多兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="atlur_kabuterimon",  # 超比多兽
            crest=Crest.KNOWLEDGE,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="hercules_kabuterimon",  # 巨大古加兽
            crest=Crest.KNOWLEDGE,
        ),
    },
    # ── 巴鲁兽线: 纯真/爱心徽章 ──
    "palmon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="togemon",        # 仙人掌兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="lilimon",        # 花仙兽
            crest=Crest.PURITY,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="rosemon",        # 蔷薇兽
            crest=Crest.PURITY,
        ),
    },
    # ── 哥玛兽线: 诚实徽章 ──
    "gomamon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="ikkakumon",      # 海狮兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="zudomon",        # 祖顿兽
            crest=Crest.SINCERITY,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="vikemon",        # 维京兽
            crest=Crest.SINCERITY,
        ),
    },
    # ── 巴达兽线: 希望徽章 ──
    "patamon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="angemon",        # 天使兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="holy_angemon",   # 神圣天使兽
            crest=Crest.HOPE,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="seraphimon",     # 究极天使兽
            crest=Crest.HOPE,
        ),
    },
    # ── 迪路兽线: 光明徽章 ──
    "tailmon": {
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="angewomon",      # 天女兽
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="holydramon",     # 圣龙兽 (神圣天女兽)
            crest=Crest.LIGHT,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="ophanimon",      # 座天使兽
            crest=Crest.LIGHT,
        ),
    },
    # ── 小狗兽: 幼年期→迪路兽 (特殊: 小狗兽进化成迪路兽) ──
    "plotmon": {
        EvolutionStage.BABY_II: SpeciesEvolution(
            next_species="tailmon",         # 迪路兽 (小狗兽 → 迪路兽)
        ),
        # 进化成迪路兽后,后续沿用 tailmon 线
        EvolutionStage.ROOKIE: SpeciesEvolution(
            next_species="angewomon",
        ),
        EvolutionStage.CHAMPION: SpeciesEvolution(
            next_species="holydramon",
            crest=Crest.LIGHT,
        ),
        EvolutionStage.ULTIMATE: SpeciesEvolution(
            next_species="ophanimon",
            crest=Crest.LIGHT,
        ),
    },
}


def get_species_evolution(species: str, stage: EvolutionStage) -> Optional[SpeciesEvolution]:
    """获取某物种在某阶段的进化信息 (大小写不敏感)。"""
    tree = SPECIES_EVOLUTION_TREE.get(species.lower(), {})
    return tree.get(stage)


# ============================================================================
# 进化阈值表
# ============================================================================

@dataclass(frozen=True)
class EvolutionRequirement:
    """某一阶段升到下一阶段的前置条件。"""

    min_victories: int       # 战斗胜利次数门槛
    min_bond: int            # 羁绊值门槛
    next_species: str        # 退化后备的 species
    crest: Optional[Crest] = None        # 所需徽章 (完全体+究极体)
    require_story_event: bool = False    # 是否需要特殊剧情事件


EVOLUTION_CHAIN: dict[EvolutionStage, EvolutionRequirement] = {
    EvolutionStage.BABY_I: EvolutionRequirement(
        min_victories=1,
        min_bond=5,
        next_species="baby_ii_form",
    ),
    EvolutionStage.BABY_II: EvolutionRequirement(
        min_victories=3,
        min_bond=15,
        next_species="rookie_form",
    ),
    EvolutionStage.ROOKIE: EvolutionRequirement(
        min_victories=8,
        min_bond=40,
        next_species="champion_form",  # 物种特定路由覆盖此值
    ),
    EvolutionStage.CHAMPION: EvolutionRequirement(
        min_victories=15,
        min_bond=60,
        next_species="ultimate_form",  # 需要徽章
        crest=None,  # 实际由物种路由决定
    ),
    EvolutionStage.ULTIMATE: EvolutionRequirement(
        min_victories=25,
        min_bond=100,
        next_species="mega_form",      # 需要徽章+特殊事件
        crest=None,
        require_story_event=True,
    ),
}


def is_final_stage(stage: EvolutionStage) -> bool:
    """判断是否已达最高阶段。"""
    return stage == EvolutionStage.MEGA


def next_stage(stage: EvolutionStage) -> Optional[EvolutionStage]:
    """返回下一阶段,若已是 MEGA 则返回 None。"""
    order = [
        EvolutionStage.BABY_I,
        EvolutionStage.BABY_II,
        EvolutionStage.ROOKIE,
        EvolutionStage.CHAMPION,
        EvolutionStage.ULTIMATE,
        EvolutionStage.MEGA,
    ]
    try:
        idx = order.index(stage)
    except ValueError:
        return None
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


# ============================================================================
# 进化结果 / 触发原因
# ============================================================================

class EvolutionReason(str, Enum):
    """进化触发原因。"""

    BATTLE_VICTORIES = "battle_victories"
    BOND = "bond"
    STORY_EVENT = "story_event"
    NOT_READY = "not_ready"
    ALREADY_MEGA = "already_mega"
    MISSING_CREST = "missing_crest"        # 缺少对应徽章
    WAITING_EVENT = "waiting_event"         # 等待特殊事件触发


@dataclass
class EvolutionResult:
    """一次进化操作的结果。"""

    evolved: bool
    old_stage: EvolutionStage
    new_stage: EvolutionStage
    reason: EvolutionReason
    next_species: Optional[str] = None
    crest_required: Optional[Crest] = None

    def to_dict(self) -> dict:
        return {
            "evolved": self.evolved,
            "old_stage": self.old_stage.value,
            "new_stage": self.new_stage.value,
            "reason": self.reason.value,
            "next_species": self.next_species,
            "crest_required": self.crest_required.value if self.crest_required else None,
        }


# ============================================================================
# 进化系统主体
# ============================================================================

class EvolutionSystem:
    """数码兽进化系统 (Phase 8: 物种特定路由 + 徽章 + 事件)。"""

    def __init__(self):
        # 全局已解锁的徽章 (被选召的孩子获得的徽章)
        self.unlocked_crests: set[Crest] = set()
        # 是否已触发特殊故事事件 (如天使兽射箭等)
        self.story_events_triggered: set[str] = set()

    def unlock_crest(self, crest: Crest) -> None:
        """解锁一枚徽章。"""
        self.unlocked_crests.add(crest)

    def trigger_story_event(self, event_id: str) -> None:
        """标记一个故事事件已触发。"""
        self.story_events_triggered.add(event_id)

    def compute_bond(self, agent: DigimonAgent) -> int:
        """从记忆流累计羁绊值。"""
        return sum(m.importance for m in agent.memory.entries)

    def _get_next_species(
        self, agent: DigimonAgent, stage: EvolutionStage
    ) -> tuple[str, Optional[Crest], bool]:
        """获取物种特定的下一形态和所需徽章。

        Returns:
            (next_species, required_crest, story_event_required)
        """
        sp_evo = get_species_evolution(agent.species, stage)
        if sp_evo is not None:
            return sp_evo.next_species, sp_evo.crest, False

        # 回退到通用链
        req = EVOLUTION_CHAIN.get(stage)
        if req is not None:
            return req.next_species, req.crest, req.require_story_event
        return "unknown_form", None, False

    def can_evolve(
        self,
        agent: DigimonAgent,
        battle_victories: int,
        bond: Optional[int] = None,
    ) -> tuple[bool, EvolutionReason, Optional[Crest]]:
        """判断当前能否进化,返回 (can, reason, missing_crest)。"""
        if is_final_stage(agent.stage):
            return False, EvolutionReason.ALREADY_MEGA, None

        req = EVOLUTION_CHAIN.get(agent.stage)
        if req is None:
            return False, EvolutionReason.NOT_READY, None

        actual_bond = bond if bond is not None else self.compute_bond(agent)

        # 检查数值条件
        stats_ok = (
            battle_victories >= req.min_victories and actual_bond >= req.min_bond
        )
        bond_overflow = actual_bond >= req.min_bond * 2

        if not stats_ok and not bond_overflow:
            return False, EvolutionReason.NOT_READY, None

        # 检查徽章要求 (CHAMPION → ULTIMATE, ULTIMATE → MEGA)
        _, required_crest, story_required = self._get_next_species(
            agent, agent.stage
        )

        # ULTIMATE → MEGA: 需要特殊事件
        if story_required and agent.stage == EvolutionStage.ULTIMATE:
            if not self.story_events_triggered:
                return False, EvolutionReason.WAITING_EVENT, required_crest

        # CHAMPION → ULTIMATE 或 ULTIMATE → MEGA: 需要徽章
        if required_crest is not None and required_crest not in self.unlocked_crests:
            return False, EvolutionReason.MISSING_CREST, required_crest

        if stats_ok:
            return True, EvolutionReason.BATTLE_VICTORIES, None
        if bond_overflow:
            return True, EvolutionReason.BOND, None
        return False, EvolutionReason.NOT_READY, None

    def evolve(self, agent: DigimonAgent, reason: EvolutionReason) -> EvolutionResult:
        """实际执行进化: 改 stage / 改 species / 重置 stats / 写记忆。"""
        old_stage = agent.stage
        target = next_stage(old_stage)
        if target is None:
            return EvolutionResult(
                evolved=False,
                old_stage=old_stage,
                new_stage=old_stage,
                reason=EvolutionReason.ALREADY_MEGA,
            )

        next_species, crest, _ = self._get_next_species(agent, old_stage)

        # ---- 升级数值 (每升一级 * 1.5 系数) ----
        scale = 1.5
        old_stats = agent.stats
        new_stats = DigimonStats(
            hp=int(old_stats.hp * scale),
            max_hp=int(old_stats.max_hp * scale),
            ep=int(old_stats.ep * scale),
            max_ep=int(old_stats.max_ep * scale),
            attack=int(old_stats.attack * scale),
            defense=int(old_stats.defense * scale),
            speed=int(old_stats.speed * scale),
        )

        # ---- 修改 agent ----
        agent.stage = target
        agent.species = next_species
        agent.stats = new_stats

        # ---- 写进化记忆 ----
        desc = (
            f"I evolved from {old_stage.value} to {target.value} "
            f"(new form: {next_species}, reason: {reason.value})"
        )
        agent.memory.add(
            event={"description": desc, "type": "evolution"},
            importance=9,
            memory_type="observation",
        )

        return EvolutionResult(
            evolved=True,
            old_stage=old_stage,
            new_stage=target,
            reason=reason,
            next_species=next_species,
        )

    def check_and_evolve(
        self,
        agent: DigimonAgent,
        battle_victories: int,
        bond: Optional[int] = None,
    ) -> EvolutionResult:
        """一站式: 判定 + 执行。"""
        can, reason, crest = self.can_evolve(
            agent, battle_victories=battle_victories, bond=bond
        )
        if not can:
            return EvolutionResult(
                evolved=False,
                old_stage=agent.stage,
                new_stage=agent.stage,
                reason=reason,
                crest_required=crest,
            )
        return self.evolve(agent, reason=reason)


__all__ = [
    "Crest",
    "EvolutionSystem",
    "EvolutionResult",
    "EvolutionReason",
    "EvolutionRequirement",
    "EVOLUTION_CHAIN",
    "SPECIES_EVOLUTION_TREE",
    "SpeciesEvolution",
    "get_species_evolution",
    "is_final_stage",
    "next_stage",
]

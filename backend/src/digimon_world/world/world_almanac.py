"""
WorldAlmanac - 数码世界年鉴引擎
================================

Phase 29 核心模块。每隔 epoch（默认 100 tick）或重大事件触发时，自动生成一个
不可变的「年鉴章节」——世界状态快照 + 事件精选 + 趋势分析 + 数码兽名人堂。

纯数据聚合，无 LLM 依赖 — 快速、低成本、高度可测试。

设计要点:
- AlmanacChapter: 章节数据类，包含世界快照、事件、趋势、名人堂
- WorldAlmanac: 章节生成/索引/过滤/导出，append-only
- 趋势靠相邻章节 diff 计算，不引入外部依赖
- 名人堂按多维度（战斗/知识/社交/利他）分别排名
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Any

# ---- 阈值 ----
DEFAULT_EPOCH_TICKS: int = 100        # 默认每 100 tick 生成一个章节
MIN_EVENTS_FOR_CHAPTER: int = 3       # 少于 3 个事件则推迟到下一 epoch
HALL_OF_FAME_SIZE: int = 5            # 名人堂每个维度取前 5
SIGNIFICANT_EVENT_TYPES: set[str] = {
    "dialogue", "battle", "evolution", "dark_gear", "disaster",
    "environmental_event", "faction_create", "personality_shift",
    "knowledge_invented", "energy_crisis", "alliance_formed",
}


# ---- 数据类 ----

@dataclass
class WorldSnapshot:
    """世界快照: 一个时间点的全局状态摘要."""

    tick: int
    world_time: str
    total_digimon: int
    active_digimon: int
    dormant_digimon: int
    avg_energy: float
    total_knowledge_items: int
    total_conventions: int
    faction_count: int
    avg_coherence_score: float
    personality_distribution: dict[str, int] = field(default_factory=dict)   # mbti → count
    region_populations: dict[str, int] = field(default_factory=dict)         # region_id → count
    evolution_distribution: dict[str, int] = field(default_factory=dict)     # stage → count


@dataclass
class CuratedEvent:
    """精选事件: 从事件流中按 significance 筛选出的高价值事件."""

    event_type: str
    title: str
    description: str
    tick: int
    world_time: str
    significance: float
    participants: list[str] = field(default_factory=list)
    location: str = ""


@dataclass
class TrendReport:
    """趋势报告: 当前章节与上一章节的对比分析."""

    personality_shifts: list[dict[str, Any]] = field(default_factory=list)
    knowledge_growth: dict[str, Any] = field(default_factory=dict)
    energy_trend: dict[str, Any] = field(default_factory=dict)
    faction_changes: dict[str, Any] = field(default_factory=dict)
    population_change: dict[str, Any] = field(default_factory=dict)
    coherence_trend: dict[str, Any] = field(default_factory=dict)


@dataclass
class HallOfFameEntry:
    """名人堂条目: 某维度排名."""

    name: str
    value: float
    detail: str = ""


@dataclass
class HallOfFame:
    """名人堂: 多维度排行榜."""

    top_fighters: list[HallOfFameEntry] = field(default_factory=list)
    top_inventors: list[HallOfFameEntry] = field(default_factory=list)
    top_socializers: list[HallOfFameEntry] = field(default_factory=list)
    top_altruists: list[HallOfFameEntry] = field(default_factory=list)
    most_evolved: list[HallOfFameEntry] = field(default_factory=list)


@dataclass
class AlmanacChapter:
    """年鉴章节: 一个 epoch 的完整历史记录."""

    epoch: int
    tick_start: int
    tick_end: int
    world_time_start: str
    world_time_end: str
    snapshot: WorldSnapshot
    top_events: list[CuratedEvent] = field(default_factory=list)
    trends: TrendReport | None = None
    hall_of_fame: HallOfFame | None = None
    generated_at: str = ""
    event_count: int = 0
    narrative_summary: str = ""


# ---- 核心引擎 ----

class WorldAlmanac:
    """数码世界年鉴引擎.

    用法:
        almanac = WorldAlmanac()
        chapter = almanac.generate_chapter(tick, world_time, snapshot_data, events, digimon_data)
        almanac.archive(chapter)
        recent = almanac.latest_chapter
        print(almanac.list_chapters())
    """

    def __init__(self) -> None:
        self._chapters: dict[int, AlmanacChapter] = {}
        self._epoch_tick_counter: int = 0
        self._last_archived_tick: int = -1

    # -- 生成 --

    def generate_chapter(
        self,
        tick: int,
        world_time: str,
        snapshot_data: dict[str, Any],
        events: list[dict[str, Any]],
        digimon_data: list[dict[str, Any]],
        *,
        tick_start: int | None = None,
        world_time_start: str | None = None,
    ) -> AlmanacChapter:
        """生成一个年鉴章节.

        Args:
            tick: 当前 tick
            world_time: 当前世界时间字符串
            snapshot_data: 世界状态快照数据
            events: 事件列表 (至少需要 type, significance, tick, world_time)
            digimon_data: 数码兽数据列表
            tick_start: epoch 开始的 tick (默认取上一章节的 tick_end+1 或 0)
            world_time_start: epoch 开始的世界时间
        """
        epoch = len(self._chapters) + 1
        if tick_start is None:
            prev = self._chapters.get(epoch - 1)
            tick_start = (prev.tick_end + 1) if prev else 0
        if world_time_start is None:
            prev = self._chapters.get(epoch - 1)
            world_time_start = prev.world_time_end if prev else "Day 1, 00:00"

        snapshot = self._build_snapshot(tick, world_time, snapshot_data, digimon_data)
        curated = self._curate_events(events, tick_start, tick)
        trends = self._compute_trends(snapshot, epoch - 1)
        hall = self._build_hall_of_fame(digimon_data)
        summary = self._generate_summary(snapshot, curated, trends, hall)

        return AlmanacChapter(
            epoch=epoch,
            tick_start=tick_start,
            tick_end=tick,
            world_time_start=world_time_start,
            world_time_end=world_time,
            snapshot=snapshot,
            top_events=curated,
            trends=trends,
            hall_of_fame=hall,
            generated_at=world_time,
            event_count=len(curated),
            narrative_summary=summary,
        )

    def archive(self, chapter: AlmanacChapter) -> None:
        """归档章节. 成功后不可修改."""
        self._chapters[chapter.epoch] = copy.deepcopy(chapter)
        self._last_archived_tick = chapter.tick_end

    def should_generate(self, tick: int, event_count: int) -> bool:
        """判断是否应该生成本 epoch 章节."""
        ticks_since_last = tick - self._last_archived_tick
        return ticks_since_last >= DEFAULT_EPOCH_TICKS and event_count >= MIN_EVENTS_FOR_CHAPTER

    # -- 查询 --

    @property
    def latest_chapter(self) -> AlmanacChapter | None:
        if not self._chapters:
            return None
        return self._chapters[max(self._chapters)]

    def get_chapter(self, epoch: int) -> AlmanacChapter | None:
        return self._chapters.get(epoch)

    def list_chapters(self) -> list[AlmanacChapter]:
        return sorted(self._chapters.values(), key=lambda c: c.epoch)

    def get_current_snapshot(
        self,
        tick: int,
        world_time: str,
        snapshot_data: dict[str, Any],
        digimon_data: list[dict[str, Any]],
    ) -> WorldSnapshot:
        """获取当前时刻的世界快照 (不归档)."""
        return self._build_snapshot(tick, world_time, snapshot_data, digimon_data)

    def export(self) -> dict[str, Any]:
        """导出完整年鉴为 JSON 可序列化字典."""
        return {
            "total_chapters": len(self._chapters),
            "last_archived_tick": self._last_archived_tick,
            "chapters": [self._chapter_to_dict(c) for c in self.list_chapters()],
        }

    # -- 内部方法 --

    def _build_snapshot(
        self,
        tick: int,
        world_time: str,
        snapshot_data: dict[str, Any],
        digimon_data: list[dict[str, Any]],
    ) -> WorldSnapshot:
        """从原始数据构建 WorldSnapshot."""
        total = len(digimon_data)
        active = sum(1 for d in digimon_data if d.get("energy", {}).get("current", 100) > 0)
        dormant = total - active
        avg_energy = (
            sum(d.get("energy", {}).get("current", 0) for d in digimon_data) / total
            if total > 0
            else 0.0
        )

        # 人格分布
        personality_dist: dict[str, int] = {}
        for d in digimon_data:
            mbti = d.get("personality", {}).get("mbti", "UNKN")
            personality_dist[mbti] = personality_dist.get(mbti, 0) + 1

        # 区域分布
        region_populations: dict[str, int] = {}
        for d in digimon_data:
            rid = str(d.get("region_id", "unknown"))
            region_populations[rid] = region_populations.get(rid, 0) + 1

        # 进化分布
        evolution_dist: dict[str, int] = {}
        for d in digimon_data:
            stage = d.get("evolution", {}).get("stage", "unknown")
            evolution_dist[stage] = evolution_dist.get(stage, 0) + 1

        return WorldSnapshot(
            tick=tick,
            world_time=world_time,
            total_digimon=total,
            active_digimon=active,
            dormant_digimon=dormant,
            avg_energy=round(avg_energy, 1),
            total_knowledge_items=snapshot_data.get("total_knowledge_items", 0),
            total_conventions=snapshot_data.get("total_conventions", 0),
            faction_count=snapshot_data.get("faction_count", 0),
            avg_coherence_score=round(snapshot_data.get("avg_coherence_score", 0.0), 2),
            personality_distribution=personality_dist,
            region_populations=region_populations,
            evolution_distribution=evolution_dist,
        )

    def _curate_events(
        self,
        events: list[dict[str, Any]],
        tick_start: int,
        tick_end: int,
    ) -> list[CuratedEvent]:
        """从事件列表中筛选出当前 epoch 内的高价值事件."""
        curated: list[CuratedEvent] = []
        for evt in events:
            t = evt.get("tick", -1)
            if t < tick_start or t > tick_end:
                continue
            etype = evt.get("type", "unknown")
            if etype not in SIGNIFICANT_EVENT_TYPES and etype != "unknown":
                # 保留非 significant 类型的事件（不过滤过度）
                pass

            sig = evt.get("significance", 0)
            if isinstance(sig, (int, float)):
                sig = float(sig)

            curated.append(
                CuratedEvent(
                    event_type=etype,
                    title=self._event_title(evt),
                    description=evt.get("description", evt.get("line", "")),
                    tick=t,
                    world_time=evt.get("world_time", evt.get("timestamp", "")),
                    significance=sig,
                    participants=self._extract_participants(evt),
                    location=evt.get("location", evt.get("region_id", "")),
                )
            )

        # 按 significance 降序，同 significance 按 tick
        curated.sort(key=lambda e: (-e.significance, e.tick))
        return curated[:20]  # 最多保留 20 个精选事件

    def _compute_trends(
        self,
        current: WorldSnapshot,
        prev_epoch: int,
    ) -> TrendReport:
        """对比当前快照与上一 epoch 快照，生成趋势报告."""
        prev_chapter = self._chapters.get(prev_epoch)
        if prev_chapter is None:
            return TrendReport()

        prev = prev_chapter.snapshot
        report = TrendReport()

        # 人格漂移
        all_mbti = set(current.personality_distribution) | set(prev.personality_distribution)
        for mbti in sorted(all_mbti):
            curr_c = current.personality_distribution.get(mbti, 0)
            prev_c = prev.personality_distribution.get(mbti, 0)
            if curr_c != prev_c:
                report.personality_shifts.append({
                    "mbti": mbti,
                    "from": prev_c,
                    "to": curr_c,
                    "delta": curr_c - prev_c,
                })

        # 知识增长
        report.knowledge_growth = {
            "from": prev.total_knowledge_items,
            "to": current.total_knowledge_items,
            "delta": current.total_knowledge_items - prev.total_knowledge_items,
        }

        # 能量趋势
        report.energy_trend = {
            "from": prev.avg_energy,
            "to": current.avg_energy,
            "delta": round(current.avg_energy - prev.avg_energy, 1),
        }

        # 派系变化
        report.faction_changes = {
            "from": prev.faction_count,
            "to": current.faction_count,
            "delta": current.faction_count - prev.faction_count,
        }

        # 人口变化
        report.population_change = {
            "from": prev.total_digimon,
            "to": current.total_digimon,
            "delta": current.total_digimon - prev.total_digimon,
        }

        # 一致性趋势
        report.coherence_trend = {
            "from": prev.avg_coherence_score,
            "to": current.avg_coherence_score,
            "delta": round(current.avg_coherence_score - prev.avg_coherence_score, 2),
        }

        return report

    def _build_hall_of_fame(self, digimon_data: list[dict[str, Any]]) -> HallOfFame:
        """基于数码兽数据构建名人堂."""

        def _rank(key: str, default: float = 0.0, detail_key: str | None = None) -> list[HallOfFameEntry]:
            ranked = sorted(
                [
                    HallOfFameEntry(
                        name=d.get("name", "?"),
                        value=float(d.get(key, default)),
                        detail=d.get(detail_key, "") if detail_key else "",
                    )
                    for d in digimon_data
                ],
                key=lambda e: -e.value,
            )
            return ranked[:HALL_OF_FAME_SIZE]

        return HallOfFame(
            top_fighters=_rank("battle_victories", 0, "evolution_stage"),
            top_inventors=_rank("knowledge_invented", 0, "current_mbti"),
            top_socializers=_rank("memory_count", 0, "faction_name"),
            top_altruists=_rank("energy_donated", 0.0, "faction_name"),
            most_evolved=_rank("evolution_score", 0, "evolution_stage"),
        )

    def _generate_summary(
        self,
        snapshot: WorldSnapshot,
        events: list[CuratedEvent],
        trends: TrendReport,
        hall: HallOfFame,
    ) -> str:
        """生成人类可读的章节摘要."""
        parts: list[str] = []

        parts.append(
            f"Epoch snapshot: {snapshot.total_digimon} digimon "
            f"({snapshot.active_digimon} active, {snapshot.dormant_digimon} dormant), "
            f"avg energy {snapshot.avg_energy:.1f}, {snapshot.faction_count} factions, "
            f"{snapshot.total_knowledge_items} knowledge items."
        )

        if events:
            top3 = events[:3]
            parts.append("Top events: " + "; ".join(
                f"[{e.event_type}] {e.title}" for e in top3
            ))

        if hall and hall.top_fighters:
            parts.append(f"Hall of Fame — Top fighter: {hall.top_fighters[0].name}.")

        if trends and trends.knowledge_growth.get("delta", 0) > 0:
            parts.append(
                f"Knowledge grew by +{trends.knowledge_growth['delta']} items this epoch."
            )

        return " ".join(parts)

    # -- 辅助 --

    @staticmethod
    def _event_title(evt: dict[str, Any]) -> str:
        """从事件数据提取可读标题."""
        etype = evt.get("type", "unknown")
        if etype == "dialogue":
            sp = evt.get("speaker", "?")
            ln = evt.get("listener", "?")
            line = evt.get("line", "")
            return f"{sp} ↔ {ln}: {line[:40]}"
        if etype == "battle":
            a = evt.get("attacker", evt.get("a", "?"))
            b = evt.get("defender", evt.get("b", "?"))
            return f"{a} ⚔ {b}"
        if etype == "evolution":
            name = evt.get("digimon_name", evt.get("name", "?"))
            stage = evt.get("to_stage", evt.get("new_stage", "?"))
            return f"{name} evolved to {stage}"
        if etype == "personality_shift":
            name = evt.get("name", "?")
            return f"{name}'s personality shifted"
        if etype == "knowledge_invented":
            inv = evt.get("inventor_name", evt.get("name", "?"))
            kn = evt.get("knowledge_name", evt.get("title", "?"))
            return f"{inv} invented {kn}"
        if etype == "faction_create":
            fn = evt.get("faction_name", evt.get("name", "?"))
            return f"Faction '{fn}' formed"
        if etype in ("dark_gear", "disaster", "environmental_event"):
            return evt.get("description", evt.get("title", etype))[:60]
        return evt.get("title", evt.get("description", etype))[:60]

    @staticmethod
    def _extract_participants(evt: dict[str, Any]) -> list[str]:
        """从事件中提取参与者列表."""
        participants: list[str] = []
        for key in ("participants", "members", "speaker", "listener",
                     "attacker", "defender", "name", "digimon_name",
                     "inventor_name"):
            val = evt.get(key)
            if isinstance(val, str):
                if val not in participants:
                    participants.append(val)
            elif isinstance(val, list):
                for v in val:
                    if isinstance(v, str) and v not in participants:
                        participants.append(v)
        return participants

    def _chapter_to_dict(self, chapter: AlmanacChapter) -> dict[str, Any]:
        """章节序列化."""
        return {
            "epoch": chapter.epoch,
            "tick_start": chapter.tick_start,
            "tick_end": chapter.tick_end,
            "world_time_start": chapter.world_time_start,
            "world_time_end": chapter.world_time_end,
            "snapshot": dataclasses.asdict(chapter.snapshot),
            "top_events": [dataclasses.asdict(e) for e in chapter.top_events],
            "trends": dataclasses.asdict(chapter.trends) if chapter.trends else None,
            "hall_of_fame": dataclasses.asdict(chapter.hall_of_fame) if chapter.hall_of_fame else None,
            "generated_at": chapter.generated_at,
            "event_count": chapter.event_count,
            "narrative_summary": chapter.narrative_summary,
        }


# ---- 工厂函数 ----

def create_almanac() -> WorldAlmanac:
    """创建默认配置的 WorldAlmanac 实例."""
    return WorldAlmanac()

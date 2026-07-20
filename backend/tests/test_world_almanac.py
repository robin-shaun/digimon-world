"""
Phase 29 测试 — WorldAlmanac
=============================

测试覆盖:
- AlmanacChapter / WorldSnapshot / CuratedEvent / TrendReport / HallOfFame 数据类
- WorldAlmanac.generate_chapter() — 基本章节生成
- WorldAlmanac.archive() / get_chapter() / list_chapters() / latest_chapter
- WorldAlmanac.should_generate() — epoch 阈值逻辑
- WorldAlmanac.get_current_snapshot() — 实时快照
- WorldAlmanac.export() — JSON 序列化
- 趋势对比 (TrendReport) — 相邻章节 diff
- 名人堂排序 — HallOfFame 各维度排行
- 事件策展 — _curate_events 筛选/排序
- 边界情况: 空数据、单数码兽、无事件、首章节无趋势
"""

from __future__ import annotations

import json

import pytest

from digimon_world.world.world_almanac import (
    HALL_OF_FAME_SIZE,
    AlmanacChapter,
    CuratedEvent,
    HallOfFame,
    HallOfFameEntry,
    TrendReport,
    WorldAlmanac,
    WorldSnapshot,
    create_almanac,
)

# ---- Fixtures ----

@pytest.fixture
def almanac() -> WorldAlmanac:
    return create_almanac()


@pytest.fixture
def sample_digimon_data() -> list[dict]:
    return [
        {
            "name": "亚古兽", "energy": {"current": 85.0, "max": 100},
            "personality": {"mbti": "ENFP", "type": "campaigner"},
            "region_id": "server_continent", "evolution": {"stage": "champion", "score": 3},
            "battle_victories": 12, "knowledge_invented": 3, "memory_count": 45,
            "energy_donated": 25.0, "evolution_stage": "champion",
            "current_mbti": "ENFP", "faction_name": "brave_hearts",
        },
        {
            "name": "加布兽", "energy": {"current": 72.0, "max": 100},
            "personality": {"mbti": "ISFJ", "type": "defender"},
            "region_id": "server_continent", "evolution": {"stage": "champion", "score": 3},
            "battle_victories": 8, "knowledge_invented": 1, "memory_count": 38,
            "energy_donated": 10.0, "evolution_stage": "champion",
            "current_mbti": "ISFJ", "faction_name": "brave_hearts",
        },
        {
            "name": "比丘兽", "energy": {"current": 0.0, "max": 100},
            "personality": {"mbti": "ESFP", "type": "entertainer"},
            "region_id": "file_island", "evolution": {"stage": "rookie", "score": 2},
            "battle_victories": 3, "knowledge_invented": 0, "memory_count": 20,
            "energy_donated": 0.0, "evolution_stage": "rookie",
            "current_mbti": "ESFP", "faction_name": "",
        },
        {
            "name": "甲虫兽", "energy": {"current": 90.0, "max": 100},
            "personality": {"mbti": "INTJ", "type": "architect"},
            "region_id": "file_island", "evolution": {"stage": "ultimate", "score": 4},
            "battle_victories": 20, "knowledge_invented": 5, "memory_count": 60,
            "energy_donated": 40.0, "evolution_stage": "ultimate",
            "current_mbti": "INTJ", "faction_name": "knowledge_seekers",
        },
        {
            "name": "巴鲁兽", "energy": {"current": 55.0, "max": 100},
            "personality": {"mbti": "INFP", "type": "mediator"},
            "region_id": "server_continent", "evolution": {"stage": "rookie", "score": 2},
            "battle_victories": 2, "knowledge_invented": 0, "memory_count": 15,
            "energy_donated": 5.0, "evolution_stage": "rookie",
            "current_mbti": "INFP", "faction_name": "",
        },
    ]


@pytest.fixture
def sample_events() -> list[dict]:
    return [
        {
            "type": "dialogue", "tick": 5, "world_time": "Day 1, 06:00",
            "speaker": "亚古兽", "listener": "加布兽",
            "line": "加布兽！我们一起去找吃的吧！",
            "significance": 6.5,
        },
        {
            "type": "battle", "tick": 12, "world_time": "Day 1, 08:30",
            "attacker": "甲虫兽", "defender": "比丘兽",
            "description": "甲虫兽挑战比丘兽",
            "significance": 7.2,
        },
        {
            "type": "evolution", "tick": 20, "world_time": "Day 1, 10:00",
            "digimon_name": "亚古兽", "to_stage": "champion",
            "description": "亚古兽进化！暴龙兽！",
            "significance": 9.0,
        },
        {
            "type": "knowledge_invented", "tick": 35, "world_time": "Day 1, 14:00",
            "inventor_name": "甲虫兽", "knowledge_name": "闪电突刺战术",
            "significance": 5.6,
        },
        {
            "type": "personality_shift", "tick": 45, "world_time": "Day 1, 16:00",
            "name": "巴鲁兽",
            "description": "巴鲁兽变得更外向",
            "significance": 4.0,
        },
        {
            "type": "faction_create", "tick": 60, "world_time": "Day 2, 08:00",
            "faction_name": "brave_hearts",
            "members": ["亚古兽", "加布兽"],
            "significance": 8.0,
        },
    ]


@pytest.fixture
def sample_snapshot_data() -> dict:
    return {
        "total_knowledge_items": 9,
        "total_conventions": 3,
        "faction_count": 2,
        "avg_coherence_score": 0.87,
    }


# ---- 数据类测试 ----

class TestWorldSnapshot:
    def test_basic_fields(self, sample_digimon_data, sample_snapshot_data):
        snap = WorldSnapshot(
            tick=50, world_time="Day 2, 06:00",
            total_digimon=5, active_digimon=4, dormant_digimon=1,
            avg_energy=70.0, total_knowledge_items=9, total_conventions=3,
            faction_count=2, avg_coherence_score=0.87,
            personality_distribution={"ENFP": 1, "ISFJ": 1, "ESFP": 1, "INTJ": 1, "INFP": 1},
            region_populations={"server_continent": 3, "file_island": 2},
            evolution_distribution={"rookie": 2, "champion": 2, "ultimate": 1},
        )
        assert snap.total_digimon == 5
        assert snap.active_digimon == 4
        assert snap.dormant_digimon == 1
        assert snap.avg_energy == 70.0
        assert snap.faction_count == 2

    def test_defaults(self):
        snap = WorldSnapshot(tick=0, world_time="Day 1, 00:00",
                             total_digimon=0, active_digimon=0, dormant_digimon=0,
                             avg_energy=0.0, total_knowledge_items=0, total_conventions=0,
                             faction_count=0, avg_coherence_score=0.0)
        assert snap.personality_distribution == {}
        assert snap.region_populations == {}
        assert snap.evolution_distribution == {}


class TestCuratedEvent:
    def test_create(self):
        evt = CuratedEvent(
            event_type="battle", title="A ⚔ B", description="A fought B",
            tick=10, world_time="Day 1, 03:00", significance=7.5,
            participants=["A", "B"], location="server_continent",
        )
        assert evt.event_type == "battle"
        assert evt.significance == 7.5

    def test_defaults(self):
        evt = CuratedEvent(
            event_type="dialogue", title="test", description="",
            tick=0, world_time="", significance=0.0,
        )
        assert evt.participants == []
        assert evt.location == ""


class TestTrendReport:
    def test_default_empty(self):
        report = TrendReport()
        assert report.personality_shifts == []
        assert report.knowledge_growth == {}
        assert report.energy_trend == {}


class TestHallOfFame:
    def test_create(self):
        hall = HallOfFame(
            top_fighters=[HallOfFameEntry("甲虫兽", 20, "ultimate")],
            top_inventors=[HallOfFameEntry("甲虫兽", 5, "INTJ")],
            top_socializers=[HallOfFameEntry("甲虫兽", 60, "knowledge_seekers")],
            top_altruists=[HallOfFameEntry("甲虫兽", 40.0, "knowledge_seekers")],
            most_evolved=[HallOfFameEntry("甲虫兽", 4, "ultimate")],
        )
        assert len(hall.top_fighters) == 1
        assert hall.top_fighters[0].name == "甲虫兽"

    def test_default_empty(self):
        hall = HallOfFame()
        assert hall.top_fighters == []
        assert hall.top_inventors == []


class TestAlmanacChapter:
    def test_create(self):
        snap = WorldSnapshot(tick=100, world_time="Day 5, 00:00",
                             total_digimon=5, active_digimon=4, dormant_digimon=1,
                             avg_energy=65.0, total_knowledge_items=10, total_conventions=2,
                             faction_count=1, avg_coherence_score=0.85)
        chapter = AlmanacChapter(
            epoch=1, tick_start=0, tick_end=100,
            world_time_start="Day 1, 00:00", world_time_end="Day 5, 00:00",
            snapshot=snap, event_count=3, narrative_summary="summary",
        )
        assert chapter.epoch == 1
        assert chapter.tick_start == 0
        assert chapter.tick_end == 100
        assert chapter.event_count == 3


# ---- WorldAlmanac 核心逻辑 ----

class TestWorldAlmanacGenerate:
    def test_generate_first_chapter(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(
            tick=100, world_time="Day 5, 00:00",
            snapshot_data=sample_snapshot_data,
            events=sample_events,
            digimon_data=sample_digimon_data,
        )
        assert chapter.epoch == 1
        assert chapter.tick_start == 0
        assert chapter.tick_end == 100
        assert chapter.world_time_start == "Day 1, 00:00"
        assert chapter.world_time_end == "Day 5, 00:00"

    def test_snapshot_correct(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5, 00:00", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        snap = chapter.snapshot
        assert snap.total_digimon == 5
        assert snap.active_digimon == 4
        assert snap.dormant_digimon == 1
        assert snap.total_knowledge_items == 9
        assert snap.total_conventions == 3
        assert snap.faction_count == 2
        assert snap.avg_coherence_score == 0.87

    def test_personality_distribution(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5, 00:00", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        pd = chapter.snapshot.personality_distribution
        assert pd["ENFP"] == 1
        assert pd["ISFJ"] == 1
        assert pd["ESFP"] == 1
        assert pd["INTJ"] == 1
        assert pd["INFP"] == 1

    def test_region_populations(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5, 00:00", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        rp = chapter.snapshot.region_populations
        assert rp["server_continent"] == 3
        assert rp["file_island"] == 2

    def test_evolution_distribution(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5, 00:00", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        ed = chapter.snapshot.evolution_distribution
        assert ed["rookie"] == 2
        assert ed["champion"] == 2
        assert ed["ultimate"] == 1

    def test_events_curated(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5, 00:00", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        assert len(chapter.top_events) > 0
        assert len(chapter.top_events) <= 20
        # 按 significance 降序
        sigs = [e.significance for e in chapter.top_events]
        assert sigs == sorted(sigs, reverse=True)

    def test_hall_of_fame(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5, 00:00", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        hall = chapter.hall_of_fame
        assert hall is not None
        # 甲虫兽战斗最多 (20)
        assert hall.top_fighters[0].name == "甲虫兽"
        assert hall.top_fighters[0].value == 20
        # 甲虫兽发明最多
        assert hall.top_inventors[0].name == "甲虫兽"
        assert hall.top_inventors[0].value == 5

    def test_narrative_summary_generated(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5, 00:00", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        assert chapter.narrative_summary != ""
        assert "5 digimon" in chapter.narrative_summary


class TestWorldAlmanacArchive:
    def test_archive_and_retrieve(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        almanac.archive(chapter)
        retrieved = almanac.get_chapter(1)
        assert retrieved is not None
        assert retrieved.epoch == 1
        assert retrieved.tick_end == 100

    def test_archive_is_immutable(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        almanac.archive(chapter)
        # 修改原 chapter 不应影响 archived 版本
        chapter.narrative_summary = "hacked"
        retrieved = almanac.get_chapter(1)
        assert retrieved.narrative_summary != "hacked"

    def test_archive_updates_last_tick(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        almanac.archive(chapter)
        assert almanac._last_archived_tick == 100

    def test_latest_chapter(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        c1 = almanac.generate_chapter(100, "Day 5", sample_snapshot_data, sample_events, sample_digimon_data)
        almanac.archive(c1)
        c2 = almanac.generate_chapter(200, "Day 10", sample_snapshot_data, sample_events, sample_digimon_data,
                                      tick_start=101, world_time_start="Day 5")
        almanac.archive(c2)
        latest = almanac.latest_chapter
        assert latest is not None
        assert latest.epoch == 2

    def test_latest_chapter_empty(self, almanac):
        assert almanac.latest_chapter is None

    def test_list_chapters(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        c1 = almanac.generate_chapter(100, "Day 5", sample_snapshot_data, sample_events, sample_digimon_data)
        almanac.archive(c1)
        c2 = almanac.generate_chapter(200, "Day 10", sample_snapshot_data, sample_events, sample_digimon_data,
                                      tick_start=101, world_time_start="Day 5")
        almanac.archive(c2)
        chapters = almanac.list_chapters()
        assert len(chapters) == 2
        assert chapters[0].epoch == 1
        assert chapters[1].epoch == 2


class TestWorldAlmanacShouldGenerate:
    def test_too_soon(self, almanac):
        almanac._last_archived_tick = 0
        assert not almanac.should_generate(tick=50, event_count=10)

    def test_not_enough_events(self, almanac):
        almanac._last_archived_tick = 0
        assert not almanac.should_generate(tick=150, event_count=1)

    def test_should_generate(self, almanac):
        almanac._last_archived_tick = 0
        assert almanac.should_generate(tick=150, event_count=5)

    def test_zero_events(self, almanac):
        almanac._last_archived_tick = 0
        assert not almanac.should_generate(tick=200, event_count=0)


class TestWorldAlmanacCurrentSnapshot:
    def test_live_snapshot(self, almanac, sample_snapshot_data, sample_digimon_data):
        snap = almanac.get_current_snapshot(50, "Day 2, 12:00", sample_snapshot_data, sample_digimon_data)
        assert snap.tick == 50
        assert snap.total_digimon == 5
        assert snap.active_digimon == 4

    def test_no_archival_side_effect(self, almanac, sample_snapshot_data, sample_digimon_data):
        almanac.get_current_snapshot(50, "Day 2", sample_snapshot_data, sample_digimon_data)
        assert len(almanac.list_chapters()) == 0
        assert almanac._last_archived_tick == -1


class TestWorldAlmanacExport:
    def test_export_empty(self, almanac):
        exported = almanac.export()
        assert exported["total_chapters"] == 0
        assert exported["last_archived_tick"] == -1
        assert exported["chapters"] == []

    def test_export_with_chapters(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        c1 = almanac.generate_chapter(100, "Day 5", sample_snapshot_data, sample_events, sample_digimon_data)
        almanac.archive(c1)
        exported = almanac.export()
        assert exported["total_chapters"] == 1
        assert len(exported["chapters"]) == 1
        ch = exported["chapters"][0]
        assert ch["epoch"] == 1
        assert "snapshot" in ch
        assert "top_events" in ch

    def test_export_json_serializable(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        c1 = almanac.generate_chapter(100, "Day 5", sample_snapshot_data, sample_events, sample_digimon_data)
        almanac.archive(c1)
        exported = almanac.export()
        # 不应抛出异常
        json_str = json.dumps(exported)
        assert len(json_str) > 0


# ---- 趋势对比 ----

class TestTrendComputation:
    def test_first_chapter_no_trend(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        # 第一章没有前一章对比，trends 应为空
        assert chapter.trends is not None
        assert chapter.trends.personality_shifts == []
        assert chapter.trends.knowledge_growth == {}

    def test_second_chapter_has_trend(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        c1 = almanac.generate_chapter(100, "Day 5", sample_snapshot_data, sample_events, sample_digimon_data)
        almanac.archive(c1)

        # 制造差异数据
        changed_snapshot = {**sample_snapshot_data,
                            "total_knowledge_items": 15, "faction_count": 3, "avg_coherence_score": 0.90}
        changed_digimon = [dict(d) for d in sample_digimon_data]
        changed_digimon[0]["personality"]["mbti"] = "ENTJ"  # 从 ENFP 变 ENTJ
        changed_digimon.append({
            "name": "哥玛兽", "energy": {"current": 95.0, "max": 100},
            "personality": {"mbti": "ISTP", "type": "virtuoso"},
            "region_id": "file_island", "evolution": {"stage": "rookie", "score": 2},
            "battle_victories": 1, "knowledge_invented": 0, "memory_count": 5,
            "energy_donated": 0.0, "evolution_stage": "rookie",
            "current_mbti": "ISTP", "faction_name": "",
        })

        c2 = almanac.generate_chapter(200, "Day 10", changed_snapshot, sample_events,
                                      changed_digimon, tick_start=101, world_time_start="Day 5")
        assert c2.trends is not None
        # 人格漂移
        assert len(c2.trends.personality_shifts) >= 1
        # 知识增长
        assert c2.trends.knowledge_growth["delta"] == 6
        # 能量趋势
        assert c2.trends.energy_trend["delta"] != 0.0
        # 派系变化
        assert c2.trends.faction_changes["delta"] == 1
        # 人口变化
        assert c2.trends.population_change["delta"] == 1


# ---- 边界情况 ----

class TestEdgeCases:
    def test_empty_digimon(self, almanac):
        snap = almanac.get_current_snapshot(0, "Day 1", {}, [])
        assert snap.total_digimon == 0
        assert snap.active_digimon == 0
        assert snap.avg_energy == 0.0

    def test_single_digimon(self, almanac):
        single = [{"name": "亚古兽", "energy": {"current": 100.0},
                   "personality": {"mbti": "ENFP"}, "region_id": "server",
                   "evolution": {"stage": "rookie"}, "battle_victories": 0,
                   "knowledge_invented": 0, "memory_count": 10, "energy_donated": 0.0,
                   "evolution_stage": "rookie", "current_mbti": "ENFP", "faction_name": ""}]
        snap = almanac.get_current_snapshot(1, "Day 1", {}, single)
        assert snap.total_digimon == 1
        assert snap.active_digimon == 1
        assert snap.dormant_digimon == 0

    def test_all_dormant(self, almanac):
        dormant_data = [
            {"name": f"d{d}", "energy": {"current": 0.0},
             "personality": {"mbti": "UNKN"}, "region_id": "void",
             "evolution": {"stage": "rookie"}, "battle_victories": 0,
             "knowledge_invented": 0, "memory_count": 0, "energy_donated": 0.0,
             "evolution_stage": "rookie", "current_mbti": "UNKN", "faction_name": ""}
            for d in range(3)
        ]
        snap = almanac.get_current_snapshot(1, "Day 1", {}, dormant_data)
        assert snap.total_digimon == 3
        assert snap.active_digimon == 0
        assert snap.dormant_digimon == 3
        assert snap.avg_energy == 0.0

    def test_no_events(self, almanac, sample_snapshot_data, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5", sample_snapshot_data, [], sample_digimon_data)
        assert chapter.top_events == []
        assert chapter.event_count == 0

    def test_events_outside_tick_range(self, almanac, sample_snapshot_data, sample_digimon_data):
        far_events = [
            {"type": "battle", "tick": 5, "significance": 9.0,
             "attacker": "A", "defender": "B", "description": "early"},
        ]
        chapter = almanac.generate_chapter(100, "Day 5", sample_snapshot_data, far_events,
                                           sample_digimon_data, tick_start=50)
        # 事件 tick=5 在 [50,100] 范围外
        assert chapter.top_events == []

    def test_hall_of_fame_size_limit(self, almanac, sample_snapshot_data, sample_events, sample_digimon_data):
        chapter = almanac.generate_chapter(100, "Day 5", sample_snapshot_data,
                                           sample_events, sample_digimon_data)
        hall = chapter.hall_of_fame
        assert hall is not None
        assert len(hall.top_fighters) <= HALL_OF_FAME_SIZE
        assert len(hall.top_inventors) <= HALL_OF_FAME_SIZE
        assert len(hall.top_socializers) <= HALL_OF_FAME_SIZE
        assert len(hall.top_altruists) <= HALL_OF_FAME_SIZE
        assert len(hall.most_evolved) <= HALL_OF_FAME_SIZE

    def test_events_sorted_by_significance_desc(self, almanac, sample_snapshot_data, sample_digimon_data):
        mixed_events = [
            {"type": "dialogue", "tick": 10, "significance": 3.0, "speaker": "A", "listener": "B", "line": "hi"},
            {"type": "battle", "tick": 20, "significance": 9.0, "attacker": "A", "defender": "B"},
            {"type": "evolution", "tick": 30, "significance": 6.0, "digimon_name": "A", "to_stage": "champion"},
        ]
        chapter = almanac.generate_chapter(50, "Day 3", sample_snapshot_data, mixed_events, sample_digimon_data)
        sigs = [e.significance for e in chapter.top_events]
        assert sigs == [9.0, 6.0, 3.0]

    def test_unknown_personality_default(self, almanac):
        unknown_d = [
            {"name": "x", "energy": {"current": 50.0},
             "personality": {}, "region_id": "void",
             "evolution": {"stage": "unknown"},
             "battle_victories": 0, "knowledge_invented": 0, "memory_count": 0,
             "energy_donated": 0.0, "evolution_stage": "unknown",
             "current_mbti": "UNKN", "faction_name": ""}
        ]
        snap = almanac.get_current_snapshot(1, "Day 1", {}, unknown_d)
        assert snap.personality_distribution.get("UNKN", 0) == 1
        assert snap.region_populations.get("void", 0) == 1


# ---- create_almanac 工厂 ----

class TestCreateAlmanac:
    def test_creates_instance(self):
        a = create_almanac()
        assert isinstance(a, WorldAlmanac)
        assert a._last_archived_tick == -1
        assert len(a.list_chapters()) == 0


# ---- 多章节序列 ----

class TestMultiChapterSequence:
    def test_three_chapter_sequence(self, almanac):
        digi = [
            {"name": "A", "energy": {"current": 80.0}, "personality": {"mbti": "ENFP"},
             "region_id": "r1", "evolution": {"stage": "rookie"},
             "battle_victories": 1, "knowledge_invented": 0, "memory_count": 5,
             "energy_donated": 0.0, "evolution_stage": "rookie",
             "current_mbti": "ENFP", "faction_name": ""},
        ]
        evts = [
            {"type": "dialogue", "tick": 10, "significance": 5.0,
             "speaker": "A", "listener": "B", "line": "hello"},
        ]
        snap = {"total_knowledge_items": 1, "total_conventions": 0,
                "faction_count": 0, "avg_coherence_score": 1.0}

        c1 = almanac.generate_chapter(100, "Day 5", snap, evts, digi)
        almanac.archive(c1)
        c2 = almanac.generate_chapter(200, "Day 10", snap, evts, digi,
                                      tick_start=101, world_time_start="Day 5")
        almanac.archive(c2)
        c3 = almanac.generate_chapter(300, "Day 15", snap, evts, digi,
                                      tick_start=201, world_time_start="Day 10")
        almanac.archive(c3)

        chapters = almanac.list_chapters()
        assert len(chapters) == 3
        assert chapters[0].epoch == 1
        assert chapters[1].epoch == 2
        assert chapters[2].epoch == 3
        assert chapters[2].tick_start == 201
        assert chapters[2].tick_end == 300

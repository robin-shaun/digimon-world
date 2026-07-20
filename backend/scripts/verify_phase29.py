#!/usr/bin/env python3
"""
Phase 29 端到端验证: 世界年鉴与历史叙事
========================================

验证内容:
A) 核心模块: WorldAlmanac, AlmanacChapter, WorldSnapshot, CuratedEvent, TrendReport, HallOfFame
B) 引擎: generate_chapter, archive, get_chapter, list_chapters, should_generate, get_current_snapshot, export
C) API 端点: GET /api/almanac, GET /api/almanac/current, GET /api/almanac/{epoch}
D) 集成: 模拟事件流 + 多章生成 + 趋势对比

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase29.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend project root is on sys.path
_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

# ---- Data helpers ----
# We need to be careful with imports — some modules might try to import
# FastAPI / other deps that require a running environment.

from digimon_world.world.world_almanac import (  # noqa: E402
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

_PASS, _FAIL, _CHECK = 0, 0, 0
MAX_LINE = 55


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL, _CHECK
    _CHECK += 1
    status = "\u2705" if condition else "\u274c"
    line = f"{name:.<{MAX_LINE}} {status}"
    if detail and not condition:
        line += f"  ({detail})"
    print(line)
    if condition:
        _PASS += 1
    else:
        _FAIL += 1


def header(title: str) -> None:
    print(f"\n{'='*64}")
    print(f"  {title}")
    print(f"{'='*64}")


# ── Sample Data ──

def _make_digimon(name, energy, mbti, region, stage, victories, knowledge, memories, donated, evo_score):
    return {
        "name": name,
        "energy": {"current": energy, "max": 100},
        "personality": {"mbti": mbti},
        "region_id": region,
        "evolution": {"stage": stage, "score": evo_score},
        "battle_victories": victories,
        "knowledge_invented": knowledge,
        "memory_count": memories,
        "energy_donated": donated,
        "evolution_stage": stage,
        "current_mbti": mbti,
        "faction_name": "brave_hearts",
        "knowledge_citations": knowledge * 3,
        "evolution_score": evo_score,
        "invention_count": knowledge,
    }


def _make_event(etype, tick, world_time, significance, participants=None, desc="", location=""):
    return {
        "type": etype,
        "tick": tick,
        "world_time": world_time,
        "significance": significance,
        "participants": participants or [],
        "description": desc or f"{etype} event at tick {tick}",
        "location": location,
    }


def _make_snapshot_data(knowledge=0, conventions=0, factions=0, coherence=0.0):
    return {
        "total_knowledge_items": knowledge,
        "total_conventions": conventions,
        "faction_count": factions,
        "avg_coherence_score": coherence,
    }


# ═══════════════════════════════════════════════════════════════════════════════
print("\U0001f4d6 Phase 29 端到端验证: 世界年鉴与历史叙事")
print(f"{'='*64}")

# ══════════════════════════════════════════════════════════════════════════
# Part A: 数据类 + 引擎初始化
# ══════════════════════════════════════════════════════════════════════════
header("Part A: 数据类 + 引擎初始化")

almanac = create_almanac()
check("A1. create_almanac 返回 WorldAlmanac", isinstance(almanac, WorldAlmanac))
check("A2. 初始无章节", len(almanac.list_chapters()) == 0)
check("A3. latest_chapter = None", almanac.latest_chapter is None)

# WorldSnapshot
snap = WorldSnapshot(
    tick=100, world_time="Day 1, 00:100",
    total_digimon=5, active_digimon=4, dormant_digimon=1,
    avg_energy=75.0, total_knowledge_items=0, total_conventions=0,
    faction_count=2, avg_coherence_score=0.8,
    personality_distribution={"ENFP": 2, "ISFJ": 3},
    region_populations={"server": 5},
    evolution_distribution={"rookie": 2, "champion": 3},
)
check("A4. WorldSnapshot 创建成功", snap.total_digimon == 5)
check("A5. dormant 正确", snap.dormant_digimon == 1)

# CuratedEvent
ce = CuratedEvent(
    event_type="battle", title="Agumon ⚔ Gabumon",
    description="热血对决", tick=50, world_time="Day 1, 00:50",
    significance=7.5, participants=["Agumon", "Gabumon"], location="server"
)
check("A6. CuratedEvent 创建", ce.event_type == "battle" and ce.significance == 7.5)

# HallOfFameEntry
hfe = HallOfFameEntry(name="亚古兽", value=12.0, detail="champion")
check("A7. HallOfFameEntry 创建", hfe.name == "亚古兽" and hfe.value == 12.0)

# TrendReport
tr = TrendReport(
    personality_shifts=[{"mbti": "ENFP", "from": 2, "to": 3, "delta": 1}],
    knowledge_growth={"from": 0, "to": 3, "delta": 3},
    energy_trend={"from": 70.0, "to": 75.0, "delta": 5.0},
    faction_changes={"from": 1, "to": 2, "delta": 1},
    population_change={"from": 4, "to": 5, "delta": 1},
    coherence_trend={"from": 0.7, "to": 0.8, "delta": 0.1},
)
check("A8. TrendReport 创建", tr.energy_trend["delta"] == 5.0)

# AlmanacChapter
chap = AlmanacChapter(
    epoch=1, tick_start=0, tick_end=100,
    world_time_start="Day 1, 00:00", world_time_end="Day 1, 00:100",
    snapshot=snap, top_events=[ce], trends=tr,
    hall_of_fame=HallOfFame(top_fighters=[hfe]),
    generated_at="Day 1, 00:100", event_count=1,
    narrative_summary="Test chapter",
)
check("A9. AlmanacChapter 创建", chap.epoch == 1 and chap.event_count == 1)

# ══════════════════════════════════════════════════════════════════════════
# Part B: 章节生成 + 归档
# ══════════════════════════════════════════════════════════════════════════
header("Part B: 章节生成 + 归档")

digimon_data = [
    _make_digimon("亚古兽", 85, "ENFP", "server", "champion", 12, 3, 45, 25.0, 3),
    _make_digimon("加布兽", 72, "ISFJ", "server", "champion", 8, 1, 38, 10.0, 3),
    _make_digimon("比丘兽", 95, "ESFP", "file_island", "rookie", 3, 0, 20, 5.0, 1),
    _make_digimon("巴鲁兽", 60, "INTP", "server", "champion", 15, 5, 55, 30.0, 4),
    _make_digimon("甲虫兽", 88, "ISTJ", "file_island", "rookie", 1, 0, 12, 2.0, 1),
]

events = [
    _make_event("battle", 10, "Day 1, 00:10", 8.0, ["亚古兽", "加布兽"], "亚古兽 vs 加布兽", "server"),
    _make_event("dialogue", 25, "Day 1, 00:25", 5.5, ["亚古兽", "巴鲁兽"], "你好吗？", "server"),
    _make_event("evolution", 40, "Day 1, 00:40", 9.0, ["比丘兽"], "比丘兽进化", "file_island"),
    _make_event("knowledge_invented", 60, "Day 1, 01:00", 7.0, ["巴鲁兽"], "发明: 种子炸弹", "server"),
    _make_event("dialogue", 75, "Day 1, 01:15", 3.0, ["加布兽", "甲虫兽"], "闲聊", "file_island"),
    _make_event("personality_shift", 90, "Day 1, 01:30", 6.5, ["亚古兽"], "亚古兽变得更外向", "server"),
]

snap_data = _make_snapshot_data(knowledge=10, conventions=3, factions=2, coherence=0.75)

# Generate first chapter
chapter1 = almanac.generate_chapter(
    tick=100, world_time="Day 1, 01:40",
    snapshot_data=snap_data, events=events, digimon_data=digimon_data,
)
check("B1. generate_chapter 返回 AlmanacChapter", isinstance(chapter1, AlmanacChapter))
check("B2. epoch=1", chapter1.epoch == 1)
check("B3. tick range [0, 100]", chapter1.tick_start == 0 and chapter1.tick_end == 100)
check("B4. snapshot 数码兽数=5", chapter1.snapshot.total_digimon == 5)
check("B5. snapshot 活跃=5", chapter1.snapshot.active_digimon == 5)
check("B6. snapshot 能量 > 0", chapter1.snapshot.avg_energy > 0)
check("B7. top_events 非空", len(chapter1.top_events) > 0)
check("B8. 趋势非 None (首章无对比)", chapter1.trends is not None)
check("B9. 名人堂非 None", chapter1.hall_of_fame is not None)
check("B10. 名人堂 top_fighters[0] = 巴鲁兽 (15胜)",
      len(chapter1.hall_of_fame.top_fighters) > 0
      and chapter1.hall_of_fame.top_fighters[0].name == "巴鲁兽")
check("B11. narrative_summary 非空", len(chapter1.narrative_summary) > 10)

# Archive
almanac.archive(chapter1)
check("B12. archive 后 list_chapters=1", len(almanac.list_chapters()) == 1)
check("B13. latest_chapter.epoch=1",
      almanac.latest_chapter is not None and almanac.latest_chapter.epoch == 1)

# Second chapter with updated data
digimon_data2 = [
    _make_digimon("亚古兽", 60, "ENFP", "server", "champion", 14, 4, 50, 28.0, 4),
    _make_digimon("加布兽", 55, "ISFJ", "server", "champion", 9, 2, 42, 12.0, 3),
    _make_digimon("比丘兽", 88, "ESFP", "file_island", "rookie", 4, 0, 24, 6.0, 1),
    _make_digimon("巴鲁兽", 50, "INTP", "server", "ultimate", 18, 7, 60, 35.0, 5),
    _make_digimon("甲虫兽", 78, "ISTJ", "file_island", "rookie", 2, 1, 15, 3.0, 1),
]
events2 = [
    _make_event("battle", 130, "Day 2, 02:10", 9.0, ["巴鲁兽", "亚古兽"], "巴鲁兽 vs 亚古兽", "server"),
    _make_event("dialogue", 150, "Day 2, 02:30", 6.0, ["加布兽", "比丘兽"], "你知道吗...", "file_island"),
    _make_event("dark_gear", 170, "Day 2, 02:50", 9.5, ["黑暗齿轮"], "黑暗齿轮出现", "server"),
]
snap_data2 = _make_snapshot_data(knowledge=15, conventions=4, factions=2, coherence=0.82)

chapter2 = almanac.generate_chapter(
    tick=200, world_time="Day 2, 03:20",
    snapshot_data=snap_data2, events=events2, digimon_data=digimon_data2,
)
almanac.archive(chapter2)
check("B14. archive 后 list_chapters=2", len(almanac.list_chapters()) == 2)
check("B15. latest_chapter.epoch=2", almanac.latest_chapter.epoch == 2)

# get_chapter
c1 = almanac.get_chapter(1)
check("B16. get_chapter(1) 非 None", c1 is not None)
c2 = almanac.get_chapter(2)
check("B17. get_chapter(2) 非 None", c2 is not None)
check("B18. get_chapter(99) = None", almanac.get_chapter(99) is None)

# list_chapters 排序
chapters = almanac.list_chapters()
check("B19. list_chapters 按 epoch 排序", [c.epoch for c in chapters] == [1, 2])

# ══════════════════════════════════════════════════════════════════════════
# Part C: 趋势对比 (跨章节)
# ══════════════════════════════════════════════════════════════════════════
header("Part C: 趋势对比")

trends = chapter2.trends
check("C1. 趋势非 None", trends is not None)
check("C2. 知识增长 delta > 0", trends.knowledge_growth.get("delta", 0) > 0)
check("C3. 知识增长 from=10 to=15",
      trends.knowledge_growth.get("from") == 10 and trends.knowledge_growth.get("to") == 15)
check("C4. 能量趋势 delta < 0 (平均下降)",
      trends.energy_trend.get("delta", 0) < 0)
check("C5. 人口不变 delta=0", trends.population_change.get("delta") == 0)
check("C6. 一致性提升 delta > 0", trends.coherence_trend.get("delta", 0) > 0)
check("C7. 有知识增长 delta 5", trends.knowledge_growth.get("delta") == 5)

# 人格漂移
check("C8. personality_shifts 是列表", isinstance(trends.personality_shifts, list))

# ══════════════════════════════════════════════════════════════════════════
# Part D: should_generate 逻辑
# ══════════════════════════════════════════════════════════════════════════
header("Part D: should_generate 逻辑")

check("D1. tick=200, 0 events → False (刚归档)", not almanac.should_generate(200, 0))
check("D2. tick=250, 0 events → False (< 100 ticks)", not almanac.should_generate(250, 0))
check("D3. tick=300, 5 events → True (>= 100 ticks, >= 3 events)",
      almanac.should_generate(300, 5))
check("D4. tick=300, 2 events → False (< 3 events)",
      not almanac.should_generate(300, 2))
check("D5. tick=350, 0 events → False", not almanac.should_generate(350, 0))

# ══════════════════════════════════════════════════════════════════════════
# Part E: get_current_snapshot (实时快照)
# ══════════════════════════════════════════════════════════════════════════
header("Part E: get_current_snapshot")

snap_cur = almanac.get_current_snapshot(
    tick=250, world_time="Day 2, 04:10",
    snapshot_data=_make_snapshot_data(knowledge=18, conventions=5, factions=3, coherence=0.85),
    digimon_data=digimon_data2,
)
check("E1. 返回 WorldSnapshot", isinstance(snap_cur, WorldSnapshot))
check("E2. tick=250", snap_cur.tick == 250)
check("E3. total=5", snap_cur.total_digimon == 5)
check("E4. avg_energy > 0", snap_cur.avg_energy > 0)
check("E5. knowledge=18", snap_cur.total_knowledge_items == 18)
check("E6. coherence=0.85", snap_cur.avg_coherence_score == 0.85)
check("E7. personality_distribution 非空",
      isinstance(snap_cur.personality_distribution, dict) and len(snap_cur.personality_distribution) > 0)
check("E8. region_populations 非空", len(snap_cur.region_populations) > 0)
check("E9. evolution_distribution 非空", len(snap_cur.evolution_distribution) > 0)

# ══════════════════════════════════════════════════════════════════════════
# Part F: export
# ══════════════════════════════════════════════════════════════════════════
header("Part F: export")

exported = almanac.export()
check("F1. 返回 dict", isinstance(exported, dict))
check("F2. total_chapters=2", exported["total_chapters"] == 2)
check("F3. last_archived_tick=200", exported["last_archived_tick"] == 200)
check("F4. chapters 列表长度=2", len(exported["chapters"]) == 2)
check("F5. 章节含 epoch", all("epoch" in c for c in exported["chapters"]))

# JSON 可序列化
try:
    import json
    json_str = json.dumps(exported, ensure_ascii=False)
    check("F6. JSON 序列化成功", len(json_str) > 100)
except Exception as e:
    check("F6. JSON 序列化成功", False, str(e))

# ══════════════════════════════════════════════════════════════════════════
# Part G: 事件策展 (_curate_events)
# ══════════════════════════════════════════════════════════════════════════
header("Part G: 事件策展")

# Use the chapter1 events that were generated
curated = chapter1.top_events
check("G1. curated 是列表", isinstance(curated, list))
check("G2. 有事件 (最多20)", len(curated) > 0)
check("G3. 按 significance 降序排列",
      all(curated[i].significance >= curated[i+1].significance
          for i in range(len(curated)-1))
      if len(curated) > 1 else True)
check("G4. 每个事件有 event_type", all(c.event_type for c in curated))
check("G5. 每个事件有 title", all(c.title for c in curated))
check("G6. 最高 sig 事件是 battle/significant",
      curated[0].significance > 0)

# ══════════════════════════════════════════════════════════════════════════
# Part H: 名人堂排序
# ══════════════════════════════════════════════════════════════════════════
header("Part H: 名人堂")

hof = chapter1.hall_of_fame
check("H1. HallOfFame 非 None", hof is not None)
check("H2. top_fighters 非空", len(hof.top_fighters) > 0)
check("H3. top_fighters 按 value 降序",
      all(hof.top_fighters[i].value >= hof.top_fighters[i+1].value
          for i in range(len(hof.top_fighters)-1)))
check("H4. top_inventors 非空", len(hof.top_inventors) > 0)
check("H5. top_socializers 非空", len(hof.top_socializers) > 0)
check("H6. 最多前5", len(hof.top_fighters) <= HALL_OF_FAME_SIZE)

# ══════════════════════════════════════════════════════════════════════════
# Part I: 边界情况
# ══════════════════════════════════════════════════════════════════════════
header("Part I: 边界情况")

almanac2 = create_almanac()

# 空数码兽列表
empty_chapter = almanac2.generate_chapter(
    tick=100, world_time="Day 1, 01:40",
    snapshot_data=_make_snapshot_data(), events=[], digimon_data=[],
)
check("I1. 空数码兽 → snapshot total=0", empty_chapter.snapshot.total_digimon == 0)
check("I2. 空数码兽 → avg_energy=0.0", empty_chapter.snapshot.avg_energy == 0.0)
check("I3. 空数码兽 → 名人堂全空",
      all(len(v) == 0 for k, v in vars(empty_chapter.hall_of_fame).items()
          if isinstance(v, list)))
check("I4. 空事件 → top_events 空", len(empty_chapter.top_events) == 0)
check("I5. 首章无趋势对比 → trends 空报告",
      isinstance(empty_chapter.trends, TrendReport)
      and empty_chapter.trends.knowledge_growth.get("delta", 0) == 0)

# generate_chapter with explicit tick_start
almanac2.archive(empty_chapter)
custom_chapter = almanac2.generate_chapter(
    tick=250, world_time="Day 2, 04:10",
    snapshot_data=_make_snapshot_data(knowledge=5),
    events=[_make_event("battle", 150, "Day 2, 02:30", 7.0, ["Agumon"])],
    digimon_data=[_make_digimon("Agumon", 90, "INTJ", "server", "rookie", 1, 0, 5, 0, 1)],
    tick_start=100, world_time_start="Day 1, 01:40",
)
check("I6. 自定义 tick_start 有效", custom_chapter.tick_start == 100)
check("I7. 自定义 world_time_start 有效",
      custom_chapter.world_time_start == "Day 1, 01:40")

# generate_chapter with auto tick_start (no prev chapter → 0)
almanac3 = create_almanac()
auto_chap = almanac3.generate_chapter(
    tick=100, world_time="Day 1, 01:40",
    snapshot_data=_make_snapshot_data(),
    events=[_make_event("dialogue", 50, "Day 1, 00:50", 5.0)],
    digimon_data=[],
)
check("I8. 无 prev chapter → tick_start=0", auto_chap.tick_start == 0)

# get_chapter before any archive
check("I9. get_chapter on unarchived almanac → None", almanac3.get_chapter(1) is None)

# ══════════════════════════════════════════════════════════════════════════
# Part J: API 端点
# ══════════════════════════════════════════════════════════════════════════
header("Part J: API 端点")

# Note: The API almanac module imports from world_state, which requires
# a running backend. We test the data path independently here.
# For API integration, we verify the router exists and is importable.

try:
    from digimon_world.api.almanac import router
    check("J1. almanac router 导入成功", True)
    check("J2. router 是 APIRouter", hasattr(router, "routes"))
    check("J3. router prefix = /api/almanac", router.prefix == "/api/almanac")

    # Check routes (paths include full prefix from APIRouter)
    route_paths = []
    for r in router.routes:
        p = getattr(r, 'path', '')
        if p:
            route_paths.append(p)
    check("J4. 路由总数 = 3", len(route_paths) == 3, f"paths={route_paths}")
    check("J5. 有 list 路由 (/api/almanac/)", "/api/almanac/" in route_paths, f"paths={route_paths}")
    check("J6. 有 current 路由 (/api/almanac/current)", "/api/almanac/current" in route_paths, f"paths={route_paths}")
    check("J6b. 有 epoch 路由 (/api/almanac/{epoch})", "/api/almanac/{epoch}" in route_paths, f"paths={route_paths}")

    # Test serialization functions
    from digimon_world.api.almanac import (
        _chapter_to_dict,
        _event_to_dict,
        _hall_of_fame_to_dict,
        _snapshot_to_dict,
        _trends_to_dict,
    )

    # _snapshot_to_dict
    sd = _snapshot_to_dict(chapter1.snapshot)
    check("J7. _snapshot_to_dict 含 tick", "tick" in sd)
    check("J8. _snapshot_to_dict 含 world_time", "world_time" in sd)
    check("J9. _snapshot_to_dict 含 total_digimon", "total_digimon" in sd)

    # _event_to_dict
    ed = _event_to_dict(chapter1.top_events[0])
    check("J10. _event_to_dict 含 event_type", "event_type" in ed)
    check("J11. _event_to_dict 含 significance", "significance" in ed)

    # _trends_to_dict
    td = _trends_to_dict(chapter2.trends)
    check("J12. _trends_to_dict 含 knowledge_growth",
          td is not None and "knowledge_growth" in td)

    # _hall_of_fame_to_dict
    hd = _hall_of_fame_to_dict(chapter1.hall_of_fame)
    check("J13. _hall_of_fame_to_dict 含 top_fighters",
          hd is not None and "top_fighters" in hd)

    # _chapter_to_dict
    cd = _chapter_to_dict(chapter1)
    check("J14. _chapter_to_dict 含 epoch", "epoch" in cd)
    check("J15. _chapter_to_dict 含 snapshot", "snapshot" in cd)
    check("J16. _chapter_to_dict 含 top_events", "top_events" in cd)
    check("J17. _chapter_to_dict 含 trends", "trends" in cd)
    check("J18. _chapter_to_dict 含 hall_of_fame", "hall_of_fame" in cd)

except ImportError as e:
    check("J. API 模块导入失败", False, str(e))
except Exception as e:
    check(f"J. API 测试异常: {type(e).__name__}", False, str(e)[:80])

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
print(f"\n{'='*64}")
print(f"  \U0001f4ca 结果: {_PASS}/{_CHECK} PASS ({_FAIL} FAIL)")
print(f"{'='*64}")

if _FAIL == 0:
    print("\n\U0001f389 Phase 29 端到端验证全部通过！")
    sys.exit(0)
else:
    print(f"\n\u26a0\ufe0f  {_FAIL} 项验证失败，请检查上述 \u274c 项。")
    sys.exit(1)

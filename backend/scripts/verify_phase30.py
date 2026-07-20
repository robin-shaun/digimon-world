#!/usr/bin/env python3
"""
Phase 30 端到端验证: 世代传承 — 数码蛋孵化、亲子羁绊与世代特质继承
==================================================================

验证内容:
A) 核心模块: LineageRecord / LineageTracker (57 unit tests exist)
B) 核心模块: EggState / Hatchery / _season_modifier (46 unit tests exist)
C) 核心模块: InheritanceEngine / InheritedTraits / 遗传四维
D) API 端点: GET /api/lineage/stats, /api/lineage/tree, /api/lineage/{name}
E) 集成: lineage + hatchery + inheritance 全生命周期

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase30.py
"""

from __future__ import annotations

import random
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

from digimon_world.world.egg_incubation import (  # noqa: E402
    MAX_INCUBATION_TICKS,
    MIN_INCUBATION_TICKS,
    EggState,
    _season_modifier,
    get_hatchery,
    reset_hatchery,
)
from digimon_world.world.lineage import (  # noqa: E402
    InheritanceEngine,
    InheritedTraits,
    LineageRecord,
    get_lineage_tracker,
    reset_lineage_tracker,
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


# ══════════════════════════════════════════════════════════════════════════
# Part A: LineageRecord — 不可变亲子记录
# ══════════════════════════════════════════════════════════════════════════
header("Part A: LineageRecord")

rec = LineageRecord(
    parent_a="Agumon",
    parent_b="Gabumon",
    child="Omnimon",
    tick_born=100,
    generation=1,
    child_species="Omegamon",
)
check("A1. LineageRecord 创建成功", rec is not None)
check("A2. parent_a", rec.parent_a == "Agumon")
check("A3. parent_b", rec.parent_b == "Gabumon")
check("A4. child", rec.child == "Omnimon")
check("A5. tick_born", rec.tick_born == 100)
check("A6. generation", rec.generation == 1)
check("A7. child_species", rec.child_species == "Omegamon")
check("A8. parents() 返回排序后的元组",
      rec.parents() == ("Agumon", "Gabumon"))
check("A8b. parents() 字典序 (B, A 输入 → A, B 输出)",
      LineageRecord("B", "A", "C", 0, 1).parents() == ("A", "B"))

d = rec.to_dict()
check("A9. to_dict() 含 parent_a", d["parent_a"] == "Agumon")
check("A10. to_dict() 含 parent_b", d["parent_b"] == "Gabumon")
check("A11. to_dict() 含 child", d["child"] == "Omnimon")
check("A12. to_dict() 含 generation", d["generation"] == 1)
check("A13. to_dict() 含 child_species", d["child_species"] == "Omegamon")

# Frozen dataclass

try:
    rec.parent_a = "X"  # type: ignore[misc]
    check("A14. LineageRecord 不可变 (frozen)", False, "should have raised")
except FrozenInstanceError:
    check("A14. LineageRecord 不可变 (frozen)", True)

# ══════════════════════════════════════════════════════════════════════════
# Part B: LineageTracker — 族谱管理器
# ══════════════════════════════════════════════════════════════════════════
header("Part B: LineageTracker")

reset_lineage_tracker()
lt = get_lineage_tracker()

# Set founders
lt.set_founders(["Agumon", "Gabumon", "Patamon"])
check("B1. 3 始祖设置成功", lt.stats()["founders"] == ["Agumon", "Gabumon", "Patamon"])
check("B2. get_generation(Agumon) = 0", lt.get_generation("Agumon") == 0)
check("B3. get_generation(Gabumon) = 0", lt.get_generation("Gabumon") == 0)
check("B4. get_generation(Patamon) = 0", lt.get_generation("Patamon") == 0)

# Register children
r1 = lt.register("Agumon", "Gabumon", "Baby1", 50, "Botamon")
check("B5. 注册 Agumon+Gabumon→Baby1 成功", r1 is not None)
check("B6. Baby1 generation = 1", r1.generation == 1)
check("B7. Baby1 父母查询", lt.get_parents("Baby1") == ("Agumon", "Gabumon"))
check("B8. get_generation(Baby1) = 1", lt.get_generation("Baby1") == 1)

r2 = lt.register("Agumon", "Patamon", "Baby2", 55, "Koromon")
check("B9. Baby2 注册成功 (同父异母)", r2.generation == 1)
check("B10. Baby2 父母 = (Agumon, Patamon)",
      lt.get_parents("Baby2") == ("Agumon", "Patamon"))

# Children query
agumon_kids = lt.get_children("Agumon")
check("B11. Agumon 子女 = [Baby1, Baby2]",
      sorted(agumon_kids) == ["Baby1", "Baby2"])

gabumon_kids = lt.get_children("Gabumon")
check("B12. Gabumon 子女 = [Baby1]", gabumon_kids == ["Baby1"])

patamon_kids = lt.get_children("Patamon")
check("B13. Patamon 子女 = [Baby2]", patamon_kids == ["Baby2"])

# Siblings
baby1_sibs = lt.get_siblings("Baby1")
check("B14. Baby1 兄弟姐妹 = [Baby2] (共享 Agumon)", baby1_sibs == ["Baby2"])

baby2_sibs = lt.get_siblings("Baby2")
check("B15. Baby2 兄弟姐妹 = [Baby1]", baby2_sibs == ["Baby1"])

# 无兄弟
check("B16. Agumon 兄弟姐妹 = [] (始祖)", lt.get_siblings("Agumon") == [])

# Gen 3: Baby1 + Baby2
r3 = lt.register("Baby1", "Baby2", "Baby3", 100, "Greymon")
check("B17. Baby3 generation = 2", r3.generation == 2)
check("B18. Baby3 父母 = (Baby1, Baby2)",
      lt.get_parents("Baby3") == ("Baby1", "Baby2"))

# Family tree
tree = lt.get_family_tree("Baby3")
check("B19. Baby3 族谱 name", tree["name"] == "Baby3")
check("B20. Baby3 族谱 generation = 2", tree["generation"] == 2)
check("B21. Baby3 族谱 parents 非空", tree["parents"] is not None)
parents_list = tree["parents"]
if parents_list:
    check("B22. Baby3 族谱 children", tree["children"] == [])

tree_agumon = lt.get_family_tree("Agumon")
check("B23. Agumon 族谱 generation = 0",
      tree_agumon["generation"] == 0)
check("B24. Agumon 族谱 descendants_count",
      tree_agumon["descendants_count"] == 3)  # Baby1, Baby2, Baby3

# Descendants
desc = lt.get_descendants("Agumon")
check("B25. Agumon 后代 = [Baby1, Baby2, Baby3]",
      sorted(desc) == ["Baby1", "Baby2", "Baby3"])

# Ancestors
anc = lt.get_ancestors("Baby3")
check("B26. Baby3 祖先非空", len(anc) > 0)
check("B27. Baby3 祖先含 Baby1", "Baby1" in anc)
check("B28. Baby3 祖先含 Baby2", "Baby2" in anc)

# Record query
check("B29. get_record(Baby1) 非空", lt.get_record("Baby1") is not None)
check("B30. get_record(Agumon) = None (始祖)",
      lt.get_record("Agumon") is None)

# Stats
stats = lt.stats()
check("B31. total_records = 3", stats["total_records"] == 3)
check("B32. total_generations >= 2", stats["total_generations"] >= 2)
check("B33. deepest_generation = 2", stats["deepest_generation"] == 2)
check("B34. most_children 是 Agumon", stats["most_children"] == "Agumon")
check("B35. most_children_count = 2", stats["most_children_count"] == 2)
check("B36. founders = [Agumon, Gabumon, Patamon]",
      stats["founders"] == ["Agumon", "Gabumon", "Patamon"])

# All records
all_recs = lt.all_records()
check("B37. all_records 长度 = 3", len(all_recs) == 3)

# Duplicate child
try:
    lt.register("Agumon", "Gabumon", "Baby1", 60, "Botamon")
    check("B38. 重复子代注册 → 应抛 ValueError", False)
except ValueError:
    check("B38. 重复子代注册 → 抛 ValueError", True)

# get_record on unknown
check("B39. get_record(Unknown) = None",
      lt.get_record("UnknownDigimon") is None)
check("B40. get_generation(Unknown) = None",
      lt.get_generation("UnknownDigimon") is None)
check("B41. get_children(Unknown) = []",
      lt.get_children("UnknownDigimon") == [])

# set_founder should not overwrite existing gen
lt.set_founder("Baby1")
check("B42. set_founder 不覆盖已有 generation",
      lt.get_generation("Baby1") == 1)

# ══════════════════════════════════════════════════════════════════════════
# Part C: EggState — 孵化状态
# ══════════════════════════════════════════════════════════════════════════
header("Part C: EggState")

egg = EggState(
    egg_id="egg_0_0001",
    parent_a="Agumon",
    parent_b="Gabumon",
    child_species="Botamon",
    tick_laid=10,
    incubation_ticks=200,
    season_at_laid="summer",
)
check("C1. EggState 创建成功", egg is not None)
check("C2. egg_id", egg.egg_id == "egg_0_0001")
check("C3. parent_a", egg.parent_a == "Agumon")
check("C4. parent_b", egg.parent_b == "Gabumon")
check("C5. child_species", egg.child_species == "Botamon")
check("C6. tick_laid", egg.tick_laid == 10)
check("C7. incubation_ticks", egg.incubation_ticks == 200)
check("C8. elapsed_ticks 默认 0", egg.elapsed_ticks == 0)
check("C9. hatch_progress 默认 0.0", egg.hatch_progress == 0.0)
check("C10. is_hatched() = False", not egg.is_hatched())
check("C11. ticks_remaining() = 200", egg.ticks_remaining() == 200)

# Advance
egg2 = egg.advance()
check("C12. advance → elapsed_ticks = 1", egg2.elapsed_ticks == 1)
check("C13. advance → hatch_progress > 0", egg2.hatch_progress > 0.0)

# Advance with warm season (summer → 1.3x speed)
egg3 = EggState(
    egg_id="egg_0_0002", parent_a="A", parent_b="B",
    child_species="X", tick_laid=0, incubation_ticks=100,
)
for _ in range(50):
    egg3 = egg3.advance(current_season="summer")
check("C14. 温暖季节加速 → 50 tick 进度 > 50%",
      egg3.hatch_progress > 0.5)

# Advance with cold season (winter → 0.7x)
egg4 = EggState(
    egg_id="egg_0_0003", parent_a="A", parent_b="B",
    child_species="X", tick_laid=0, incubation_ticks=100,
)
for _ in range(50):
    egg4 = egg4.advance(current_season="winter")
check("C15. 寒冷季节减速 → 50 tick 进度 < 夏季同 tick 进度",
      egg4.hatch_progress < egg3.hatch_progress)

# Full hatch
egg5 = EggState(
    egg_id="egg_0_0004", parent_a="A", parent_b="B",
    child_species="X", tick_laid=0, incubation_ticks=10,
)
for _ in range(15):
    egg5 = egg5.advance()
check("C16. 孵化完成 → is_hatched() = True", egg5.is_hatched())
check("C17. 孵化完成 → hatch_progress >= 1.0", egg5.hatch_progress >= 1.0)
check("C18. 孵化完成 → ticks_remaining = 0", egg5.ticks_remaining() == 0)

# Already hatched → no change
egg5b = egg5.advance()
check("C19. 已孵化 → advance 不变", egg5b.elapsed_ticks == egg5.elapsed_ticks)

# Zero incubation_ticks → instant hatch
egg6 = EggState(
    egg_id="egg_0_0005", parent_a="A", parent_b="B",
    child_species="X", tick_laid=0, incubation_ticks=0,
)
egg6a = egg6.advance()
check("C20. incubation_ticks=0 → 1 tick 后 is_hatched",
      egg6a.is_hatched())
check("C21. incubation_ticks=0 → hatch_progress = 1.0",
      egg6a.hatch_progress == 1.0)

# to_dict
ed = egg.to_dict()
check("C22. to_dict() 含 egg_id", ed["egg_id"] == "egg_0_0001")
check("C23. to_dict() 含 is_hatched", "is_hatched" in ed)
check("C24. to_dict() 含 ticks_remaining", "ticks_remaining" in ed)
check("C25. to_dict() 含 season_at_laid", ed.get("season_at_laid") == "summer")

# Frozen
try:
    egg.elapsed_ticks = 99  # type: ignore[misc]
    check("C26. EggState 不可变 (frozen)", False)
except FrozenInstanceError:
    check("C26. EggState 不可变 (frozen)", True)

# ══════════════════════════════════════════════════════════════════════════
# Part D: Hatchery — 孵化管理器
# ══════════════════════════════════════════════════════════════════════════
header("Part D: Hatchery")

reset_hatchery()
hatch = get_hatchery()

# lay_egg
egg_d1 = hatch.lay_egg(
    parent_a="Agumon",
    parent_b="Gabumon",
    child_species="Botamon",
    tick=100,
    incubation_ticks=150,
    season="summer",
)
check("D1. lay_egg 返回 EggState", egg_d1 is not None)
check("D2. egg_id 格式正确", egg_d1.egg_id.startswith("egg_100_"))
check("D3. incubation_ticks = 150", egg_d1.incubation_ticks == 150)
check("D4. season_at_laid = summer", egg_d1.season_at_laid == "summer")

# Auto-random incubation_ticks
egg_d2 = hatch.lay_egg(
    parent_a="Patamon", parent_b="Gatomon",
    child_species="Salamon", tick=110, season="winter",
)
check("D5. 随机孵化时长 >= MIN", egg_d2.incubation_ticks >= MIN_INCUBATION_TICKS)
check("D6. 随机孵化时长 <= MAX", egg_d2.incubation_ticks <= MAX_INCUBATION_TICKS)

# Query
check("D7. get_egg 查找到 egg_d1", hatch.get_egg(egg_d1.egg_id) is not None)
check("D8. all_eggs = 2", len(hatch.all_eggs()) == 2)
check("D9. incubating_eggs = 2", len(hatch.incubating_eggs()) == 2)

# eggs_from_parent
eggs_agumon = hatch.eggs_from_parent("Agumon")
check("D10. Agumon 的蛋 = 1", len(eggs_agumon) == 1)
check("D10b. Agumon 的蛋是 egg_d1", eggs_agumon[0].egg_id == egg_d1.egg_id)

eggs_none = hatch.eggs_from_parent("UnknownDigi")
check("D11. UnknownDigi 的蛋 = []", eggs_none == [])

# Tick: advance all
for _ in range(150):
    hatch.tick(current_tick=250, season="summer")
hatched_egg = hatch.get_egg(egg_d1.egg_id)
check("D12. 150 tick 后 egg_d1 已孵化",
      hatched_egg is not None and hatched_egg.is_hatched())

hatched = hatch.hatched_results()
check("D13. hatched_results 至少有 1 条", len(hatched) >= 1)

# Stats
h_stats = hatch.stats()
check("D14. stats.total_eggs_laid = 2", h_stats["total_eggs_laid"] == 2)
check("D15. stats.incubating 合理", h_stats["incubating"] + h_stats["hatched"] == h_stats["total_eggs_laid"])
check("D16. stats.avg_incubation_ticks >= 0", h_stats["avg_incubation_ticks"] >= 0)
check("D17. stats.progress_distribution 有 4 桶", len(h_stats["progress_distribution"]) == 4)

# HatchResult
if hatched:
    hr = hatched[0]
    check("D18. HatchResult.egg_id 非空", hr.egg_id != "")
    check("D19. HatchResult.parent_a = Agumon", hr.parent_a == "Agumon")
    check("D20. HatchResult.parent_b = Gabumon", hr.parent_b == "Gabumon")
    check("D21. HatchResult.child_species = Botamon", hr.child_species == "Botamon")
    check("D22. HatchResult.tick_hatched > 0", hr.tick_hatched > 0)
    hrd = hr.to_dict()
    check("D23. HatchResult.to_dict() 含 egg_id", "egg_id" in hrd)
    check("D24. HatchResult.to_dict() 含 parent_a", "parent_a" in hrd)
    check("D25. HatchResult.to_dict() 含 tick_hatched", "tick_hatched" in hrd)

# Empty hatchery
reset_hatchery()
hatch2 = get_hatchery()
check("D26. 重置后 incubating_eggs = 0", len(hatch2.incubating_eggs()) == 0)
check("D27. 重置后 hatched_results = 0", len(hatch2.hatched_results()) == 0)
check("D28. 重置后 stats 归零", hatch2.stats()["total_eggs_laid"] == 0)

# ══════════════════════════════════════════════════════════════════════════
# Part E: _season_modifier
# ══════════════════════════════════════════════════════════════════════════
header("Part E: _season_modifier")

check("E1. summer → >1 (加速)", _season_modifier("summer") > 1.0)
check("E2. spring → >1 (加速)", _season_modifier("spring") > 1.0)
check("E3. winter → <1 (减速)", _season_modifier("winter") < 1.0)
check("E4. autumn → <1 (减速)", _season_modifier("autumn") < 1.0)
check("E5. fall → <1 (减速)", _season_modifier("fall") < 1.0)
check("E6. None → 1.0 (中性)", _season_modifier(None) == 1.0)
check("E7. 未知季节 → 1.0", _season_modifier("monsoon") == 1.0)
check("E8. 大写 SUMMER → lower() 后识别为 warm", _season_modifier("SUMMER") > 1.0)

# ══════════════════════════════════════════════════════════════════════════
# Part F: InheritanceEngine — 特质遗传
# ══════════════════════════════════════════════════════════════════════════
header("Part F: InheritanceEngine")

eng = InheritanceEngine(rng=random.Random(42), strength=0.6, jitter=0.15, mutation_chance=0.0)

# Scalar inheritance
val = eng._inherit_scalar(0.3, 0.7)
check("F1. _inherit_scalar 在 [0,1]", 0.0 <= val <= 1.0)
check("F2. _inherit_scalar 接近 midpoint=0.5", abs(val - 0.5) < 0.3,
      f"got {val:.3f}")

# Personality inheritance
pers_a = {"E/I": 0.2, "S/N": 0.8, "T/F": 0.5, "J/P": 0.3}
pers_b = {"E/I": 0.6, "S/N": 0.4, "T/F": 0.5, "J/P": 0.7}
child_pers = eng.inherit_personality(pers_a, pers_b)
check("F3. 人格继承含 E/I", "E/I" in child_pers)
check("F4. 人格继承含所有 4 维", len(child_pers) >= 4)
check("F5. 人格值全在 [0,1]", all(0 <= v <= 1 for v in child_pers.values()))

# Knowledge affinity
know_a = {"combat": 0.9, "healing": 0.2}
know_b = {"combat": 0.8, "exploration": 0.7}
child_know = eng.inherit_knowledge_affinity(know_a, know_b)
check("F6. 知识继承含 combat", "combat" in child_know)
check("F7. 知识继承含 exploration", "exploration" in child_know)
check("F8. 知识继承含 healing", "healing" in child_know)
check("F9. 双亲高亲和力加成 (combat > midpoint)",
      child_know["combat"] > 0.85,
      f"got {child_know['combat']:.3f}")

# Crest affinity
crest_a = {"courage": 0.9, "love": 0.3}
crest_b = {"courage": 0.7, "friendship": 0.8}
child_crest = eng.inherit_crest_affinity(crest_a, crest_b)
check("F10. 徽章继承含 courage", "courage" in child_crest)
check("F11. 徽章继承含 love", "love" in child_crest)
check("F12. 徽章继承含 friendship", "friendship" in child_crest)

# Attribute bias
attr_child = eng.inherit_attribute_bias("vaccine", "data")
check("F13. 属性偏向 vaccine key", "vaccine" in attr_child)
check("F14. 属性偏向 data key", "data" in attr_child)
check("F15. 属性偏向值和 ≈ 1.0", abs(sum(attr_child.values()) - 1.0) < 0.01)

# Same attribute parents
attr_same = eng.inherit_attribute_bias("virus", "virus")
check("F16. 同属性 → 仅 1 key", len(attr_same) == 1)
check("F17. 同属性 → 归一化仍 = 1",
      abs(attr_same.get("virus", 0) - 1.0) < 0.01)

# compute_all
traits = eng.compute_all(
    personality_a=pers_a, personality_b=pers_b,
    knowledge_a=know_a, knowledge_b=know_b,
    crests_a=crest_a, crests_b=crest_b,
    attr_a="vaccine", attr_b="data",
)
check("F18. compute_all 返回 InheritedTraits", isinstance(traits, InheritedTraits))
check("F19. InheritedTraits.personality_vector",
      len(traits.personality_vector) >= 4)
check("F20. InheritedTraits.knowledge_affinity",
      len(traits.knowledge_affinity) >= 3)
check("F21. InheritedTraits.crest_affinity",
      len(traits.crest_affinity) >= 3)
check("F22. InheritedTraits.attribute_bias",
      len(traits.attribute_bias) >= 1)

# to_dict
td = traits.to_dict()
check("F23. traits.to_dict() 含 personality_vector",
      "personality_vector" in td)
check("F24. traits.to_dict() 含 knowledge_affinity",
      "knowledge_affinity" in td)
check("F25. traits.to_dict() 含 crest_affinity",
      "crest_affinity" in td)
check("F26. traits.to_dict() 含 attribute_bias",
      "attribute_bias" in td)

# Mutation test
eng_mut = InheritanceEngine(rng=random.Random(7), mutation_chance=1.0)
child_mut = eng_mut.inherit_personality(
    {"E/I": 0.9}, {"E/I": 0.1},
)
check("F27. mutation_chance=1.0 → 值可能突变",
      child_mut.get("E/I", 0.5) != 0.5,  # likely not the midpoint
      f"got {child_mut.get('E/I', 0.5):.3f}")

# Zero-strength (pure jitter)
eng_zero = InheritanceEngine(rng=random.Random(42), strength=0.0, jitter=0.3, mutation_chance=0.0)
zero_val = eng_zero._inherit_scalar(0.9, 0.9)
check("F28. strength=0 → midpoint (0.9,0.9) 加 jitter",
      zero_val < 0.9, f"got {zero_val:.3f}")

# Full-strength (midpoint exact)
eng_full = InheritanceEngine(rng=random.Random(42), strength=1.0, jitter=0.0, mutation_chance=0.0)
full_val = eng_full._inherit_scalar(0.3, 0.7)
check("F29. strength=1, jitter=0 → 精确 midpoint",
      abs(full_val - 0.5) < 0.01, f"got {full_val:.3f}")

# Empty dicts
eng_empty = InheritanceEngine(rng=random.Random(42))
empty_pers = eng_empty.inherit_personality({}, {})
check("F30. 空人格输入 → 空输出", empty_pers == {})

# ══════════════════════════════════════════════════════════════════════════
# Part G: API 端点结构验证
# ══════════════════════════════════════════════════════════════════════════
header("Part G: API 端点")

try:
    from digimon_world.api.lineage import router as lineage_router

    check("G1. lineage router 导入成功", True)
    check("G2. router 是 APIRouter", hasattr(lineage_router, "routes"))
    check("G3. router prefix = /api/lineage",
          lineage_router.prefix == "/api/lineage")

    route_paths = []
    for r in lineage_router.routes:
        p = getattr(r, "path", "")
        if p:
            route_paths.append(p)
    check("G4. lineage 路由数 = 3", len(route_paths) == 3,
          f"paths={route_paths}")
    check("G5. 有 /stats 路由",
          "/api/lineage/stats" in route_paths, f"paths={route_paths}")
    check("G6. 有 /tree 路由",
          "/api/lineage/tree" in route_paths, f"paths={route_paths}")
    check("G7. 有 /{name} 参数路由",
          "/api/lineage/{name}" in route_paths, f"paths={route_paths}")

except ImportError as e:
    check("G. API 模块导入失败", False, str(e))
except Exception as e:
    check(f"G. API 测试异常: {type(e).__name__}", False, str(e)[:80])

# ══════════════════════════════════════════════════════════════════════════
# Part H: 集成 — lineage + hatchery + inheritance 全生命周期
# ══════════════════════════════════════════════════════════════════════════
header("Part H: 集成 — 全生命周期")

reset_lineage_tracker()
reset_hatchery()

lt2 = get_lineage_tracker()
hatch_h = get_hatchery()
eng_h = InheritanceEngine(rng=random.Random(42))

# Step 1: 始祖
lt2.set_founders(["Agumon", "Gabumon"])
check("H1. 2 始祖设置", len(lt2.stats()["founders"]) == 2)

# Step 2: 产蛋
egg_h1 = hatch_h.lay_egg(
    parent_a="Agumon",
    parent_b="Gabumon",
    child_species="Botamon",
    tick=200,
    incubation_ticks=20,
    season="summer",
)
check("H2. 产蛋成功", egg_h1 is not None)

# Step 3: 孵化
hatched_h = []
for t in range(25):
    hatched_h += hatch_h.tick(current_tick=200 + t, season="summer")
check("H3. 25 tick 后孵化完成", len(hatched_h) >= 1)

# Step 4: 注册亲子关系
if hatched_h:
    hr_h = hatched_h[0]
    rec_h = lt2.register(
        parent_a=hr_h.parent_a,
        parent_b=hr_h.parent_b,
        child=hr_h.child_species,  # child name = species in this simple case
        tick_born=hr_h.tick_hatched,
        child_species=hr_h.child_species,
    )
    check("H4. 孵化→注册亲子记录", rec_h is not None)
    check("H5. 子代 generation = 1", rec_h.generation == 1)

# Step 5: 遗传
child_traits = eng_h.compute_all(
    personality_a={"E/I": 0.3, "S/N": 0.7, "T/F": 0.6, "J/P": 0.4},
    personality_b={"E/I": 0.7, "S/N": 0.3, "T/F": 0.4, "J/P": 0.6},
    knowledge_a={"combat": 0.9},
    knowledge_b={"combat": 0.1},
    crests_a={"courage": 0.8},
    crests_b={},
    attr_a="vaccine",
    attr_b="data",
)
check("H6. 遗传计算完成", child_traits is not None)
check("H7. 子代人格 vector 含 4 维", len(child_traits.personality_vector) >= 4)
check("H8. 子代知识含 combat", "combat" in child_traits.knowledge_affinity)
check("H9. 子代徽章含 courage", "courage" in child_traits.crest_affinity)

# Step 6: lineage stats after full cycle
stats_h = lt2.stats()
check("H10. 集成后 total_records >= 1", stats_h["total_records"] >= 1)

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
print(f"\n{'='*64}")
print(f"  📊 结果: {_PASS}/{_CHECK} PASS ({_FAIL} FAIL)")
print(f"{'='*64}")

sys.exit(0 if _FAIL == 0 else 1)

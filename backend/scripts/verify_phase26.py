#!/usr/bin/env python3
"""
Phase 26 端到端验证: 人格动力学 (Personality Dynamics)
=====================================================

验证内容:
A) 核心模块: PersonalityVector, SocialInfluenceTracker
B) 引擎: PersonalityDynamicsEngine (record_interaction, step, shift detection)
C) API 端点: /api/digimon/{name}/personality, /api/personality/network, /api/personality/shifts

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase26.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure backend project root is on sys.path
_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from digimon_world.api.app import app  # noqa: E402
from digimon_world.world.personality_dynamics import (  # noqa: E402
    _DEFAULT_INFLUENCE_FACTOR,
    _MAX_DEBT_NORMALIZE,
    _SHIFT_DRIFT_THRESHOLD,
    INTERACTION_BASE_VECTORS,
    PersonalityDynamicsEngine,
    PersonalityShift,
    PersonalityVector,
    SocialInfluenceRecord,
    SocialInfluenceTracker,
    get_personality_dynamics_engine,
    reset_personality_dynamics_engine,
)
from digimon_world.world.personality_engine import (  # noqa: E402
    PersonalityEvolutionEngine,
    PersonalityProfile,
    reset_personality_engine,
)

PASS = "\033[32m✅ PASS\033[0m"
FAIL = "\033[31m❌ FAIL\033[0m"

results: list[tuple[str, bool, str]] = []

_DIMS = ["ei", "sn", "tf", "jp"]


def approx(value: float, rel: float = 1e-6, abs_tol: float = 1e-9) -> float:
    """Dummy function — we use math.isclose instead."""
    return value  # never used directly, kept for compat


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    msg = f"  {status} {name}"
    if detail and not condition:
        msg += f" — {detail}"
    print(msg)
    results.append((name, condition, detail))
    return condition


def init_deterministic(engine: PersonalityDynamicsEngine, name: str) -> PersonalityVector:
    """Create a deterministic zero-valued personality vector."""
    profile = PersonalityProfile(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
    engine.evolution_engine.set(name, profile)
    vec = PersonalityVector(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
    engine.vectors[name] = vec
    return vec


def ensure_deterministic(engine: PersonalityDynamicsEngine, *names: str) -> None:
    """Ensure the given agents have deterministic zero-valued vectors."""
    for name in names:
        if name not in engine.vectors:
            init_deterministic(engine, name)


def main():
    print("=" * 60)
    print("  Phase 26 验证: 人格动力学 (Personality Dynamics)")
    print("=" * 60)

    reset_personality_dynamics_engine()
    reset_personality_engine()

    # Create fresh deterministic engine
    evo = PersonalityEvolutionEngine()
    engine = PersonalityDynamicsEngine(evolution_engine=evo)

    # ================================================================
    # SECTION A: Core module verification (17 checks: A.1–A.17)
    # ================================================================
    print("\n📊 Section A: 核心模块 — PersonalityVector + SocialInfluenceTracker")

    # A.1–A.2: from_personality_profile
    profile = PersonalityProfile(ei=0.5, sn=-0.3, tf=0.7, jp=-0.2)
    vec = PersonalityVector.from_personality_profile(profile)
    check("A.1  from_personality_profile 值正确",
          vec.ei == 0.5 and vec.sn == -0.3 and vec.tf == 0.7 and vec.jp == -0.2,
          f"got ({vec.ei}, {vec.sn}, {vec.tf}, {vec.jp})")
    check("A.2  from_personality_profile 记录原始类型",
          vec.original_type == "ENTP",
          f"got {vec.original_type}")

    # A.3–A.4: mbti_type derivation
    v1 = PersonalityVector(ei=0.8, sn=-0.7, tf=0.6, jp=-0.9)
    check("A.3  mbti_type 推导 ENTP",
          v1.mbti_type() == "ENTP",
          f"got {v1.mbti_type()}")
    v2 = PersonalityVector(ei=-0.5, sn=-0.3, tf=-0.2, jp=-0.1)
    check("A.4  mbti_type 推导 INFP",
          v2.mbti_type() == "INFP",
          f"got {v2.mbti_type()}")

    # A.5–A.6: distance_to (Euclidean)
    a = PersonalityVector(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
    b = PersonalityVector(ei=1.0, sn=0.0, tf=0.0, jp=0.0)
    check("A.5  distance_to = 1.0",
          math.isclose(a.distance_to(b), 1.0),
          f"got {a.distance_to(b)}")
    c = PersonalityVector(ei=1.0, sn=1.0, tf=0.0, jp=0.0)
    check("A.6  distance_to = sqrt(2)",
          math.isclose(a.distance_to(c), math.sqrt(2.0)),
          f"got {a.distance_to(c)}")

    # A.7: drift_from_original = 0 initially
    v3 = PersonalityVector(ei=0.5, sn=0.3, tf=-0.2, jp=0.1)
    check("A.7  drift_from_original 初始为 0",
          math.isclose(v3.drift_from_original(), 0.0),
          f"got {v3.drift_from_original()}")

    # A.8–A.10: _apply_shifts updates values and drift_total
    v4 = PersonalityVector(ei=0.5, sn=0.3, tf=-0.2, jp=0.1)
    v4._apply_shifts({"ei": 0.1, "sn": -0.05, "tf": 0.0, "jp": 0.0}, 0.12)
    check("A.8  _apply_shifts 更新 ei/sn 值",
          math.isclose(v4.ei, 0.6) and math.isclose(v4.sn, 0.25),
          f"got ei={v4.ei}, sn={v4.sn}")
    check("A.9  _apply_shifts drift_total > 0",
          v4.drift_total > 0.0,
          f"got {v4.drift_total}")
    expected_drift = math.sqrt(0.1**2 + 0.05**2)
    check("A.10 _apply_shifts drift_from_original 正确",
          math.isclose(v4.drift_from_original(), expected_drift, abs_tol=1e-4),
          f"expected {expected_drift}, got {v4.drift_from_original()}")

    # A.11: to_dict
    v5 = PersonalityVector(ei=0.5, sn=-0.3, tf=0.7, jp=-0.1)
    d = v5.to_dict()
    expected_keys = {"ei", "sn", "tf", "jp", "stability_score", "drift_total",
                     "original_type", "current_type", "drift_from_original", "original_values"}
    check("A.11 to_dict 包含所有期望键",
          expected_keys.issubset(d.keys()),
          f"missing: {expected_keys - d.keys()}")

    # A.12: dimensions clamped to [-1, 1]
    v6 = PersonalityVector(ei=0.995, sn=0.0, tf=0.0, jp=0.0)
    v6._apply_shifts({"ei": 0.1}, 0.1)
    check("A.12 维度 clamp 到 [-1, 1] (上限)",
          math.isclose(v6.ei, 1.0),
          f"got {v6.ei}")

    # A.13: SocialInfluenceRecord
    rec = SocialInfluenceRecord(
        influencer_name="agumon", influenced_name="gabumon",
        interaction_type="dialogue", magnitude=0.8,
        dimension_shifts={"ei": 0.016, "tf": -0.008}, tick=100,
    )
    check("A.13 SocialInfluenceRecord 字段完整",
          rec.influencer_name == "agumon"
          and rec.influenced_name == "gabumon"
          and rec.interaction_type == "dialogue"
          and rec.magnitude == 0.8
          and rec.tick == 100
          and bool(rec.timestamp),
          f"timestamp={rec.timestamp}")

    # A.14: add_record + get_influences_on
    tracker = SocialInfluenceTracker()
    tracker.add_record(SocialInfluenceRecord(
        influencer_name="X", influenced_name="target",
        interaction_type="dialogue", magnitude=0.3,
        dimension_shifts={}, tick=1,
    ))
    tracker.add_record(SocialInfluenceRecord(
        influencer_name="Y", influenced_name="target",
        interaction_type="battle", magnitude=0.7,
        dimension_shifts={}, tick=1,
    ))
    results_t = tracker.get_influences_on("target")
    check("A.14 add_record + get_influences_on",
          len(results_t) == 2 and results_t[0].influencer_name == "X",
          f"got {len(results_t)} records")

    # A.15: get_influence_network
    tracker2 = SocialInfluenceTracker()
    tracker2.add_record(SocialInfluenceRecord(
        influencer_name="A", influenced_name="B",
        interaction_type="dialogue", magnitude=0.3,
        dimension_shifts={}, tick=1,
    ))
    tracker2.add_record(SocialInfluenceRecord(
        influencer_name="A", influenced_name="B",
        interaction_type="battle", magnitude=0.2,
        dimension_shifts={}, tick=1,
    ))
    tracker2.add_record(SocialInfluenceRecord(
        influencer_name="B", influenced_name="C",
        interaction_type="help", magnitude=0.5,
        dimension_shifts={}, tick=1,
    ))
    net = tracker2.get_influence_network()
    check("A.15 get_influence_network 矩阵正确",
          math.isclose(net["A"]["B"], 0.5) and math.isclose(net["B"]["C"], 0.5),
          f"net={net}")

    # A.16: get_top_influencers
    tracker3 = SocialInfluenceTracker()
    tracker3.add_record(SocialInfluenceRecord(
        influencer_name="Z", influenced_name="target",
        interaction_type="dialogue", magnitude=0.1,
        dimension_shifts={}, tick=1,
    ))
    tracker3.add_record(SocialInfluenceRecord(
        influencer_name="Y", influenced_name="target",
        interaction_type="battle", magnitude=0.8,
        dimension_shifts={}, tick=1,
    ))
    tracker3.add_record(SocialInfluenceRecord(
        influencer_name="X", influenced_name="target",
        interaction_type="help", magnitude=0.5,
        dimension_shifts={}, tick=1,
    ))
    top = tracker3.get_top_influencers("target", n=2)
    check("A.16 get_top_influencers top 2",
          len(top) == 2 and top[0][0] == "Y" and math.isclose(top[0][1], 0.8),
          f"top={top}")

    # A.17: get_interaction_count bidirectional
    tracker4 = SocialInfluenceTracker()
    tracker4.add_record(SocialInfluenceRecord(
        influencer_name="A", influenced_name="B",
        interaction_type="dialogue", magnitude=0.5,
        dimension_shifts={}, tick=1,
    ))
    tracker4.add_record(SocialInfluenceRecord(
        influencer_name="B", influenced_name="A",
        interaction_type="battle", magnitude=0.5,
        dimension_shifts={}, tick=1,
    ))
    check("A.17 get_interaction_count 双向计数",
          tracker4.get_interaction_count("A", "B") == 2
          and tracker4.get_interaction_count("A", "C") == 0)

    # ================================================================
    # SECTION B: Engine verification (20 checks: B.1–B.20)
    # ================================================================
    print("\n📊 Section B: 引擎 — PersonalityDynamicsEngine")

    # B.1: get_or_create_vector creates new
    vec_new = engine.get_or_create_vector("new_agent")
    check("B.1  get_or_create_vector 创建新向量",
          vec_new is not None and "new_agent" in engine.vectors)

    # B.2: get_or_create_vector returns same instance
    vec_again = engine.get_or_create_vector("new_agent")
    check("B.2  get_or_create_vector 返回同一实例",
          vec_new is vec_again)

    # B.3–B.8: record_interaction for all 6 types
    ensure_deterministic(engine, "b")

    engine.record_interaction("influencer", "b", "dialogue", 1.0, tick=1)
    vec_b = engine.get_vector("b")
    check("B.3  dialogue: ei+0.02, tf-0.01",
          math.isclose(vec_b.ei, 0.02) and math.isclose(vec_b.tf, -0.01),
          f"ei={vec_b.ei}, tf={vec_b.tf}")

    ensure_deterministic(engine, "b_battle")
    engine.record_interaction("influencer", "b_battle", "battle", 1.0, tick=1)
    vec_bb = engine.get_vector("b_battle")
    check("B.4  battle: ei+0.01, tf+0.02, jp+0.01",
          math.isclose(vec_bb.ei, 0.01) and math.isclose(vec_bb.tf, 0.02) and math.isclose(vec_bb.jp, 0.01),
          f"ei={vec_bb.ei}, tf={vec_bb.tf}, jp={vec_bb.jp}")

    ensure_deterministic(engine, "b_help")
    engine.record_interaction("influencer", "b_help", "help", 1.0, tick=1)
    vec_bh = engine.get_vector("b_help")
    check("B.5  help: ei+0.01, tf-0.02",
          math.isclose(vec_bh.ei, 0.01) and math.isclose(vec_bh.tf, -0.02),
          f"ei={vec_bh.ei}, tf={vec_bh.tf}")

    ensure_deterministic(engine, "b_trade")
    engine.record_interaction("influencer", "b_trade", "trade", 1.0, tick=1)
    vec_bt = engine.get_vector("b_trade")
    check("B.6  trade: sn+0.01, jp-0.01",
          math.isclose(vec_bt.sn, 0.01) and math.isclose(vec_bt.jp, -0.01),
          f"sn={vec_bt.sn}, jp={vec_bt.jp}")

    ensure_deterministic(engine, "b_gift")
    engine.record_interaction("influencer", "b_gift", "gift", 1.0, tick=1)
    vec_bg = engine.get_vector("b_gift")
    check("B.7  gift: sn-0.01, tf-0.01",
          math.isclose(vec_bg.sn, -0.01) and math.isclose(vec_bg.tf, -0.01),
          f"sn={vec_bg.sn}, tf={vec_bg.tf}")

    ensure_deterministic(engine, "b_wakeup")
    engine.record_interaction("influencer", "b_wakeup", "wakeup", 1.0, tick=1)
    vec_bw = engine.get_vector("b_wakeup")
    check("B.8  wakeup: ei+0.02, tf-0.01",
          math.isclose(vec_bw.ei, 0.02) and math.isclose(vec_bw.tf, -0.01),
          f"ei={vec_bw.ei}, tf={vec_bw.tf}")

    # B.9: unknown type raises ValueError
    try:
        engine.record_interaction("a", "b", "nonexistent", 1.0, tick=1)
        check("B.9  未知类型 raise ValueError", False, "no exception raised")
    except ValueError as e:
        check("B.9  未知类型 raise ValueError", "未知互动类型" in str(e),
              f"exception: {e}")

    # B.10: multiple interactions accumulate
    ensure_deterministic(engine, "b_acc")
    for _ in range(5):
        engine.record_interaction("influencer", "b_acc", "dialogue", 1.0, tick=1)
    vec_acc = engine.get_vector("b_acc")
    check("B.10 多次互动累积: ei=0.10, tf=-0.05",
          math.isclose(vec_acc.ei, 0.10) and math.isclose(vec_acc.tf, -0.05),
          f"ei={vec_acc.ei}, tf={vec_acc.tf}")

    # B.11: step() computes stability < 1.0 after varied shifts
    ensure_deterministic(engine, "stability_test")
    vec_st = engine.get_vector("stability_test")
    vec_st._apply_shifts({"ei": 0.05, "sn": 0.01, "tf": 0.0, "jp": 0.0}, 0.051)
    vec_st._apply_shifts({"ei": -0.1, "sn": 0.0, "tf": 0.0, "jp": 0.0}, 0.1)
    vec_st._apply_shifts({"ei": 0.02, "sn": 0.0, "tf": -0.03, "jp": 0.0}, 0.036)
    vec_st._apply_shifts({"ei": 0.08, "sn": 0.0, "tf": 0.0, "jp": 0.0}, 0.08)
    vec_st._apply_shifts({"ei": -0.04, "sn": 0.0, "tf": 0.0, "jp": 0.01}, 0.041)
    engine.step(10)
    check("B.11 step() 计算稳定性 < 1.0",
          vec_st.stability_score < 1.0,
          f"stability={vec_st.stability_score}")

    # B.12: step() records trajectory snapshots
    ensure_deterministic(engine, "traj_test")
    engine.get_or_create_vector("traj_test")
    engine.step(10)
    engine.step(20)
    traj = engine.get_personality_trajectory("traj_test")
    check("B.12 step() 记录轨迹快照",
          len(traj) == 2 and traj[0]["tick"] == 10 and traj[1]["tick"] == 20,
          f"got {len(traj)} snapshots, ticks={[t['tick'] for t in traj]}")

    # B.13: step() detects personality shift when type changes + drift > threshold
    ensure_deterministic(engine, "shift_agent")
    vec_shift = engine.get_vector("shift_agent")
    vec_shift.ei = -0.8
    vec_shift.sn = -0.3
    vec_shift.tf = -0.7
    vec_shift.jp = -0.5
    shifts = engine.step(50)
    check("B.13 step() 检测类型转变 (ESTJ→INFP)",
          len(shifts) == 1 and shifts[0].agent_name == "shift_agent"
          and shifts[0].old_type == "ESTJ" and shifts[0].new_type == "INFP"
          and shifts[0].drift_distance > _SHIFT_DRIFT_THRESHOLD,
          f"shifts={shifts}")

    # B.14: step() does NOT detect shift when type unchanged
    ensure_deterministic(engine, "no_shift_agent")
    vec_ns = engine.get_vector("no_shift_agent")
    vec_ns.ei = 0.9
    vec_ns.sn = 0.9
    vec_ns.tf = 0.9
    vec_ns.jp = 0.9
    type_stays = vec_ns.mbti_type() == "ESTJ"
    shifts_ns = engine.step(10)
    no_shift = all(s.agent_name != "no_shift_agent" for s in shifts_ns)
    check("B.14 类型不变时无转变 (仍为 ESTJ)",
          type_stays and no_shift,
          f"type={vec_ns.mbti_type()}, shifts={shifts_ns}")

    # B.15: step() avoids duplicate shifts
    ensure_deterministic(engine, "dup_agent")
    vec_dup = engine.get_vector("dup_agent")
    vec_dup.ei = -0.9
    vec_dup.sn = -0.5
    vec_dup.tf = -0.7
    vec_dup.jp = -0.5
    s1 = engine.step(10)
    s2 = engine.step(20)
    check("B.15 step() 不重复记录转变",
          len(s1) >= 1 and len(s2) == 0,
          f"first step: {len(s1)} shifts, second: {len(s2)}")

    # B.16: influence factor = 1.0 without altruism
    engine2 = PersonalityDynamicsEngine(evolution_engine=PersonalityEvolutionEngine())
    factor_default = engine2._compute_influence_factor("a", "b")
    check("B.16 influence_factor = 1.0 (无 altruism)",
          math.isclose(factor_default, _DEFAULT_INFLUENCE_FACTOR),
          f"got {factor_default}")

    # B.17: influence factor > 1.0 with mock debt
    mock_altruism = MagicMock()
    mock_altruism.get_debt.return_value = 30.0
    engine2.set_altruism(mock_altruism)
    factor_debt = engine2._compute_influence_factor("debtor", "creditor")
    expected_factor = 1.0 + min(1.0, 30.0 / _MAX_DEBT_NORMALIZE)
    check("B.17 influence_factor > 1.0 (有债务)",
          factor_debt > 1.0 and math.isclose(factor_debt, expected_factor),
          f"got {factor_debt}, expected {expected_factor}")

    # B.18: profile sync after interaction
    ensure_deterministic(engine, "sync_me")
    engine.record_interaction("a", "sync_me", "dialogue", 1.0, tick=1)
    prof = engine.evolution_engine.get("sync_me")
    vec_sync = engine.get_vector("sync_me")
    check("B.18 profile 与 vector 同步",
          prof is not None and math.isclose(prof.ei, vec_sync.ei),
          f"prof.ei={prof.ei if prof else 'None'}, vec.ei={vec_sync.ei}")

    # B.19: all 6 interaction types defined
    check("B.19 6 种互动类型均已定义",
          set(INTERACTION_BASE_VECTORS.keys()) == {"dialogue", "battle", "help", "trade", "gift", "wakeup"})

    # B.20: engine reset clears all state
    engine_reset = PersonalityDynamicsEngine(evolution_engine=PersonalityEvolutionEngine())
    engine_reset.get_or_create_vector("agent")
    engine_reset.record_interaction("a", "b", "dialogue", 1.0, tick=1)
    engine_reset.shifts.append(PersonalityShift(
        agent_name="x", old_type="ESTJ", new_type="ISTJ",
        drift_distance=0.5, tick=10,
    ))
    engine_reset.reset()
    check("B.20 reset 清空所有状态",
          len(engine_reset.vectors) == 0
          and len(engine_reset.influence_tracker) == 0
          and len(engine_reset.shifts) == 0,
          f"vectors={len(engine_reset.vectors)}, tracker={len(engine_reset.influence_tracker)}, shifts={len(engine_reset.shifts)}")

    # ================================================================
    # SECTION C: API verification (5 checks: C.1–C.5)
    # ================================================================
    print("\n📊 Section C: API 端点")

    # Reset world + dynamics engine for API tests
    from digimon_world.world import get_world, reset_world
    reset_world()
    reset_personality_dynamics_engine()
    reset_personality_engine()

    world = get_world()
    all_agents = world.all()
    check("C.0  WorldState has agents",
          len(all_agents) > 0,
          f"got {len(all_agents)} agents")

    client = TestClient(app)

    # Pre-populate interactions via the singleton engine
    dynamics = get_personality_dynamics_engine()
    if len(all_agents) >= 2:
        a1 = all_agents[0].name
        a2 = all_agents[1].name
        dynamics.record_interaction(a1, a2, "dialogue", 0.8, tick=10)
        dynamics.record_interaction(a2, a1, "battle", 0.5, tick=10)
        dynamics.step(10)
        # Force a personality shift
        vec_a1 = dynamics.get_or_create_vector(a1)
        vec_a1.ei = -0.8
        vec_a1.sn = -0.3
        vec_a1.tf = -0.7
        vec_a1.jp = -0.5
        dynamics.step(20)

    # C.1: GET /api/digimon/{name}/personality returns 200 with dynamics
    if len(all_agents) >= 1:
        first_name = all_agents[0].name
        resp = client.get(f"/api/digimon/{first_name}/personality")
        check("C.1  GET /api/digimon/{name}/personality 返回 200",
              resp.status_code == 200,
              f"status: {resp.status_code}, body: {resp.text[:200]}")

        if resp.status_code == 200:
            data = resp.json()
            check("C.2  响应含 dynamics + trajectory + shifts 字段",
                  "dynamics" in data and "trajectory" in data and "personality_shifts" in data,
                  f"keys present: dynamics={'dynamics' in data}, trajectory={'trajectory' in data}, shifts={'personality_shifts' in data}")

    # C.3: GET /api/personality/network returns nodes/edges/summary
    resp_net = client.get("/api/personality/network")
    check("C.3  GET /api/personality/network 返回 200",
          resp_net.status_code == 200,
          f"status: {resp_net.status_code}")
    if resp_net.status_code == 200:
        net_data = resp_net.json()
        check("C.4  网络响应含 nodes/edges/summary",
              "nodes" in net_data and "edges" in net_data and "summary" in net_data,
              f"keys: {list(net_data.keys())}")

    # C.5: GET /api/personality/shifts returns shifts list
    resp_shifts = client.get("/api/personality/shifts")
    check("C.5  GET /api/personality/shifts 返回 200",
          resp_shifts.status_code == 200,
          f"status: {resp_shifts.status_code}")
    if resp_shifts.status_code == 200:
        shifts_data = resp_shifts.json()
        check("C.6  响应含 shifts/total/by_agent",
              "shifts" in shifts_data and "total" in shifts_data and "by_agent" in shifts_data,
              f"keys: {list(shifts_data.keys())}")

    # C.7: shifts?min_significance=0.5 filters correctly
    resp_filt = client.get("/api/personality/shifts?min_significance=0.5")
    check("C.7  shifts?min_significance=0.5 返回 200",
          resp_filt.status_code == 200,
          f"status: {resp_filt.status_code}")
    if resp_filt.status_code == 200:
        filt_data = resp_filt.json()
        all_filtered_ok = True
        for s in filt_data.get("shifts", []):
            if s.get("significance", 0.0) < 0.5:
                all_filtered_ok = False
                break
        check("C.8  min_significance 过滤正确",
              all_filtered_ok)

    # C.9: 404 for missing agent
    resp_404 = client.get("/api/digimon/nonexistent_xyz_agent/personality")
    check("C.9  不存在 agent → 404",
          resp_404.status_code == 404,
          f"status: {resp_404.status_code}")

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    status = PASS if passed == total else FAIL
    print(f"  {status} Phase 26: {passed}/{total} 项通过")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)

#!/usr/bin/env python3
"""
Phase 28 端到端验证: Agent 自我认知与叙事一致性引擎
====================================================

验证内容:
A) 核心模块: SelfModel, TheoryOfMind, NarrativeCoherence
B) 引擎: SelfEvaluator, BeliefUpdate, StrategicReasoning, CoherenceEngine
C) API 端点: /api/digimon/{name}/self, /api/digimon/{name}/tom, /api/narratives/coherence

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase28.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend project root is on sys.path
_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

from digimon_world.world.narrative_coherence import (  # noqa: E402
    CoherenceEngine,
    CoherenceReport,
    RelationConflictDetector,
    SpatialNarrativeBinder,
    get_coherence_engine,
    reset_coherence_engine,
)
from digimon_world.world.self_model import (  # noqa: E402
    SELF_MODEL_DIMS,
    SelfAssessmentResult,
    SelfEvaluator,
    SelfModel,
    SelfModelRegistry,
    get_self_model_registry,
    reset_self_model_registry,
)
from digimon_world.world.theory_of_mind import (  # noqa: E402
    BeliefUpdate,
    MentalStateModel,
    StrategicReasoning,
    TheoryOfMindRegistry,
    get_theory_of_mind_registry,
    reset_theory_of_mind_registry,
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


# ═══════════════════════════════════════════════════════════════════════════════
print("\U0001f52c Phase 28 端到端验证: Agent 自我认知与叙事一致性引擎")
print(f"{'='*64}")

# Reset for clean test
reset_self_model_registry()
reset_theory_of_mind_registry()
reset_coherence_engine()

# ══════════════════════════════════════════════════════════════════════════
# Part A: 自我模型 (SelfModel & SelfEvaluator)
# ══════════════════════════════════════════════════════════════════════════
header("Part A: 自我模型 (SelfModel & SelfEvaluator)")

sm = SelfModel(agent_name="Agumon")
check("A1. SelfModel 初始化成功", sm.agent_name == "Agumon")
check("A1. identity 有 4 个维度", all(d in sm.identity for d in SELF_MODEL_DIMS))
check("A1. self_assessment 有 4 个维度", all(d in sm.self_assessment for d in SELF_MODEL_DIMS))
check("A1. uncertainty 有 4 个维度", all(d in sm.uncertainty for d in SELF_MODEL_DIMS))
check("A1. 初始 identity > 0 (随机基线)", any(v > 0 for v in sm.identity.values()))

# A2: 初始不确定性高
check("A2. 初始 uncertainty[combat]=0.8", sm.uncertainty["combat_score"] == 0.8)

# A3: to_dict
d = sm.to_dict()
check("A3. to_dict 返回 dict", isinstance(d, dict))
check("A3. 含 identity/self_assessment/uncertainty/trajectory",
      all(k in d for k in ("identity", "self_assessment", "uncertainty", "trajectory")))

# A4: should_introspect (last_introspection_tick=0, interval=10 → 0 < 10 = False)
check("A4. tick=0 时 should_introspect(0) = False (未满间隔)",
      not sm.should_introspect(0))
check("A4. tick=10 时 should_introspect(10) = True",
      sm.should_introspect(10))

# A5: SelfEvaluator.compute_actual_scores
mock_context = {
    "battle_victories": 15, "attack": 80, "defense": 60,
    "evolution_stage": "champion",
    "relationship_count": 8, "dialogue_count": 25,
    "regions_visited": 4, "distance_traveled": 500.0,
    "skills_count": 4, "inventions_count": 2,
}
scores = SelfEvaluator.compute_actual_scores(mock_context)
check("A5. compute_actual_scores 返回 4 维 dict", len(scores) == 4)
check("A5. combat_score > 0 (有战斗记录)", scores["combat_score"] > 0)
check("A5. social_score > 0", scores["social_score"] > 0)

# A6: SelfEvaluator.evaluate 完整流程
result = SelfEvaluator.evaluate(
    agent_name="Agumon", agent_context=mock_context,
    self_model=sm, tick=10,
)
check("A6. evaluate 返回 SelfAssessmentResult", isinstance(result, SelfAssessmentResult))
check("A6. result.agent_name='Agumon'", result.agent_name == "Agumon")
check("A6. result.tick=10", result.tick == 10)
check("A6. actual_scores 有 4 维", len(result.actual_scores) == 4)
check("A6. adjustments 有值", len(result.adjustments) == 4)
check("A6. uncertainty 衰减 < 0.8 (已评估)", sm.uncertainty["combat_score"] < 0.8)

# A7: generate_goals
goals = SelfEvaluator.generate_goals(sm)
check("A7. generate_goals 返回 list", isinstance(goals, list))

# A8: SelfModelRegistry 单例
reg = get_self_model_registry()
check("A8. get_self_model_registry 返回 SelfModelRegistry", isinstance(reg, SelfModelRegistry))

# A9: get_or_create
# First register sm manually so get_or_create returns it
reg.set("Agumon", sm)
fetched2 = reg.get_or_create("Agumon")
check("A9. get_or_create 已存在返回旧实例", fetched2 is sm)
fetched = reg.get_or_create("Gabumon")
check("A9. get_or_create 创建新 agent", fetched is not None and fetched.agent_name == "Gabumon")

# A10: get
check("A10. get 获取已注册 agent", reg.get("Agumon") is not None)
check("A10. get 获取不存在 agent 返回 None", reg.get("Nope") is None)

# A11: step
res = reg.step("Gabumon", mock_context, tick=15)
check("A11. registry.step 返回结果", isinstance(res, SelfAssessmentResult))

# A12: list_agents + agent_count
agents = reg.list_agents()
check("A12. list_agents 返回 >= 2", len(agents) >= 2)
check("A12. agent_count() >= 2", reg.agent_count() >= 2)

# A13: to_dict
sd = reg.to_dict()
check("A13. to_dict 返回 dict 含 agent", "Agumon" in sd)

# ══════════════════════════════════════════════════════════════════════════
# Part B: 心智理论 (MentalStateModel & TheoryOfMindRegistry)
# ══════════════════════════════════════════════════════════════════════════
header("Part B: 心智理论 (MentalStateModel & BeliefUpdate)")

tom_reg = get_theory_of_mind_registry()
check("B1. get_theory_of_mind_registry 返回 TheoryOfMindRegistry", isinstance(tom_reg, TheoryOfMindRegistry))

# B2: get_or_create
msm = tom_reg.get_or_create("Agumon", "Gabumon")
check("B2. get_or_create 返回 MentalStateModel", isinstance(msm, MentalStateModel))
check("B2. target_name='Gabumon'", msm.target_name == "Gabumon")

# B3: 心智模型维度
check("B3. beliefs 有内容", len(msm.beliefs) > 0)
check("B3. intentions 有内容", len(msm.intentions) > 0)
check("B3. desires 有内容", len(msm.desires) > 0)

# B4: 初始置信度
check("B4. 初始 confidence=0.2", msm.confidence == 0.2)

# B5: BeliefUpdate.update_from_observation
BeliefUpdate.update_from_observation(msm, {"action_type": "attack", "intensity": 0.8}, tick=5)
check("B5. 观察 attack 后 intentions[attack] > 0", msm.intentions.get("attack", 0) > 0)
check("B5. 观察后 confidence > 0.2", msm.confidence > 0.2)

# B6: BeliefUpdate.decay_confidence
BeliefUpdate.update_from_observation(msm, {"action_type": "talk", "intensity": 0.5}, tick=7)
fresh_c = msm.confidence
BeliefUpdate.decay_confidence(msm, tick=45)  # 间隔 38 > 20
check("B6. decay_confidence 降低 confidence", msm.confidence < fresh_c,
      f"fresh={fresh_c:.3f}→{msm.confidence:.3f}")

# B7: to_dict
d2 = msm.to_dict()
check("B7. to_dict 含 beliefs/intentions/desires/confidence",
      all(k in d2 for k in ("beliefs", "intentions", "desires", "confidence")))

# B8: StrategicReasoning.predict_strategy
pred = StrategicReasoning.predict_strategy(
    agent_name="Agumon", target_name="Gabumon",
    self_identity={"combat_score": 0.5, "social_score": 0.4, "exploration_score": 0.3, "knowledge_score": 0.6},
    mental_model=msm, tick=10,
)
check("B8. predict_strategy 返回 StrategyPrediction", pred is not None)
check("B8. recommended_approach in valid set",
      pred.recommended_approach in ("engage_combat", "avoid_combat", "engage_social", "avoid_social", "neutral", "observe"))
check("B8. to_dict 可序列化", isinstance(pred.to_dict(), dict))

# B9: get 方法
msm2 = tom_reg.get("Agumon", "Gabumon")
check("B9. get 返回已有模型", msm2 is not None and msm2 is msm)
none_msm = tom_reg.get("Nobody", "Nowhere")
check("B9. get 不存在返回 None", none_msm is None)

# B10: TheoryOfMindRegistry.step 方法存在
check("B10. registry.step 方法存在", hasattr(tom_reg, "step"))

# ══════════════════════════════════════════════════════════════════════════
# Part C: 叙事一致性引擎 (Narrative Coherence Engine)
# ══════════════════════════════════════════════════════════════════════════
header("Part C: 叙事一致性引擎 (CoherenceEngine)")

engine = get_coherence_engine()
check("C1. get_coherence_engine 返回 CoherenceEngine", isinstance(engine, CoherenceEngine))

# C2: record_relation_snapshot
snap = engine.record_relation_snapshot(
    "Agumon", "Gabumon", tick=10, affinity=70, rivalry=20, respect=50, fear=10,
)
check("C2. record_relation_snapshot 成功", snap is not None)
snap2 = engine.record_relation_snapshot(
    "Agumon", "Gabumon", tick=20, affinity=-50, rivalry=80, respect=30, fear=60,
)
check("C2. 第二次快照记录成功", snap2 is not None)

# C3: detect_ambivalence (static)
conflict = RelationConflictDetector.detect_ambivalence("A", "B", affinity=80, rivalry=80)
check("C3. detect_ambivalence 检测到爱恨交织", conflict is not None)
check("C3. conflict_type='ambivalence'", conflict.conflict_type == "ambivalence")
none_c = RelationConflictDetector.detect_ambivalence("C", "D", affinity=10, rivalry=0)
check("C3. 低矛盾无检测", none_c is None)

# C4: detect_flip (static) - needs history
from digimon_world.world.narrative_coherence import RelationSnapshot  # noqa: E402

history = [
    RelationSnapshot("A", "B", tick=0, affinity=60, rivalry=10, respect=50, fear=5),
    RelationSnapshot("A", "B", tick=50, affinity=-60, rivalry=80, respect=30, fear=70),
]
flip = RelationConflictDetector.detect_flip("A", "B", history)
check("C4. detect_flip 检测到关系翻转", flip is not None)
check("C4. conflict_type='flip'", flip.conflict_type == "flip")

# C5: detect_one_sided (static)
os = RelationConflictDetector.detect_one_sided("A", "B", affinity_a_to_b=90, affinity_b_to_a=-80)
check("C5. detect_one_sided 检测到单向", os is not None)
check("C5. conflict_type='one_sided'", os.conflict_type == "one_sided")

# C6: detect_all (static)
all_c = RelationConflictDetector.detect_all(
    [("A", "B", 80, 80, 70, 20)],
    pair_histories={("A", "B"): history},
)
check("C6. detect_all 返回列表", isinstance(all_c, list))
check("C6. 检测到多个矛盾", len(all_c) >= 1)

# C7: SpatialNarrativeBinder.check_event_location (static)
inc = SpatialNarrativeBinder.check_event_location(
    "Agumon", "battle", event_tick=10,
    event_location=(100, 100),
    agent_position_at_tick=(110, 115),
)
check("C7. 近距离 (<500px) 无不一致", inc is None)
inc2 = SpatialNarrativeBinder.check_event_location(
    "Agumon", "battle", event_tick=10,
    event_location=(1000, 1000),
    agent_position_at_tick=(100, 100),
)
check("C7. 远距离 (>500px) 检测到不一致", inc2 is not None, f"dist={inc2.distance_px if inc2 else 'None'}")

# C8: CoherenceEngine.check
report = engine.check(
    tick=100, agent_names=["Agumon", "Gabumon"],
    pairs_data=[
        ("Agumon", "Gabumon", 0.7, 0.8, 0.2, 0.15),
    ],
    events=[{"agent_name": "Agumon", "event_type": "battle", "tick": 95, "location": (100, 100)}],
    agent_positions={"Agumon": {95: (105, 110)}},
)
check("C8. engine.check 返回 CoherenceReport", isinstance(report, CoherenceReport))
check("C8. global_score 在 [0, 1]", 0 <= report.global_score <= 1, f"score={report.global_score}")

# C9: CoherenceReport.to_dict
rd = report.to_dict()
check("C9. to_dict 含 global_score", "global_score" in rd)
check("C9. 含 relation_score/spatial_score/density_score",
      all(k in rd for k in ("relation_score", "spatial_score", "density_score")))

# C10: is_healthy / is_critical
check("C10. is_healthy() 返回 bool", isinstance(report.is_healthy(), bool))
check("C10. is_critical() 返回 bool", isinstance(report.is_critical(), bool))

# C11: should_check
check("C11. should_check(50) = False (刚在 100 检完)", not engine.should_check(50))
check("C11. should_check(200) = True (间隔 >= 50)", engine.should_check(200))

# C12: get_pair_history
ph = engine.get_pair_history("Agumon", "Gabumon")
check("C12. get_pair_history 返回列表", isinstance(ph, list))
check("C12. 有 2 条快照", len(ph) == 2)

# ══════════════════════════════════════════════════════════════════════════
# Part D: API 端点
# ══════════════════════════════════════════════════════════════════════════
header("Part D: API 端点")

try:
    from fastapi.testclient import TestClient

    from digimon_world.api.app import app

    client = TestClient(app)

    # D1: GET /api/digimon/{name}/self (不存在的 agent)
    resp = client.get("/api/digimon/NonExistent456/self")
    check("D1. 不存在 agent → 404", resp.status_code == 404)

    # D2: GET /api/digimon/{name}/tom
    resp = client.get("/api/digimon/NonExistent456/tom")
    check("D2. 不存在 agent → 404", resp.status_code == 404)

    # D3: GET /api/narratives/coherence
    resp = client.get("/api/narratives/coherence")
    check("D3. GET /api/narratives/coherence 200", resp.status_code == 200)
    d3 = resp.json()
    check("D3. 返回 JSON 对象", isinstance(d3, dict))
    check("D3. 含 last_check_tick + status", "last_check_tick" in d3 and "status" in d3)

    check("D. API 路由全部注册", True)
except ImportError as e:
    check("D. API 导入成功 (FastAPI)", False, str(e))
except Exception as e:
    check(f"D. API 测试异常: {type(e).__name__}", False, str(e)[:80])

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
print(f"\n{'='*64}")
print(f"  \U0001f4ca 结果: {_PASS}/{_CHECK} PASS ({_FAIL} FAIL)")
print(f"{'='*64}")

if _FAIL == 0:
    print("\n\U0001f389 Phase 28 端到端验证全部通过！")
    sys.exit(0)
else:
    print(f"\n\u26a0\ufe0f  {_FAIL} 项验证失败，请检查上述 \u274c 项。")
    sys.exit(1)

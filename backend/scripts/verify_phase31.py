#!/usr/bin/env python3
"""
Phase 31 端到端验证: 涌现验证与协作深度
========================================

验证内容:
A) 协作任务全生命周期 (创建→加入→贡献→完成→奖励)
B) 任务生成引擎 (随机生成/扫描)
C) 涌现耦合增益真实性 (genuine/neutral/suspected_noise)
D) 导演偏好反馈全生命周期 (记录→查询→prompt注入)
E) 集成: 协作+涌现+偏好完整生命周期

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase31.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from unittest.mock import MagicMock

_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

from digimon_world.world.cooperative_tasks import (  # noqa: E402
    TASK_TYPES,
    CooperativeTask,
    CooperativeTaskRegistry,
    TaskGenerationEngine,
    get_cooperative_registry,
    reset_cooperative_registry,
)
from digimon_world.world.director_preferences import (  # noqa: E402
    get_preference_store,
    reset_preference_store,
)
from digimon_world.world.emergence_metrics import (  # noqa: E402
    compute_coupling_gain,
)

_PASS, _FAIL, _CHECK = 0, 0, 0
MAX_LINE = 58


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
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ── Helpers ────────────────────────────────────────────────────────

def make_agent(name: str, energy: int = 100, loc: tuple = (0, 0),
               plan: str = "", mood: dict | None = None) -> MagicMock:
    """Create a mock agent with basic attributes."""
    a = MagicMock()
    a.name = name
    a.energy = energy
    a.location = loc
    a.current_plan = plan
    a.mood_state = mood or {"joy": 0.5, "fear": 0.1, "anger": 0.1, "sadness": 0.1}
    return a


class FakeRegion:
    def __init__(self, rid: str, name: str, bounds: tuple = (0, 0, 2000, 2000)):
        self.id = rid
        self.name = name
        self.bounds = bounds


class FakeWorld:
    def __init__(self, regions: dict | None = None):
        self.regions = regions or {}
        self._agents: list = []

    def all(self) -> list:
        return list(self._agents)

    def add_agent(self, agent) -> None:
        self._agents.append(agent)


# ══════════════════════════════════════════════════════════════════════════
# Part A: 协作任务全生命周期 — CooperativeTask + Registry
# ══════════════════════════════════════════════════════════════════════════
header("Part A: 协作任务全生命周期")

reset_cooperative_registry()
rng = random.Random(42)

# A1. 创建 Registry
registry = CooperativeTaskRegistry()
check("A1.  Registry创建", registry is not None)
check("A1b. 初始任务数=0", registry.task_count() == 0)

# A2. create_task — 所有四种类型
for tt in TASK_TYPES:
    task = registry.create_task(
        task_type=tt, title=f"{tt}测试", description="创建测试",
        required_participants=2, region_id="forest",
        position={"x": 100, "y": 200},
    )
    check(f"A2.  create_task({tt})", task is not None and task.task_type == tt)
    check(f"A2b. task_id前缀({tt})", task.task_id.startswith(f"coop_{tt}_"))

check("A2c. 总任务数=4", registry.task_count() == 4)

# A3. join_task — 加入+自动激活
t1 = registry.create_task("hunt", "狩猎魔狼", "组队猎杀", 3, "plains")
check("A3.  join(a)成功", registry.join_task(t1.task_id, "战士A"))
check("A3b. join(b)成功", registry.join_task(t1.task_id, "战士B"))
check("A3c. 未满人仍pending", t1.status == "pending")
check("A3d. join(c)成功→active", registry.join_task(t1.task_id, "战士C"))
check("A3e. 满人自动激活", t1.status == "active" and t1.is_fully_staffed())

# A4. 子目标分配
check("A4.  子目标已分配", len(t1.sub_goals) == 3)
check("A4b. 三人子目标不同", len(set(t1.sub_goals.values())) >= 2)

# A5. 贡献度
check("A5.  contribute(0.3)", registry.contribute(t1.task_id, "战士A", 0.3))
check("A5b. contribute(0.3)", registry.contribute(t1.task_id, "战士B", 0.3))
check("A5c. contribute(0.5)", registry.contribute(t1.task_id, "战士C", 0.5))
check("A5d. 总贡献=1.1", abs(t1.total_contribution() - 1.1) < 0.01)

# A6. 完成检测
result = registry.check_completion(t1.task_id)
check("A6.  任务完成", result["completed"])
check("A6b. status→completed", t1.status == "completed")
check("A6c. 奖励3人", len(result.get("rewards", {})) == 3)

# A7. 拒绝错误操作
type_err = False
try:
    registry.create_task("invalid", "x", "x", 2, "r")
except ValueError:
    type_err = True
check("A7.  无效类型→ValueError", type_err)

min_err = False
try:
    registry.create_task("explore", "x", "x", 1, "r")
except ValueError:
    min_err = True
check("A7b. 人数<2→ValueError", min_err)

check("A7c. 重复加入拒绝", not registry.join_task(t1.task_id, "战士A"))
check("A7d. 已完成任务拒绝join", not registry.join_task(t1.task_id, "新战士"))

# A8. 查询
check("A8.  get_active排除completed", t1 not in registry.get_active_tasks())
check("A8b. get_agent_tasks", len(registry.get_agent_tasks("战士A")) == 1)
check("A8c. get_tasks_by_region", len(registry.get_tasks_by_region("plains")) == 1)

# A9. to_dict
d = t1.to_dict()
check("A9.  to_dict含task_id", d["task_id"] == t1.task_id)
check("A9b. to_dict含participant_count", d["participant_count"] == 3)
check("A9c. to_dict含total_contribution", d["total_contribution"] > 1.0)


# ══════════════════════════════════════════════════════════════════════════
# Part B: 任务生成引擎 — TaskGenerationEngine
# ══════════════════════════════════════════════════════════════════════════
header("Part B: 任务生成引擎")

engine = TaskGenerationEngine(rng=rng)

world = FakeWorld({
    "forest": FakeRegion("forest", "森林区"),
    "plains": FakeRegion("plains", "平原区"),
    "spiral_mountain": FakeRegion("spiral_mountain", "螺旋山"),
})

agents = [make_agent(f"digi_{i}", energy=80 + i * 2, loc=(i * 50, i * 60)) for i in range(10)]
for a in agents:
    world.add_agent(a)

# B1. generate_random_task
task = engine.generate_random_task(world, agents, 300)
check("B1.  生成任务非空", task is not None)
if task:
    check("B1b. 参与者≥2", len(task.current_participants) >= 2)
    check("B1c. status=active", task.status == "active")
    check("B1d. 有子目标", len(task.sub_goals) >= 2)
    check("B1e. tick_created=300", task.tick_created == 300)

# B2. scan_for_opportunities
tasks = engine.scan_for_opportunities(world, agents, 400)
check("B2.  scan不崩溃", isinstance(tasks, list))

# B3. 多种任务类型
task_types_seen = set()
for _ in range(20):
    t = engine.generate_random_task(world, agents, 500)
    if t:
        task_types_seen.add(t.task_type)
check(f"B3.  覆盖≥2种类型(已见{len(task_types_seen)})", len(task_types_seen) >= 2)


# ══════════════════════════════════════════════════════════════════════════
# Part C: 涌现耦合增益真实性
# ══════════════════════════════════════════════════════════════════════════
header("Part C: 涌现耦合增益真实性验证")

# C1. <2 agent → insufficient_data
w1 = FakeWorld()
snap1 = compute_coupling_gain(w1)  # type: ignore[arg-type]
check("C1.  <2 agent→insufficient_data", snap1.verdict == "insufficient_data")
check("C1b. coupling_gain=0", snap1.coupling_gain == 0.0)
check("C1c. validity_score=0", snap1.validity_score == 0.0)

# C2. 分散agent → 低耦合
w2 = FakeWorld()
for i in range(6):
    ag = make_agent(f"a_{i}", loc=(i * 300, i * 250), plan="探索" if i < 3 else "休息")
    w2.add_agent(ag)
snap2 = compute_coupling_gain(w2)  # type: ignore[arg-type]
check("C2.  ≥5 agent→有判定", snap2.verdict != "insufficient_data",
      f"verdict={snap2.verdict}")
check("C2b. coupling_gain有值", snap2.coupling_gain > 0)
check("C2c. validity_score 0-100", 0 <= snap2.validity_score <= 100)
check("C2d. agent_count=6", snap2.agent_count == 6)

# C3. 高密集agent → 高耦合
w3 = FakeWorld()
for i in range(10):
    ag = make_agent(f"close_{i}", loc=(500 + i * 10, 500 + i * 10),
                    plan="共同守卫领地",
                    mood={"joy": 0.8, "fear": 0.05, "anger": 0.1, "sadness": 0.05})
    w3.add_agent(ag)
snap3 = compute_coupling_gain(w3)  # type: ignore[arg-type]
check("C3.  高耦合→genuine/neutral", snap3.verdict in ("genuine", "neutral"),
      f"verdict={snap3.verdict}, gain={snap3.coupling_gain:.3f}")
check("C3b. coupling_gain>0.5", snap3.coupling_gain > 0.5,
      f"gain={snap3.coupling_gain:.3f}")

# C4. to_dict
d = snap3.to_dict()
check("C4.  to_dict含coupling_gain", "coupling_gain" in d)
check("C4b. to_dict含verdict", "verdict" in d)
check("C4c. to_dict含validity_score", "validity_score" in d)


# ══════════════════════════════════════════════════════════════════════════
# Part D: 导演偏好反馈全生命周期
# ══════════════════════════════════════════════════════════════════════════
header("Part D: 导演偏好反馈系统")

reset_preference_store()
store = get_preference_store()
check("D1.  空store记录=0", store.count() == 0)

# D2. 记录偏好
rec1 = store.record("亚古兽", "like", "explore", context="探索精神好", tick=10)
check("D2.  record like", rec1 is not None and rec1.id == 1)
store.record("亚古兽", "like", "explore", tick=15)
store.record("亚古兽", "like", "explore", tick=20)
check("D2b. 累计3条like", len(store.get_for_agent("亚古兽")) == 3)

store.record("亚古兽", "avoid", "battle", context="不要无谓战斗", tick=25)
store.record("亚古兽", "avoid", "battle", tick=30)
store.record("亚古兽", "like", "social", tick=35)

# D3. get_for_agent
records = store.get_for_agent("亚古兽")
check("D3.  共6条", len(records) == 6)
check("D3b. ID升序", [r.id for r in records] == [1, 2, 3, 4, 5, 6])

# D4. get_prompt_hints
hints = store.get_prompt_hints("亚古兽")
check("D4.  hints非空", len(hints) > 0)
check("D4b. 含'导演偏好'", "导演偏好" in hints)
check("D4c. 含'探索(×3)'", "探索(×3)" in hints)
check("D4d. 含'战斗(×2)'", "战斗(×2)" in hints)
check("D4e. 含'社交'", "社交" in hints)
check("D4f. like在avoid前", hints.index("喜欢") < hints.index("避免"))

# D5. 多agent隔离
store.record("加布兽", "like", "social", tick=5)
hints_a = store.get_prompt_hints("亚古兽")
hints_b = store.get_prompt_hints("加布兽")
check("D5.  多agent隔离", "战斗" in hints_a and "战斗" not in hints_b)

# D6. 无偏好→空
check("D6.  无偏好→空", store.get_prompt_hints("不存在") == "")

# D7. 无效参数
try:
    store.record("a", "neutral", "explore")  # type: ignore[arg-type]
    check("D7.  无效preference→ValueError", False)
except ValueError:
    check("D7.  无效preference→ValueError", True)


# ══════════════════════════════════════════════════════════════════════════
# Part E: 集成 — 协作+涌现+偏好完整生命周期
# ══════════════════════════════════════════════════════════════════════════
header("Part E: 集成验证")

# E1. 协作创建+贡献+完成+偏好记录完整链
reset_cooperative_registry()
reset_preference_store()
reg = get_cooperative_registry()
ps = get_preference_store()

task_e = reg.create_task("explore", "探索迷雾森林", "联合调查", 3, "forest", {"x": 300, "y": 400})
check("E1.  集成任务创建", task_e is not None)
check("E1b. 初始0参与者", len(task_e.current_participants) == 0)

for name in ["亚古兽", "加布兽", "比丘兽"]:
    reg.join_task(task_e.task_id, name)
check("E1c. 3人加入→active", task_e.status == "active")
check("E1d. 子目标3人", len(task_e.sub_goals) == 3)

reg.contribute(task_e.task_id, "亚古兽", 0.4)
reg.contribute(task_e.task_id, "加布兽", 0.35)
reg.contribute(task_e.task_id, "比丘兽", 0.3)
result_e = reg.check_completion(task_e.task_id)
check("E1e. 集成任务完成", result_e["completed"])
check("E1f. 奖励3人", len(result_e.get("rewards", {})) == 3)

# 导演反馈
ps.record("亚古兽", "like", "explore", context="协作探索很出色", tick=100)
ps.record("加布兽", "like", "social", context="团队配合好", tick=100)
ps.record("比丘兽", "avoid", "flee", context="不应逃", tick=100)
h = ps.get_prompt_hints("亚古兽")
check("E1g. 导演反馈→prompt注入", "探索" in h and "导演偏好" in h)

# E2. 涌现验证 — 协作后聚集的agent耦合更高
w_check = FakeWorld()
for i in range(6):
    ag = make_agent(f"digi_{i}", loc=(300 + i * 10, 400 + i * 10),
                    plan="探索迷雾森林",
                    mood={"joy": 0.7, "fear": 0.1, "anger": 0.05, "sadness": 0.15})
    w_check.add_agent(ag)
for i in range(6, 10):
    ag = make_agent(f"digi_{i}", loc=(i * 350, i * 280),
                    plan="休息",
                    mood={"joy": 0.3, "fear": 0.2, "anger": 0.4, "sadness": 0.1})
    w_check.add_agent(ag)

snap = compute_coupling_gain(w_check)  # type: ignore[arg-type]
check("E2.  协作后耦合增益可计算", snap.coupling_gain > 0,
      f"gain={snap.coupling_gain:.3f}")
check("E2b. verdict有判定", snap.verdict != "insufficient_data")
check("E2c. validity_score 0-100", 0 <= snap.validity_score <= 100)

# E3. 全局单例一致性
reset_cooperative_registry()
reset_preference_store()
r1 = get_cooperative_registry()
r2 = get_cooperative_registry()
check("E3.  注册表单例一致", r1 is r2)

p1 = get_preference_store()
p2 = get_preference_store()
check("E3b. 偏好存储单例一致", p1 is p2)

# E4. add_task 用已完成任务验证
reset_cooperative_registry()
reg2 = get_cooperative_registry()
completed_task = CooperativeTask(
    task_id="done_1", task_type="build", title="已完成任务", description="已完成",
    required_participants=2, current_participants=["a", "b"],
    sub_goals={"a": "搬运", "b": "搭建"},
    individual_contributions={"a": 0.6, "b": 0.6},
    status="completed", tick_created=0, region_id="town",
    completion_threshold=1.0,
)
reg2.add_task(completed_task)
check("E4.  add_task正确索引", len(reg2.get_agent_tasks("a")) == 1)
check("E4b. 已完成不在活跃列", completed_task not in reg2.get_active_tasks())

# ══════════════════════════════════════════════════════════════════════════
# 结果汇总
# ══════════════════════════════════════════════════════════════════════════
header("结果汇总")

print(f"\n  通过: {_PASS} / 失败: {_FAIL} / 总计: {_CHECK}")
if _FAIL == 0:
    print("  \u2705 Phase 31 端到端验证全部通过！")
else:
    print(f"  \u274c Phase 31 端到端验证有 {_FAIL} 项失败")

sys.exit(0 if _FAIL == 0 else 1)

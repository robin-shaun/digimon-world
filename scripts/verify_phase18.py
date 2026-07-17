#!/usr/bin/env python3
"""Phase 18 端到端验证脚本

验证记忆自主规划系统完整链路:
1. 遗忘曲线数学正确性
2. 复述选策略
3. 过期检测模式匹配
4. Agent 集成 (register → step → diagnose)
5. API 端点可用性
"""

import asyncio
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

# ─── 路径设置 ───
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "src"))

from digimon_world.memory.memory_autonomy import (
    EbbinghausCurve,
    ForgettingEngine,
    MemoryAutonomy,
    MemoryHealth,
    MemoryRehearsal,
    MemoryUpdateDetector,
    FORGETTING_STRENGTH_DEFAULT,
    REHEARSAL_STRENGTH_THRESHOLD,
    MAX_REHEARSAL_PER_STEP,
)
from digimon_world.memory.memory_stream import MemoryNode


PASS = 0
FAIL = 0
SKIP = 0


def check(condition: bool, label: str) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}")


def skip_check(label: str) -> None:
    global SKIP
    SKIP += 1
    print(f"  ⏭️  {label} (backend not available)")


def make_memory(node_id: int, desc: str, importance: int = 5,
                created_at: datetime | None = None) -> MemoryNode:
    """创建测试用 MemoryNode。"""
    return MemoryNode(
        node_id=node_id,
        description=desc,
        importance=importance,
        timestamp=created_at or datetime.utcnow(),
        memory_type="test",
    )


# ═══════════════════════════════════════════════
# 第一组: 遗忘曲线数学
# ═══════════════════════════════════════════════
print("\n━━━ 第一组: Ebbinghaus 遗忘曲线 ━━━")

# 1.1 默认曲线
curve = EbbinghausCurve()
hl = curve.half_life_seconds()
expected_hl = FORGETTING_STRENGTH_DEFAULT * math.log(2)
check(abs(hl - expected_hl) < 0.01, f"半衰期正确: {hl:.1f}s ≈ {expected_hl:.1f}s (S={FORGETTING_STRENGTH_DEFAULT})")

# 1.2 初始强度
check(abs(curve.retention(0) - 1.0) < 1e-9, "t=0 时保留率 = 1.0")

# 1.3 半衰时强度
s_at_hl = curve.retention(hl)
check(abs(s_at_hl - 0.5) < 1e-6, f"t={hl:.1f}s 时保留率 = {s_at_hl:.6f} ≈ 0.5")

# 1.4 自定义 S
curve2 = EbbinghausCurve(S=7200.0)
hl2 = curve2.half_life_seconds()
check(abs(curve2.retention(hl2) - 0.5) < 1e-6, f"S=7200 半衰期={hl2:.1f}s, 保留率=0.5")

# 1.5 负时间
check(abs(curve.retention(-100) - 1.0) < 1e-9, "负时间返回 1.0")

# 1.6 个性曲线
brave_curve = EbbinghausCurve.for_agent("测试", "brave")
lazy_curve = EbbinghausCurve.for_agent("测试", "lazy")
check(brave_curve.half_life_seconds() > lazy_curve.half_life_seconds(),
      f"brave({brave_curve.half_life_seconds():.0f}s) > lazy({lazy_curve.half_life_seconds():.0f}s)")


# ═══════════════════════════════════════════════
# 第二组: ForgettingEngine
# ═══════════════════════════════════════════════
print("\n━━━ 第二组: ForgettingEngine ━━━")

engine = ForgettingEngine()

# 2.1 注册记忆
m1 = make_memory(1, "与亚古兽战斗并胜利", importance=9)
h1 = engine.register(m1)
check(h1.strength == 1.0, "新注册记忆 strength = 1.0")
check(h1.rehearsal_count == 0, "rehearsal_count = 0")
check(1 in engine.memory_health, "node_id=1 在 memory_health 中")

# 2.2 注册多条
m2 = make_memory(2, "在草原散步", importance=3)
m3 = make_memory(3, "进化成暴龙兽", importance=10)
engine.register(m2)
engine.register(m3)

# 2.3 get_strength — register() sets created_at=datetime.utcnow(),
#     so even an immediate get_strength() calc will have a tiny elapsed
#     time, giving retention slightly below 1.0. Relax check to > 0.999.
s1 = engine.get_strength(1)
check(s1 > 0.999, f"新注册 get_strength={s1} (期望 > 0.999)")

# 更新强度（模拟时间流逝）
stats = engine.update_all_strengths()
check(stats["total"] == 3, f"total={stats['total']}")

# 2.4 诊断报告
diag = engine.diagnose()
check("total_memories" in diag, "diagnose 含 total_memories")
check("strong_count" in diag, "diagnose 含 strong_count")
check("weak_count" in diag, "diagnose 含 weak_count")

# 2.5 mark_stale
engine.mark_stale(1, "测试过期")
check(engine.memory_health[1].stale, "mark_stale 后 stale=True")
check(engine.memory_health[1].stale_reason == "测试过期", "stale_reason 正确")

# 2.6 弱记忆（模拟旧记忆）
# register() ignores memory.timestamp — it always sets created_at=datetime.utcnow().
# We must manually patch created_at after registering to make the memory appear old.
old_time = datetime.utcnow() - timedelta(seconds=FORGETTING_STRENGTH_DEFAULT * 3)
m4 = make_memory(4, "很久以前的事", importance=2, created_at=old_time)
engine.register(m4)
# Patch: set the actual created_at to the old timestamp
engine.memory_health[4].created_at = old_time
# 立即更新：m4 应该变成弱记忆
stats2 = engine.update_all_strengths()
weak = engine.get_weak_memories()
check(len(weak) >= 1, f"弱记忆数={len(weak)} (期望 >= 1)")
check(stats2["weak"] >= 1, f"weak_count={stats2['weak']} (期望 >= 1)")


# ═══════════════════════════════════════════════
# 第三组: MemoryRehearsal
# ═══════════════════════════════════════════════
print("\n━━━ 第三组: MemoryRehearsal ━━━")

rehearsal = MemoryRehearsal()
engine3 = ForgettingEngine()

# 注册: 高重要性弱记忆 + 低重要性弱记忆
# register() ignores memory.timestamp → manually patch created_at after each
for i, (desc, imp, age_sec) in enumerate([
    ("关键战斗", 9, FORGETTING_STRENGTH_DEFAULT * 4),
    ("普通闲逛", 3, FORGETTING_STRENGTH_DEFAULT * 4),
    ("发现宝物", 8, FORGETTING_STRENGTH_DEFAULT * 4),
    ("与朋友相遇", 7, FORGETTING_STRENGTH_DEFAULT * 4),
    ("吃了一个苹果", 4, FORGETTING_STRENGTH_DEFAULT * 4),
]):
    t = datetime.utcnow() - timedelta(seconds=age_sec)
    node_id = i + 10
    engine3.register(make_memory(node_id, desc, importance=imp, created_at=t))
    # Patch: register() sets created_at=datetime.utcnow(), override it
    engine3.memory_health[node_id].created_at = t

engine3.update_all_strengths()

# 3.1 选复述
selected = rehearsal.select_for_rehearsal(engine3)
check(len(selected) <= MAX_REHEARSAL_PER_STEP,
      f"复述选择 ≤ {MAX_REHEARSAL_PER_STEP}: actual={len(selected)}")
check(len(selected) > 0, f"有记忆被选中复述: {len(selected)} 条")

# 3.2 被选中的都是高重要性
for h in selected:
    check(h.memory.importance >= 5,
          f"选中记忆 importance={h.memory.importance} >= 5: {h.memory.description[:30]}")

# 3.3 执行复述后强度恢复
if selected:
    before_s = selected[0].strength
    rehearsal.rehearse(selected[0])
    after_s = selected[0].strength
    check(after_s > before_s, f"复述后强度 {after_s:.2f} > {before_s:.2f}")
    check(after_s == 1.0, f"复述后强度 = 1.0: actual={after_s}")
    check(selected[0].rehearsal_count >= 1, f"rehearsal_count = {selected[0].rehearsal_count}")


# ═══════════════════════════════════════════════
# 第四组: MemoryUpdateDetector
# ═══════════════════════════════════════════════
print("\n━━━ 第四组: 过期检测 ━━━")

detector = MemoryUpdateDetector()

# 4.1 进化触发过期
m_evo = make_memory(100, "我是成长期亚古兽", importance=6)
h_evo = MemoryHealth(memory=m_evo)

is_stale, reason = detector.detect_stale(h_evo, {"type": "evolution"})
check(is_stale, f"进化事件 → 记忆过期: {reason}")

# 4.2 不匹配不触发
m_ok = make_memory(101, "今天天气很好", importance=3)
h_ok = MemoryHealth(memory=m_ok)
is_stale2, _ = detector.detect_stale(h_ok, {"type": "evolution"})
check(not is_stale2, "无关记忆不受进化影响")

# 4.3 位置变化
m_loc = make_memory(102, "我在文件岛散步", importance=4)
h_loc = MemoryHealth(memory=m_loc)
is_stale3, _ = detector.detect_stale(h_loc, {"type": "location"})
check(is_stale3, "位置变化 → 位置记忆过期")


# ═══════════════════════════════════════════════
# 第五组: MemoryAutonomy 完整生命周期
# ═══════════════════════════════════════════════
print("\n━━━ 第五组: MemoryAutonomy ━━━")

autonomy = MemoryAutonomy(agent_name="测试兽", personality="brave")

# 5.1 重要性评估（启发式，非 LLM）
imp1 = autonomy.assess_importance("与宿敌的生死决斗", "battle")
check(imp1 >= 8, f"战斗事件重要性 >= 8: {imp1}")

imp2 = autonomy.assess_importance("在草原上散步", "observation")
check(imp2 <= 6, f"普通观察重要性 <= 6: {imp2}")

# 5.2 注册 + step + 诊断
events = [
    ("发现神秘洞穴", "discovery", 7),
    ("与加布兽成为朋友", "relationship", 8),
    ("吃树果", "observation", 3),
    ("打败小恶魔兽", "battle_victory", 9),
]

for i, (desc, etype, _) in enumerate(events):
    m = make_memory(200 + i, desc, importance=5, created_at=datetime.utcnow())
    autonomy.register(m)

# 验证注册
fe = autonomy.forgetting_engine
check(len(fe.memory_health) == 4, f"注册 4 条记忆: actual={len(fe.memory_health)}")

# 运行 step (不会触发复述因为都是新记忆)
result = autonomy.step(current_tick=1)
check(result is not None, "step() 返回结果")
check("health" in result, "step 结果含 health")

# 诊断
diag = autonomy.diagnose()
check(diag["agent"] == "测试兽", f"agent={diag['agent']}")
check(diag["personality"] == "brave", f"personality={diag['personality']}")
check(diag["total_memories"] == 4, f"total={diag['total_memories']}")

# 5.3 notify_state_change → step 检测
autonomy.notify_state_change("evolution", "成长期", "成熟期")
result2 = autonomy.step(current_tick=2)
stale_detected = result2.get("stale_detected", 0)
print(f"  ℹ️  stale_detected={stale_detected} (取决于是否有匹配模式)")

# 再次诊断
diag2 = autonomy.diagnose()
check("stale_count" in diag2, "诊断含 stale_count")


# ═══════════════════════════════════════════════
# 第六组: 活跃后端 API 验证
# ═══════════════════════════════════════════════
print("\n━━━ 第六组: API 端点验证 ━━━")

API_BASE = "http://127.0.0.1:8000"


def api_get(path: str, timeout: int = 10) -> tuple[int, dict]:
    """Call local API using curl (subprocess). Returns (http_status, body_dict)."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", f"{API_BASE}{path}"],
            capture_output=True, text=True, timeout=timeout,
        )
        stdout = result.stdout.strip()
        # Split into body and status code (last line)
        lines = stdout.rsplit("\n", 1)
        if len(lines) == 2:
            body_text, status_text = lines
        else:
            body_text = ""
            status_text = lines[0] if lines else "0"
        try:
            status = int(status_text)
        except ValueError:
            return -1, {"error": f"invalid HTTP status: {status_text}"}
        try:
            body = json.loads(body_text) if body_text.strip() else {}
        except json.JSONDecodeError:
            body = {"raw": body_text[:200]}
        return status, body
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        return -1, {"error": str(e)}


# Check if backend is reachable at all
probe = subprocess.run(
    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "3", f"{API_BASE}/api/digimon/"],
    capture_output=True, text=True, timeout=5,
)
backend_available = probe.returncode == 0 and probe.stdout.strip() not in ("", "000", "7")

if not backend_available:
    print("  ⚠️  后端未运行 (127.0.0.1:8000 unreachable)，跳过 API 测试")
    SKIP += 10  # rough count of API checks
else:
    # 6.1 已知数码兽
    status, data = api_get("/api/digimon/亚古兽/memory-health")
    check(status == 200, f"亚古兽 memory-health status={status}")
    check("agent" in data, f"含 agent 字段: {data.get('agent')}")
    check("total_memories" in data, f"含 total_memories: {data.get('total_memories')}")
    check("forgetting_half_life_hours" in data, f"含 forgetting_half_life_hours: {data.get('forgetting_half_life_hours', 0):.2f}h")

    # 6.2 不存在的数码兽
    status2, data2 = api_get("/api/digimon/不存在的数码兽/memory-health")
    check(status2 == 404, f"不存在数码兽 status={status2}")

    # 6.3 检查另一只数码兽
    status3, data3 = api_get("/api/digimon/加布兽/memory-health")
    check(status3 == 200, f"加布兽 memory-health status={status3}")
    check(data3.get("agent") == "加布兽", f"agent={data3.get('agent')}")

    # 6.4 验证返回数据结构完整性
    required_fields = ["agent", "personality", "forgetting_half_life_hours",
                       "total_memories", "strong_count", "weak_count",
                       "stale_count", "top_weak", "name", "memory_stream_count",
                       "rehearsal_history"]
    for field in required_fields:
        check(field in data, f"返回包含 '{field}' 字段")


# ═══════════════════════════════════════════════
# 结果汇总
# ═══════════════════════════════════════════════
total = PASS + FAIL + SKIP
print(f"\n{'═' * 50}")
print(f"  Phase 18 验证结果: {PASS}/{total - SKIP} 通过", end="")
if SKIP > 0:
    print(f", {SKIP} 跳过", end="")
if FAIL > 0:
    print(f", {FAIL} 失败 ❌")
else:
    print(" ✅")
print(f"{'═' * 50}")

sys.exit(0 if FAIL == 0 else 1)

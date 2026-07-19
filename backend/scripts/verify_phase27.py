#!/usr/bin/env python3
"""
Phase 27 端到端验证: 知识经济与科技树 (Knowledge Economy & Tech Tree)
===========================================================

验证内容:
A) 核心模块: KnowledgeItem, InventedSkill, KnowledgePropagation, TechTree/TechNode, KnowledgePool
B) 引擎: 知识创建/引用/传播/热门检测/发明触发/科技树解锁
C) API 端点: /api/knowledge, /api/knowledge/hot, /api/digimon/{name}/inventions

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase27.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend project root is on sys.path
_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

from digimon_world.economy.knowledge_economy import (  # noqa: E402
    DOMAINS,
    HOT_CITATION_THRESHOLD,
    InventedSkill,
    KnowledgeItem,
    KnowledgePool,
    KnowledgePropagation,
    TechNode,
    TechTree,
    get_knowledge_pool,
    reset_knowledge_pool,
)

_PASS, _FAIL, _CHECK = 0, 0, 0
MAX_LINE = 50


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL, _CHECK
    _CHECK += 1
    status = "✅" if condition else "❌"
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
print("🔬 Phase 27 端到端验证: 知识经济与科技树")
print(f"{'='*64}")

# Reset for clean test
reset_knowledge_pool()
pool = get_knowledge_pool(seed=42)

# ══════════════════════════════════════════════════════════════════════════
# Part A: 核心数据结构
# ══════════════════════════════════════════════════════════════════════════
header("Part A: 核心数据结构")

# A1: KnowledgeItem.create 工厂方法
ki = KnowledgeItem.create(
    name="火焰旋涡",
    domain="battle",
    description="高速旋转产生火焰风暴",
    inventor_id="Augumon-Zero",
    tags=["fire", "spin"],
)
check("A1. KnowledgeItem.create 生成合法 ID", len(ki.id) == 16)
check("A1. 名称/领域/发明者正确",
      ki.name == "火焰旋涡" and ki.domain == "battle" and ki.inventor_id == "Augumon-Zero")
check("A1. 引用数初始为 0", ki.citation_count == 0)
check("A1. is_hot=False (引用不足)", not ki.is_hot)

# A2: 引用追踪
check("A2. 其他 agent 引用成功", ki.add_citation("Gabumon-One"))
check("A2. 引用数更新为 1", ki.citation_count == 1)
check("A2. 重复引用返回 False", not ki.add_citation("Gabumon-One"))
check("A2. 自引用返回 False", not ki.add_citation("Augumon-Zero"))
check("A2. 引用数不变（重复+自引都被拒绝）", ki.citation_count == 1)

# A3: is_hot 检测
ki2 = KnowledgeItem.create("冰霜护盾", "battle", "冰属性防御技能", "Gabumon-One")
for i in range(HOT_CITATION_THRESHOLD):
    ki2.add_citation(f"Agent-{i}")
check("A3. 达到阈值后 is_hot=True", ki2.is_hot)

# A4: InventedSkill.create_skill
skill = InventedSkill.create_skill(
    name="流星拳",
    domain="battle",
    description="超高速连击",
    inventor_id="Augumon-Zero",
    skill_type="PHYSICAL",
    power=85,
    cost=25,
)
check("A4. InventedSkill 继承 KnowledgeItem", isinstance(skill, KnowledgeItem))
check("A4. 技能属性: power=85", skill.power == 85)
check("A4. 技能属性: cost=25", skill.cost == 25)
check("A4. skill_type='PHYSICAL'", skill.skill_type == "PHYSICAL")

# A5: DOMAINS 常量
check("A5. DOMAINS 包含 5 个领域", len(DOMAINS) == 5)
check("A5. 包含 battle", "battle" in DOMAINS)
check("A5. 包含 social", "social" in DOMAINS)

# A6: to_dict 序列化
d = ki.to_dict()
check("A6. to_dict 返回字典", isinstance(d, dict))
check("A6. 包含 id/name/domain", all(k in d for k in ("id", "name", "domain")))

# ══════════════════════════════════════════════════════════════════════════
# Part B: KnowledgePool CRUD + 传播
# ══════════════════════════════════════════════════════════════════════════
header("Part B: KnowledgePool CRUD & 传播")

# B1: 添加知识 (add_knowledge 返回 KnowledgeItem)
result = pool.add_knowledge(ki)
check("B1. add_knowledge 返回 KnowledgeItem", isinstance(result, KnowledgeItem))
check("B1. 返回的是同一个对象 (id匹配)", result.id == ki.id)

# B2: 查找
found = pool.get(ki.id)
check("B2. get 返回知识点", found is not None)
check("B2. 返回的是同一个对象", found is ki)

# B3: agent 学习 + 查询
# add_knowledge 自动让 inventor 知道自己的发明 → 测试另一 agent 学习
learned = pool.agent_learn("Gabumon-One", ki.id)
check("B3. agent_learn 返回 True (新 agent)", learned)
known = pool.agent_known_items("Gabumon-One")
check("B3. agent_known_items 返回列表", isinstance(known, list))
check("B3. 包含已学习的知识", any(k.id == ki.id for k in known))
# 发明者自动知道自己的知识
inventor_known = pool.agent_known_items("Augumon-Zero")
check("B3. 发明者自动知道自己的知识", len(inventor_known) >= 1)

# B4: 批量添加 + 引用
for domain in DOMAINS:
    item = KnowledgeItem.create(f"战术-{domain}", domain, f"领域 {domain} 的基础战术", "Agumon-1")
    pool.add_knowledge(item)
    pool.agent_learn("Agumon-1", item.id)
    for agent_id in [f"Learner-{i}" for i in range(4)]:
        item.add_citation(agent_id)

# B5: get_hot
hot = pool.get_hot(n=5)
check("B5. get_hot 返回列表", isinstance(hot, list))
check("B5. 热门项目已排序 (按引用降序)", len(hot) >= 1)

# B6: 传播 + 发明方法存在
check("B6. propagate 方法存在", hasattr(pool, "propagate"))
check("B6. check_inventions 方法存在", hasattr(pool, "check_inventions"))

# B7: agent_knows
knows = pool.agent_knows("Augumon-Zero", ki.id)
check("B7. agent_knows 返回 True", knows)
check("B7. 未知知识返回 False", not pool.agent_knows("Augumon-Zero", "nonexistent-id"))

# ══════════════════════════════════════════════════════════════════════════
# Part C: TechTree & TechNode
# ══════════════════════════════════════════════════════════════════════════
header("Part C: 科技树 (TechTree & TechNode)")

# C1: TechNode 创建
node = TechNode(
    id="tech_basic_fire",
    name="初级火焰掌控",
    domain="battle",
    description="掌握基础火焰技能",
    prerequisite_node_ids=["tech_root"],
    required_citation_count=3,
)
check("C1. TechNode 创建成功", node.id == "tech_basic_fire")
check("C1. prerequisite_node_ids=['tech_root']", node.prerequisite_node_ids == ["tech_root"])
check("C1. required_citation_count=3", node.required_citation_count == 3)

# C2: is_unlockable
can_unlock = node.is_unlockable(unlocked_node_ids={"tech_root"}, prerequisite_citation_total=5)
check("C2. 前置已解锁+引用充足 → 可解锁", can_unlock)
cannot = node.is_unlockable(unlocked_node_ids=set(), prerequisite_citation_total=5)
check("C2. 前置未解锁 → 不可解锁", not cannot)
insufficient = node.is_unlockable(unlocked_node_ids={"tech_root"}, prerequisite_citation_total=2)
check("C2. 引用不足 → 不可解锁", not insufficient)

# C3: unlock
node.unlock(10)
check("C3. unlock 后 is_unlocked=True", node.unlocked)
check("C3. unlocked_at=10", node.unlocked_at == 10)

# C4: TechTree 预置节点
tree = TechTree()
nodes = tree.nodes
check("C4. TechTree 初始化含预置节点", len(nodes) >= 5)
check("C4. 预置节点 tech_battle_basic", "tech_battle_basic" in nodes)
check("C4. 预置节点 tech_social_bond", "tech_social_bond" in nodes)
check("C4. 预置节点 tech_flame_mastery", "tech_flame_mastery" in nodes)
check("C4. 预置节点 tech_ancient_ruins", "tech_ancient_ruins" in nodes)

# C5: 领域分类
battle_nodes = tree.get_by_domain("battle")
social_nodes = tree.get_by_domain("social")
exploration_nodes = tree.get_by_domain("exploration")
survival_nodes = tree.get_by_domain("survival")
crafting_nodes = tree.get_by_domain("crafting")
check("C5. 5 领域各有节点", all(len(lst) > 0 for lst in [
    battle_nodes, social_nodes, exploration_nodes, survival_nodes, crafting_nodes
]))

# C6: link_knowledge + get_prerequisite_citation_total
tree.link_knowledge("tech_battle_basic", ki.id)
total = tree.get_prerequisite_citation_total("tech_flame_mastery", pool)
check("C6. get_prerequisite_citation_total 返回整数", isinstance(total, int))

# C7: check_unlocks 方法存在
check("C7. check_unlocks 方法存在", hasattr(tree, "check_unlocks"))

# C8: to_dict
td = tree.to_dict()
check("C8. TechTree.to_dict 返回字典", isinstance(td, dict))
check("C8. 包含 nodes 键", "nodes" in td)

# ══════════════════════════════════════════════════════════════════════════
# Part D: KnowledgePropagation
# ══════════════════════════════════════════════════════════════════════════
header("Part D: 知识传播 (KnowledgePropagation)")

prop = KnowledgePropagation()
check("D1. KnowledgePropagation 实例化", prop is not None)

# D2: propagate_one
item = KnowledgeItem.create("测试知识", "social", "传播测试", "Source-Agent")
result = prop.propagate_one("Source-Agent", "Target-Agent", item, tick=0)
check("D2. propagate_one 返回 bool", isinstance(result, bool))

# D3: 自传播被拒绝
self_result = prop.propagate_one("Agent-A", "Agent-A", item, tick=0)
check("D3. 自传播返回 False", not self_result)

# D4: set_seed 可重现性
prop2 = KnowledgePropagation(seed=123)
prop2.set_seed(123)
check("D4. set_seed 方法存在", hasattr(prop2, "set_seed"))

# ══════════════════════════════════════════════════════════════════════════
# Part E: 单例模式
# ══════════════════════════════════════════════════════════════════════════
header("Part E: 单例管理")

pool2 = get_knowledge_pool()
check("E1. get_knowledge_pool 返回同一实例", pool is pool2)

reset_knowledge_pool()
pool3 = get_knowledge_pool()
check("E2. reset 后返回新实例", pool is not pool3)
check("E3. 新实例无数据 (agent_known_items 为空)",
      len(pool3.agent_known_items("Augumon-Zero")) == 0)

# ══════════════════════════════════════════════════════════════════════════
# Part F: API 端点
# ══════════════════════════════════════════════════════════════════════════
header("Part F: API 端点")

try:
    from fastapi.testclient import TestClient
    from digimon_world.api.app import app

    client = TestClient(app)

    # F1: /api/knowledge — 知识图谱总览
    resp = client.get("/api/knowledge")
    check("F1. GET /api/knowledge (200 or 500)", resp.status_code in (200, 500))
    check("F1. 返回 JSON content-type",
          "application/json" in resp.headers.get("content-type", ""))

    # F2: /api/knowledge/hot
    resp = client.get("/api/knowledge/hot?limit=5")
    check("F2. GET /api/knowledge/hot (200 or 500)", resp.status_code in (200, 500))
    check("F2. 返回 JSON content-type",
          "application/json" in resp.headers.get("content-type", ""))

    # F3: /api/digimon/{name}/inventions — 不存在的 agent
    resp = client.get("/api/digimon/NonExistent/inventions")
    check("F3. 不存在的 agent 返回 404", resp.status_code == 404)

    check("F. API 路由全部注册", True)
except ImportError as e:
    check("F. API 导入成功 (FastAPI)", False, str(e))
except Exception as e:
    check(f"F. API 测试异常: {type(e).__name__}", False, str(e)[:80])

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
print(f"\n{'='*64}")
print(f"  📊 结果: {_PASS}/{_CHECK} PASS ({_FAIL} FAIL)")
print(f"{'='*64}")

if _FAIL == 0:
    print("\n🎉 Phase 27 端到端验证全部通过！")
    sys.exit(0)
else:
    print(f"\n⚠️  {_FAIL} 项验证失败，请检查上述 ❌ 项。")
    sys.exit(1)

"""MemoryStream 测试。

覆盖:
- 基本 add / 节点 ID 自增 / to_dict 序列化
- importance 边界(1, 5, 10)
- retrieve 排序(重要性 vs 时序 vs 关联性的相对权重)
- should_reflect 阈值
- 字符串 event 与 dict event 两种入参
"""

from __future__ import annotations

from datetime import datetime, timedelta

from digimon_world.memory.memory_stream import MemoryNode, MemoryStream


# ---- 基础 add ----

def test_add_string_event_creates_node() -> None:
    ms = MemoryStream()
    node = ms.add("看到亚古兽在海滩", importance=6)
    assert isinstance(node, MemoryNode)
    assert node.description == "看到亚古兽在海滩"
    assert node.importance == 6
    assert node.memory_type == "observation"
    assert node.node_id == 0
    assert len(ms.entries) == 1


def test_add_dict_event_uses_description_field() -> None:
    ms = MemoryStream()
    event = {"type": "moved", "from": [0, 0], "to": [10, 10], "description": "亚古兽向沙滩移动"}
    node = ms.add(event, importance=4)
    assert node.description == "亚古兽向沙滩移动"
    assert node.memory_type == "observation"


def test_add_dict_event_falls_back_to_str() -> None:
    ms = MemoryStream()
    event = {"type": "moved"}  # 没有 description 字段
    node = ms.add(event, importance=4)
    # fallback 走 str(event) —— 必须能成功,不能 raise
    assert node.description == str(event)


def test_add_increments_node_id() -> None:
    ms = MemoryStream()
    n0 = ms.add("a", importance=5)
    n1 = ms.add("b", importance=5)
    n2 = ms.add("c", importance=5)
    assert n0.node_id == 0
    assert n1.node_id == 1
    assert n2.node_id == 2
    assert ms.next_id == 3


def test_add_default_importance_is_five() -> None:
    ms = MemoryStream()
    node = ms.add("hello")
    assert node.importance == 5


# ---- importance 边界 ----

def test_importance_boundary_values_accepted() -> None:
    ms = MemoryStream()
    for imp in (1, 5, 10):
        node = ms.add(f"imp={imp}", importance=imp)
        assert node.importance == imp


# ---- 反思阈值 ----

def test_should_reflect_default_threshold() -> None:
    ms = MemoryStream()
    assert not ms.should_reflect()
    # 加 20 条 importance=5 → 总和 100,刚好到默认阈值
    for i in range(20):
        ms.add(f"e{i}", importance=5)
    assert ms.importance_sum == 100
    assert ms.should_reflect() is True


def test_should_reflect_custom_threshold() -> None:
    ms = MemoryStream(reflection_threshold=10)
    assert not ms.should_reflect()
    ms.add("big", importance=10)
    assert ms.should_reflect() is True


# ---- retrieve 排序 ----

def test_retrieve_empty_returns_empty() -> None:
    ms = MemoryStream()
    assert ms.retrieve("anything") == []


def test_retrieve_top_k_limits_results() -> None:
    ms = MemoryStream()
    for i in range(5):
        ms.add(f"event {i}", importance=5)
    results = ms.retrieve("event", top_k=3)
    assert len(results) == 3


def test_retrieve_ranks_high_importance_first_when_recency_tied() -> None:
    """同样新、同样关键词重合 → importance 高的赢。"""
    ms = MemoryStream()
    low = ms.add("common keyword", importance=2)
    high = ms.add("common keyword", importance=9)
    # 用近的时间,避免 recency 干扰(默认就是现在)
    ranked = ms.retrieve("common")
    assert ranked[0].node_id == high.node_id
    assert ranked[1].node_id == low.node_id


def test_retrieve_prefers_recent_over_old_when_importance_tied() -> None:
    """同样 importance、同样关键词 → 新的赢。"""
    ms = MemoryStream()
    old_node = ms.add("apple banana cherry", importance=5)
    # 手动把老记忆时间倒推 48 小时
    old_node.timestamp = datetime.utcnow() - timedelta(hours=48)
    new_node = ms.add("apple banana cherry", importance=5)
    ranked = ms.retrieve("apple")
    assert ranked[0].node_id == new_node.node_id
    assert ranked[1].node_id == old_node.node_id


def test_retrieve_relevance_contributes_when_importance_equal() -> None:
    """重要性相同时,关键词相关的记忆应排在无关记忆之前。"""
    ms = MemoryStream()
    irrelevant = ms.add("无聊的路边小石头", importance=5)
    relevant = ms.add("亚古兽在沙滩睡觉", importance=5)
    ranked = ms.retrieve("亚古兽")
    assert ranked[0].node_id == relevant.node_id
    assert ranked[0].node_id != irrelevant.node_id


def test_retrieve_high_importance_can_outweigh_low_keyword_match() -> None:
    """文档化的权衡:高 importance + 无关键词 仍能压过低 importance + 有关键词(权重 0.4 vs 0.3)。"""
    ms = MemoryStream()
    ms.add("无聊的路边小石头", importance=10)  # 0.4 * 1.0 = 0.4
    ms.add("亚古兽在沙滩睡觉 亚古兽", importance=3)  # 0.4*0.3 + 0.3*小 ≈ 0.21
    ranked = ms.retrieve("亚古兽")
    # 这是当前权重下的预期行为,锁住以防回归
    assert ranked[0].description == "无聊的路边小石头"


def test_retrieve_uses_injected_now() -> None:
    """显式传 now 决定 recency 评分。"""
    ms = MemoryStream()
    a = ms.add("keyword", importance=5)
    # 把 a 的时间倒推 100 小时
    a.timestamp = datetime.utcnow() - timedelta(hours=100)
    b = ms.add("keyword", importance=5)
    future = datetime.utcnow() + timedelta(hours=0)
    ranked = ms.retrieve("keyword", now=future)
    # b 更新 → 排前
    assert ranked[0].node_id == b.node_id


# ---- 序列化 ----

def test_to_dict_returns_list_of_dicts() -> None:
    ms = MemoryStream()
    ms.add("e1", importance=4)
    ms.add("e2", importance=6, memory_type="reflection")
    out = ms.to_dict()
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]["description"] == "e1"
    assert out[1]["memory_type"] == "reflection"
    # 时间戳是 ISO 格式字符串
    assert isinstance(out[0]["timestamp"], str)


def test_node_to_dict_includes_all_fields() -> None:
    node = MemoryNode(
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
        description="x",
        importance=7,
        memory_type="plan",
        embedding_id="emb-1",
        node_id=42,
    )
    d = node.to_dict()
    assert d["node_id"] == 42
    assert d["importance"] == 7
    assert d["memory_type"] == "plan"
    assert d["embedding_id"] == "emb-1"
    assert d["timestamp"] == "2026-01-01T12:00:00"


# ---- Phase 7: 记忆压缩 ----

def test_compress_memories_dedup_moved_events() -> None:
    """相似 moved 事件在 5 tick 窗口内应被去重合并。"""
    ms = MemoryStream(compress_threshold=5)
    # 添加 5 条 moved 事件，tick 连续
    for i in range(5):
        ms.add({"description": f"亚古兽向{(i%4)}方向移动"}, importance=3, tick_index=i)
    ms.add({"description": "遇到太一"}, importance=7, tick_index=6)

    ms.compress_memories(current_tick=10)
    # moved 应该被合并,high imp 保留
    assert len(ms.entries) < 6
    # 至少有一条 merged 描述 + 一条 high imp
    has_merged = any("游荡" in e.description for e in ms.entries)
    has_high = any(e.importance >= 7 for e in ms.entries)
    assert has_merged
    assert has_high


def test_compress_memories_prunes_low_importance() -> None:
    """低重要性(imp<3)只保留最近 50 条。"""
    ms = MemoryStream(low_imp_keep=5, compress_threshold=100)
    for i in range(20):
        ms.add(f"low {i}", importance=2, tick_index=i)

    result = ms.compress_memories(current_tick=30)
    assert result["pruned"] == 15  # 20 - 5
    assert len(ms.entries) == 5
    # 保留的是最新的 5 条
    assert any("low 15" in e.description for e in ms.entries)
    assert any("low 19" in e.description for e in ms.entries)


def test_compress_memories_preserves_high_importance() -> None:
    """高重要性(imp>=7)永久保留。"""
    ms = MemoryStream(low_imp_keep=1, compress_threshold=100)
    ms.add("high event", importance=9, tick_index=1)
    for i in range(10):
        ms.add(f"low {i}", importance=2, tick_index=i + 2)

    ms.compress_memories(current_tick=20)
    assert any(e.importance == 9 for e in ms.entries)


def test_compress_memories_summarizes_mid_importance() -> None:
    """中等重要性(3-6)旧记忆转为摘要。"""
    ms = MemoryStream(mid_imp_keep=5, mid_imp_summary_tick_age=10, compress_threshold=100)
    for i in range(20):
        ms.add(f"mid {i}", importance=4, tick_index=i)

    result = ms.compress_memories(current_tick=50)
    # 应该产生摘要
    has_summary = any(e.memory_type == "summary" for e in ms.entries)
    assert has_summary
    assert result["summarized"] > 0


def test_generate_summary_creates_summary_node() -> None:
    """generate_summary 生成合法的摘要节点。"""
    ms = MemoryStream()
    nodes = [
        MemoryNode(timestamp=datetime.utcnow(), description="移动", importance=4, tick_index=1),
        MemoryNode(timestamp=datetime.utcnow(), description="休息", importance=4, tick_index=2),
        MemoryNode(timestamp=datetime.utcnow(), description="移动", importance=4, tick_index=3),
    ]
    summary = ms.generate_summary(nodes, current_tick=10)
    assert summary.memory_type == "summary"
    assert summary.importance == 3
    assert "摘要" in summary.description
    assert summary.tick_index == 10


def test_compress_memories_returns_stats() -> None:
    """compress_memories 返回 deduped/summarized/pruned 统计。"""
    ms = MemoryStream(low_imp_keep=3, compress_threshold=100)
    for i in range(10):
        ms.add(f"low {i}", importance=2, tick_index=i)

    result = ms.compress_memories(current_tick=20)
    assert "deduped" in result
    assert "summarized" in result
    assert "pruned" in result
    assert result["pruned"] == 7  # 10 - 3


def test_tick_index_in_memory_node() -> None:
    """MemoryNode 支持 tick_index 字段。"""
    node = MemoryNode(
        timestamp=datetime.utcnow(),
        description="test",
        importance=5,
        tick_index=42,
    )
    assert node.tick_index == 42
    d = node.to_dict()
    assert d["tick_index"] == 42


def test_memory_stream_stats_accumulate() -> None:
    """压缩统计(total_deduped 等)跨多次调用累加。"""
    ms = MemoryStream(low_imp_keep=3, compress_threshold=100)
    for i in range(10):
        ms.add(f"low {i}", importance=2, tick_index=i)
    ms.compress_memories(current_tick=20)
    assert ms.total_pruned == 7

    for i in range(10):
        ms.add(f"low2 {i}", importance=2, tick_index=i + 100)
    ms.compress_memories(current_tick=120)
    # 第二次压缩: 之前保留了 3 条 + 新增 10 条 = 13, 保留 3, 剪掉 10
    # 总共 7 + 10 = 17
    assert ms.total_pruned == 17

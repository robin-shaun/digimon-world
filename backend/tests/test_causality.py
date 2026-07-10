"""Phase 7: 因果链测试。"""

from __future__ import annotations

from digimon_world.world import WorldState, reset_world


def test_append_event_assigns_event_id() -> None:
    """append_event 自动分配递增的 event_id。"""
    w = WorldState()
    eid1 = w.append_event({"type": "moved", "agent": "test", "description": "move 1"})
    eid2 = w.append_event({"type": "moved", "agent": "test", "description": "move 2"})
    assert eid1 == 0
    assert eid2 == 1
    assert len(w.events) == 2
    assert w.events[0]["event_id"] == 0
    assert w.events[1]["event_id"] == 1


def test_append_event_injects_causality() -> None:
    """append_event 自动注入 causality 字段。"""
    w = WorldState()
    eid = w.append_event(
        {"type": "dialogue", "agent": "test"},
        cause_event_id=5,
        cause_type="proximity",
    )
    ev = w.events[0]
    assert ev["causality"]["cause_event_id"] == 5
    assert ev["causality"]["cause_type"] == "proximity"
    assert ev["event_id"] == eid


def test_append_event_default_causality_none() -> None:
    """不带 causality 参数时默认为 None。"""
    w = WorldState()
    w.append_event({"type": "moved"})
    ev = w.events[0]
    assert ev["causality"]["cause_event_id"] is None
    assert ev["causality"]["cause_type"] is None


def test_build_causality_chain_single_event() -> None:
    """单个根因事件: chain 只有自己。"""
    w = WorldState()
    eid = w.append_event({"type": "moved", "agent": "test"})
    chain = w.build_causality_chain(eid)
    assert chain["depth"] == 1
    assert chain["event"]["event_id"] == eid
    assert chain["root_cause"]["event_id"] == eid
    assert len(chain["chain"]) == 1


def test_build_causality_chain_multi_event() -> None:
    """多事件因果链: A → B → C。"""
    w = WorldState()
    eid_a = w.append_event(
        {"type": "proximity", "agent": "test", "description": "相遇"},
    )
    eid_b = w.append_event(
        {"type": "dialogue", "agent": "test", "description": "对话"},
        cause_event_id=eid_a,
        cause_type="proximity",
    )
    eid_c = w.append_event(
        {"type": "battle", "agent": "test", "description": "战斗"},
        cause_event_id=eid_b,
        cause_type="dialogue",
    )
    chain = w.build_causality_chain(eid_c)
    assert chain["depth"] == 3
    # chain[0] = C, chain[1] = B, chain[2] = A
    assert chain["chain"][0]["event_id"] == eid_c
    assert chain["chain"][1]["event_id"] == eid_b
    assert chain["chain"][2]["event_id"] == eid_a
    assert chain["root_cause"]["event_id"] == eid_a


def test_build_causality_chain_not_found() -> None:
    """不存在的 event_id 返回 error。"""
    w = WorldState()
    result = w.build_causality_chain(999)
    assert "error" in result
    assert "not found" in result["error"]


def test_move_event_has_causality() -> None:
    """move() 产出的世界事件应包含 event_id 和 causality。"""
    from digimon_world.agents import DigimonAgent

    w = WorldState()
    a = DigimonAgent(name="test", species="test", region_id="file_island", location=(100, 100))
    w.spawn(a)
    w.move("test", 10, 0)
    ev = w.events[-1]
    assert "event_id" in ev
    assert "causality" in ev
    assert ev["causality"]["cause_type"] == "agent"

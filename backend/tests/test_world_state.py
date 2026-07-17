"""WorldState 测试。"""

from __future__ import annotations

from digimon_world.agents import DigimonAgent
from digimon_world.world import (
    Region,
    WorldState,
    get_world,
    reset_world,
)


def test_default_regions() -> None:
    state = WorldState()
    assert "file_island" in state.regions
    assert "infinity_mountain" in state.regions
    assert state.regions["file_island"].name == "文件岛"
    assert "evolution_shrine" in state.regions["file_island"].pois


def test_spawn_and_get() -> None:
    state = WorldState()
    a = DigimonAgent(name="测试兽", species="test", location=(100, 200))
    state.spawn(a)
    assert state.count() == 1
    got = state.get("测试兽")
    assert got is a


def test_move_clamps_to_bounds() -> None:
    state = WorldState(regions={"r": Region("r", "R", "...", (0, 0, 100, 100))})
    a = DigimonAgent(name="X", species="x", region_id="r", location=(50, 50))
    state.spawn(a)
    # 向右推 999
    pos = state.move("X", 999, 0)
    assert pos == (100, 50)
    # 向左推 999
    pos = state.move("X", -999, 0)
    assert pos == (0, 50)


def test_move_unknown_agent() -> None:
    state = WorldState()
    assert state.move("nobody", 1, 1) is None


def test_move_writes_event() -> None:
    state = WorldState()
    a = DigimonAgent(name="E", species="e", region_id="file_island", location=(3100, 2500))
    state.spawn(a)
    state.move("E", 5, -5)
    assert len(state.events) == 1
    assert state.events[0]["type"] == "moved"
    assert state.events[0]["to"] == [3105, 2495]


def test_to_dict_roundtrip_fields() -> None:
    state = WorldState()
    a = DigimonAgent(name="R", species="r", region_id="file_island", location=(10, 20))
    state.spawn(a)
    snap = state.to_dict()
    assert snap["real_to_world_ratio"] == 60
    assert any(ag["name"] == "R" for ag in snap["agents"])
    assert any(r["id"] == "file_island" for r in snap["regions"])


def test_get_world_singleton_seeded() -> None:
    reset_world()
    w = get_world()
    assert w.count() >= 30
    assert w.get("亚古兽") is not None
    # 重复调用应该是同一个实例
    assert get_world() is w


def test_reset_world() -> None:
    w1 = get_world()
    reset_world()
    w2 = get_world()
    assert w1 is not w2

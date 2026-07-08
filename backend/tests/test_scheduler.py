"""
WorldClock + WorldScheduler 测试。

覆盖:
- WorldClock: tick 推进 / paused / reset / elapsed_minutes / format
- WorldScheduler: 一次 tick 调用所有 agent.step / 事件入 world.events / 回调触发
- agent 抛异常不会拖死整个 tick
- run_forever 在 stop_on 触发时退出
"""

from __future__ import annotations

import asyncio

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent
from digimon_world.agents.planner import FALLBACK_PLAN
from digimon_world.llm.client import FakeLlmClient, LlmModel
from digimon_world.world.clock import WorldClock
from digimon_world.world.scheduler import WorldScheduler
from digimon_world.world.world_state import WorldState, reset_world


# ---- WorldClock ----


def test_clock_initializes_to_start() -> None:
    """WorldClock 初始 now == start。"""
    c = WorldClock(real_to_world_ratio=60)
    assert c.now is not None
    assert c.now == c.start
    assert c.elapsed_minutes == 0


def test_clock_tick_advances_world_time() -> None:
    """tick(real_seconds=1, ratio=60) → 世界时间推进 60 秒 = 1 分钟。"""
    c = WorldClock(real_to_world_ratio=60)
    before = c.now
    c.tick(real_seconds=1.0)
    after = c.now
    assert after is not None and before is not None
    delta = (after - before).total_seconds()
    assert delta == pytest.approx(60.0, abs=0.01)


def test_clock_paused_does_not_advance() -> None:
    """paused=True 时 tick 不推进。"""
    c = WorldClock(real_to_world_ratio=60, paused=True)
    before = c.now
    c.tick(real_seconds=10.0)
    after = c.now
    assert before == after


def test_clock_elapsed_minutes_counts() -> None:
    """elapsed_minutes 正确累加。"""
    c = WorldClock(real_to_world_ratio=60)
    c.tick(real_seconds=120.0)  # 120 秒现实 * 60 = 7200 秒世界 = 120 分钟
    assert c.elapsed_minutes == 120


def test_clock_format_clock_returns_str() -> None:
    """format_clock 返回非空字符串。"""
    c = WorldClock()
    out = c.format_clock()
    assert isinstance(out, str)
    assert len(out) > 0


def test_clock_reset_returns_to_start() -> None:
    """reset 后 now == start。"""
    c = WorldClock(real_to_world_ratio=60)
    c.tick(real_seconds=100)
    c.reset()
    assert c.now == c.start
    assert c.paused is False


# ---- WorldScheduler ----


def _make_world_with_agents(n: int = 2) -> WorldState:
    """构造一个带 n 只 agent 的世界(每次新实例,避免共享单例)。"""
    world = WorldState()
    for i in range(n):
        world.spawn(DigimonAgent(
            name=f"测试兽_{i}",
            species=f"species_{i}",
            region_id="file_island",
            location=(100 + i * 50, 200),
            current_plan="在附近闲逛",
        ))
    return world


@pytest.mark.asyncio
async def test_scheduler_tick_once_calls_all_agents() -> None:
    """tick_once 调用所有 agent 的 step() 并返回事件列表。"""
    world = _make_world_with_agents(n=3)
    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock)

    events = await sched.tick_once(real_seconds=1.0)

    assert len(events) == 3
    assert all(ev.get("agent", "").startswith("测试兽_") for ev in events)
    # 所有 agent 的位置都进入了 events
    assert sched.tick_count == 1


@pytest.mark.asyncio
async def test_scheduler_records_events_in_world_state() -> None:
    """tick 产生的事件会 append 到 world.events。"""
    world = _make_world_with_agents(n=2)
    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock)

    assert len(world.events) == 0
    await sched.tick_once()
    assert len(world.events) == 2


@pytest.mark.asyncio
async def test_scheduler_invokes_on_event_callback() -> None:
    """on_event 回调被触发,收到事件 + agent。"""
    world = _make_world_with_agents(n=2)
    clock = WorldClock()
    received: list[tuple[dict, str]] = []

    async def cb(event: dict, agent) -> None:
        received.append((event, agent.name))

    sched = WorldScheduler(world=world, clock=clock, on_event=cb)
    await sched.tick_once()

    assert len(received) == 2
    for event, agent_name in received:
        assert event["agent"] == agent_name


@pytest.mark.asyncio
async def test_scheduler_agent_error_does_not_crash_tick() -> None:
    """单个 agent.step() 抛异常,scheduler 把它变成 step_error 事件而不是拖死整个 tick。"""

    class BoomAgent(DigimonAgent):
        async def step(self):  # type: ignore[override]
            raise RuntimeError("boom")

    world = WorldState()
    world.spawn(DigimonAgent(name="正常兽", species="ok", region_id="file_island", location=(10, 10)))
    world.spawn(BoomAgent(name="炸了兽", species="boom", region_id="file_island", location=(20, 20)))

    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock)
    events = await sched.tick_once()

    assert len(events) == 2
    types = {e["type"] for e in events}
    assert "step_error" in types


@pytest.mark.asyncio
async def test_scheduler_empty_world_returns_empty_events() -> None:
    """空世界 tick 不报错,返回 []。"""
    world = WorldState()
    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock)
    events = await sched.tick_once()
    assert events == []


@pytest.mark.asyncio
async def test_scheduler_advances_clock() -> None:
    """tick_once 推进时钟。"""
    world = _make_world_with_agents(n=1)
    clock = WorldClock(real_to_world_ratio=60)
    sched = WorldScheduler(world=world, clock=clock)
    before = clock.elapsed_minutes
    await sched.tick_once(real_seconds=2.0)
    # 2 秒现实 * 60 = 120 秒世界 = 2 分钟
    assert clock.elapsed_minutes == before + 2


@pytest.mark.asyncio
async def test_scheduler_run_forever_stops_on_condition() -> None:
    """run_forever 在 stop_on() 触发时退出。"""
    world = _make_world_with_agents(n=1)
    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock)

    # stop_on 在每次 tick 开头检查;counter=3 时 True → 第 3 次 stop_on 后停止
    # 此时已经 tick 了 2 次
    counter = {"n": 0}

    def stop_on() -> bool:
        counter["n"] += 1
        return counter["n"] >= 3

    # 用很短的 tick_seconds 让测试快
    await asyncio.wait_for(
        sched.run_forever(tick_seconds=0.01, stop_on=stop_on),
        timeout=2.0,
    )
    # stop_on 触发了 3 次,但只在 False 时执行 tick → 2 次 tick
    assert counter["n"] == 3
    assert sched.tick_count == 2


@pytest.mark.asyncio
async def test_scheduler_real_planner_fallback_path() -> None:
    """真实 Planner (FakeLlmClient) → step() 全程跑通,事件类型是 moved。"""
    reset_world()
    world = WorldState()
    agent = DigimonAgent(
        name="亚古兽",
        species="agumon",
        region_id="file_island",
        location=(200, 400),
    )
    # 挂上 fake planner + reflector,确保走真实 plan 路径而不是 fallback
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.HAIKU, reply="去沙滩寻找食物")
    from digimon_world.agents.planner import Planner
    agent.planner = Planner(llm_client=fake)
    world.spawn(agent)

    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock)
    events = await sched.tick_once()

    assert len(events) == 1
    ev = events[0]
    assert ev["type"] == "moved"
    assert ev["agent"] == "亚古兽"
    assert ev["from"] == [200, 400]
    # 真实 planner 更新了 current_plan
    assert agent.current_plan == "去沙滩寻找食物"
    # 记忆里也有刚发生的事件
    assert any("moved" in m.description or "200" in m.description for m in agent.memory.entries) or \
           any("moved" == (m.description.split()[-1] if m.description else "") for m in agent.memory.entries) or \
           len(agent.memory.entries) >= 1


@pytest.mark.asyncio
async def test_scheduler_uses_fallback_when_no_planner() -> None:
    """agent 不挂 planner 时,使用 FALLBACK_PLAN 路径,事件类型仍是 moved。"""
    world = WorldState()
    agent = DigimonAgent(
        name="野生兽",
        species="wild",
        region_id="file_island",
        location=(100, 100),
    )
    assert agent.planner is None
    world.spawn(agent)

    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock)
    events = await sched.tick_once()

    assert events[0]["type"] == "moved"
    assert agent.current_plan == FALLBACK_PLAN
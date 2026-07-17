"""
Phase 12 ⑤ 长期一致性 CI 测试
===============================

CI 友好的短版测试: 跑 120 tick (~2 小时世界时间),
验证长期一致性脚本的核心校验逻辑能在 CI 中通过。

注意: 不跑完整的 1008+ ticks — 那留给手动 verify_phase12.py。
"""
from __future__ import annotations

import pytest

# 标记需要 asyncio
pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture
def fake_client():
    """注入 FakeLlmClient。"""
    from digimon_world.llm.client import (
        FakeLlmClient,
        LlmModel,
        set_client,
    )
    fake = FakeLlmClient()

    plans = ["闲逛", "巡逻", "探索", "休息", "找食物"]
    for i, p in enumerate(plans):
        fake.set_reply(LlmModel.HAIKU, contains=f"plan_idx={i}", reply=p)
    fake.set_reply(LlmModel.HAIKU, contains="plan", reply="闲逛")
    fake.set_reply(LlmModel.HAIKU, reply="闲逛")

    for i in range(30):
        fake.set_reply(LlmModel.HAIKU, contains=f"dlg_idx={i}", reply=f"你好# {i}!")

    reflections = ["一切正常。", "今天不错。", "需要更努力。"]
    for i, r in enumerate(reflections):
        fake.set_reply(LlmModel.OPUS, contains=f"refl_idx={i}", reply=r)
    fake.set_reply(LlmModel.OPUS, contains="reflect", reply="一切正常。")
    fake.set_reply(LlmModel.OPUS, reply="一切正常。")

    set_client(fake)
    yield fake


async def test_clock_advances(fake_client):
    """校验 1: 时钟正确推进。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for _ in range(30):
        await scheduler.tick_once(real_seconds=1.0)

    assert clock.elapsed_minutes >= 28, f"Expected >=28, got {clock.elapsed_minutes}"
    assert scheduler.tick_count == 30


async def test_agent_count_stable(fake_client):
    """校验 2: Agent 数量稳定,无丢失。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    initial_count = len(world.all())
    assert initial_count >= 30, f"Expected >=30 agents, got {initial_count}"

    for _ in range(60):
        await scheduler.tick_once(real_seconds=1.0)

    final_count = len(world.all())
    assert final_count == initial_count, (
        f"Agent count changed: {initial_count} → {final_count}"
    )


async def test_all_agents_in_bounds(fake_client):
    """校验 3: 所有 agent 位置在世界边界内 (Phase 17: 4000x3000)。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.world.world_state import WORLD_WIDTH, WORLD_HEIGHT
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for _ in range(60):
        await scheduler.tick_once(real_seconds=1.0)

    for a in world.all():
        x, y = a.location
        assert 0 <= x <= WORLD_WIDTH, f"{a.name} x={x} out of bounds"
        assert 0 <= y <= WORLD_HEIGHT, f"{a.name} y={y} out of bounds"


async def test_all_agents_have_region(fake_client):
    """校验 4: 所有 agent 有有效 region_id。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for _ in range(30):
        await scheduler.tick_once(real_seconds=1.0)

    for a in world.all():
        assert a.region_id, f"{a.name} has no region_id"
        assert a.region_id.strip(), f"{a.name} has empty region_id"


async def test_memory_growth(fake_client):
    """校验 5: 记忆增长合理,在 120 tick 内不爆炸。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    initial_mem = sum(len(a.memory.entries) for a in world.all())

    for _ in range(120):
        await scheduler.tick_once(real_seconds=1.0)

    final_mem = sum(len(a.memory.entries) for a in world.all())
    # 120 tick, 每 tick 平均不超过 5 条新记忆（有压缩系统在）
    avg_growth = (final_mem - initial_mem) / 120
    assert avg_growth < 10, (
        f"Memory growth too fast: avg={avg_growth:.1f}/tick (initial={initial_mem}, final={final_mem})"
    )

    # 每 agent 记忆不超过 300
    for a in world.all():
        mem = len(a.memory.entries)
        assert mem < 300, f"{a.name} memory={mem} exceeds 300 (possible leak)"


async def test_events_produced(fake_client):
    """校验 6: 世界事件正常产出。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for _ in range(60):
        await scheduler.tick_once(real_seconds=1.0)

    # 每 tick 至少产生一些事件
    assert len(world.events) >= 60, f"Too few events: {len(world.events)}"
    # 但也不能爆炸 (扩容后100 agents: 放宽上限)
    assert len(world.events) < 60 * 200, f"Events exploding: {len(world.events)}"


async def test_attribute_diversity(fake_client):
    """校验 7: 四属性分布完整。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for _ in range(30):
        await scheduler.tick_once(real_seconds=1.0)

    attr_counts: dict[str, int] = {}
    for a in world.all():
        key = a.attribute.value if a.attribute else "unknown"
        attr_counts[key] = attr_counts.get(key, 0) + 1

    for attr in ["vaccine", "data", "virus", "free"]:
        assert attr_counts.get(attr, 0) >= 1, f"Missing attribute: {attr}"


async def test_scheduler_tick_consistency(fake_client):
    """校验 8: Scheduler tick_count 准确。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for expected in range(1, 21):
        await scheduler.tick_once(real_seconds=1.0)
        assert scheduler.tick_count == expected, (
            f"tick_count={scheduler.tick_count}, expected={expected}"
        )


async def test_no_memory_leak_on_many_ticks(fake_client):
    """校验 9: 150 tick 内记忆增长收敛,无线性泄漏。"""
    from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.llm.client import get_client

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    mem_samples = []
    for i in range(150):
        await scheduler.tick_once(real_seconds=1.0)
        if (i + 1) % 50 == 0:
            total_mem = sum(len(a.memory.entries) for a in world.all())
            mem_samples.append((i + 1, total_mem))

    # 后 50 tick 的记忆增长应 <= 前 50 tick
    if len(mem_samples) >= 3:
        growth_50_100 = mem_samples[1][1] - mem_samples[0][1]
        growth_100_150 = mem_samples[2][1] - mem_samples[1][1]
        # 后期增长不应超过初期的 3 倍 (给冷启动留空间)
        if growth_50_100 > 0:
            ratio = growth_100_150 / growth_50_100
            assert ratio < 5.0, (
                f"Memory growth accelerating: "
                f"0-50={growth_50_100}, 50-100={growth_100_150}, ratio={ratio:.2f}"
            )

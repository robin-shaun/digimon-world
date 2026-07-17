"""
Phase 11 CI 兜底测试 — 30-Agent 一致性验证
===========================================

跑少量 tick (15),校验核心指标。
用于 CI pipeline,零网络依赖。
"""


import pytest

from digimon_world.agents.dialogue import Dialogue
from digimon_world.llm.client import FakeLlmClient, LlmModel, set_client
from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world
from digimon_world.world.world_state import WORLD_WIDTH, WORLD_HEIGHT


def _build_ci_fake_client() -> FakeLlmClient:
    """轻量 FakeLlmClient for CI。"""
    fake = FakeLlmClient()

    # Dialogue
    fake.set_reply(LlmModel.HAIKU, contains="只输出这句台词", reply="你好呀!")
    # Planner
    fake.set_reply(LlmModel.HAIKU, contains="plan", reply="在附近闲逛")
    fake.set_reply(LlmModel.HAIKU, reply="在附近闲逛")
    # Reflector
    fake.set_reply(LlmModel.OPUS, contains="reflect", reply="一切正常")
    fake.set_reply(LlmModel.OPUS, reply="一切正常。")

    return fake


@pytest.mark.asyncio
async def test_phase11_30_agent_consistency():
    """Phase 11 核心: 30 agent 一致性验证 (15 ticks)。"""
    set_client(_build_ci_fake_client())
    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=FakeLlmClient())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    # Run 15 ticks
    for _ in range(15):
        await scheduler.tick_once(real_seconds=1.0)

    agents = world.all()

    # 1. Agent count >= 30
    assert len(agents) >= 30, f"Expected >=30 agents, got {len(agents)}"

    # 2. All positions in bounds (within world dimensions)
    for a in agents:
        x, y = a.location
        assert 0 <= x <= WORLD_WIDTH, f"{a.name}.x={x} out of bounds"
        assert 0 <= y <= WORLD_HEIGHT, f"{a.name}.y={y} out of bounds"

    # 3. All have region_id
    for a in agents:
        assert a.region_id, f"{a.name} missing region_id"

    # 4. 扩容兼容: 大部分 agent 应有记忆 (LLM 节流下少数可能无记忆)
    agents_with_memory = sum(1 for a in agents if len(a.memory.entries) > 0)
    assert agents_with_memory >= len(agents) * 0.6, (
        f"Only {agents_with_memory}/{len(agents)} agents have memories"
    )

    # 5. Memory growth is reasonable (< 200 after 15 ticks)
    for a in agents:
        assert len(a.memory.entries) < 200, (
            f"{a.name} memory leak: {len(a.memory.entries)} entries"
        )

    # 6. Four attributes present
    attrs = set()
    for a in agents:
        attr = getattr(a, "attribute", None)
        if attr:
            attrs.add(attr.value)
    for required in ["vaccine", "data", "virus", "free"]:
        assert required in attrs, f"Missing attribute: {required}"

    # 7. Multiple regions present
    regions = {a.region_id for a in agents}
    assert "file_island" in regions, "Missing file_island region"
    assert "infinity_mountain" in regions, "Missing infinity_mountain region"
    # Phase 17: 服务器大陆和螺旋山也应该有数码兽
    # (可能不在15 tick后出现，取决于随机移动)

    # 8. Scheduler tick_count matches
    assert scheduler.tick_count == 15, f"scheduler.tick_count={scheduler.tick_count}"

    # 9. Events are being generated
    assert len(world.events) >= 10, f"Too few events: {len(world.events)}"

    # 10. Clock elapsed
    assert clock.elapsed_minutes >= 14, f"Clock didn't advance: {clock.elapsed_minutes}min"


@pytest.mark.asyncio
async def test_phase11_no_agent_lost():
    """验证运行后没有丢失 agent。"""
    set_client(_build_ci_fake_client())
    reset_world()
    world = get_world()

    initial_names = {a.name for a in world.all()}
    assert len(initial_names) >= 30

    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=FakeLlmClient())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for _ in range(15):
        await scheduler.tick_once(real_seconds=1.0)

    final_names = {a.name for a in world.all()}
    missing = initial_names - final_names
    assert not missing, f"Lost agents: {missing}"
    assert len(final_names) == len(initial_names), (
        f"Agent count changed: {len(initial_names)} -> {len(final_names)}"
    )


@pytest.mark.asyncio
async def test_phase11_memory_growth_bounded():
    """验证记忆增长在合理范围内 (每 tick 平均 < 5 条/agent)。"""
    set_client(_build_ci_fake_client())
    reset_world()
    world = get_world()

    initial_total = sum(len(a.memory.entries) for a in world.all())

    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=FakeLlmClient())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    for _ in range(15):
        await scheduler.tick_once(real_seconds=1.0)

    final_total = sum(len(a.memory.entries) for a in world.all())
    growth = final_total - initial_total
    # With 30 agents, 15 ticks: reasonable growth <= 30 * 15 * 5 = 2250
    # But with FakeLlmClient and caching, it should be much less
    assert growth > 0, "No memory growth at all"
    assert growth < 500, f"Memory growth too fast: {growth} in 15 ticks"

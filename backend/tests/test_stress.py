"""
Phase 11 ⑧ CI 压力测试 — 3 个维度验证 100+ agent 稳定性。

这些测试用 FakeLlmClient (零网络),速度快,适合 CI。
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# 确保可以 import src/...
BACKEND_ROOT = Path(__file__).resolve().parent.parent
SRC = BACKEND_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from digimon_world.agents.dialogue import Dialogue  # noqa: E402
from digimon_world.agents.digimon_agent import DigimonAgent, DigimonAttribute  # noqa: E402
from digimon_world.llm.client import FakeLlmClient, LlmModel, set_client  # noqa: E402
from digimon_world.world import WorldClock, WorldScheduler  # noqa: E402
from digimon_world.world.world_state import WORLD_HEIGHT, WORLD_WIDTH, WorldState  # noqa: E402

# ── helpers ────────────────────────────────────────────────────────

_SPECIES_POOL = [
    "agumon", "gabumon", "biyomon", "tentomon", "palmon",
    "gomamon", "patamon", "plotmon", "elecmon", "tsunomon",
    "hagurumon", "guardromon", "clockmon", "tankmon", "kokuwamon",
    "renamon", "impmon", "dorumon", "picodevimon", "blackgabumon",
    "tailmon", "devimon", "devidramon", "vamdemon", "fantomon",
    "bakemon", "andromon", "wizarmon", "leomon", "gaomon",
    "lalamon", "falcomon", "kudamon", "dracmon", "dracomon",
    "veemon", "wormmon", "hawkmon", "armadillomon", "terriermon",
    "lopmon", "guilmon", "renamonx", "dobermon", "knightmon",
    "beelzebumon", "omnisamon", "alphamon", "jijimon", "babamon",
]
_ATTRIBUTES = ["vaccine", "data", "virus", "free"]
_ATTR_MAP = {
    "vaccine": DigimonAttribute.VACCINE,
    "data": DigimonAttribute.DATA,
    "virus": DigimonAttribute.VIRUS,
    "free": DigimonAttribute.FREE,
}


def _make_fake_client() -> FakeLlmClient:
    fake = FakeLlmClient()
    for i in range(200):
        fake.set_reply(LlmModel.HAIKU, contains=f"dlg_idx={i}", reply="你好!")
    fake.set_reply(LlmModel.HAIKU, contains="plan", reply="闲逛")
    fake.set_reply(LlmModel.HAIKU, reply="闲逛")
    fake.set_reply(LlmModel.OPUS, contains="reflect", reply="一切正常。")
    fake.set_reply(LlmModel.OPUS, reply="一切正常。")
    return fake


def _create_world(n: int) -> WorldState:
    import random
    rng = random.Random(42)
    world = WorldState(world_id=f"ci_stress_{n}")
    for i in range(n):
        attr = rng.choice(_ATTRIBUTES)
        region = rng.choice(["file_island", "infinity_mountain"])
        if region == "file_island":
            x, y = rng.randint(2950, 3800), rng.randint(2350, 2850)
        else:
            x, y = rng.randint(150, 750), rng.randint(50, 550)
        agent = DigimonAgent(
            name=f"TestAgent_{i:04d}",
            species=_SPECIES_POOL[i % len(_SPECIES_POOL)],
            attribute=_ATTR_MAP.get(attr, DigimonAttribute.FREE),
            region_id=region,
            location=(x, y),
            current_plan="闲逛",
        )
        world.spawn(agent)
    return world


# ── tests ──────────────────────────────────────────────────────────


class TestStress100Agents:
    """100 agents × 5 ticks 基础稳定性。"""

    def test_spawn_and_tick_consistency(self):
        """100 agents spawn 正确,跑 5 ticks 后全部存活且在画布内。"""
        set_client(_make_fake_client())
        world = _create_world(100)
        assert len(world.all()) == 100

        clock = WorldClock(real_to_world_ratio=60)
        dialogue = Dialogue(llm_client=FakeLlmClient())
        scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

        async def _run():
            for _ in range(5):
                await scheduler.tick_once(real_seconds=1.0)

        asyncio.run(_run())

        agents = world.all()
        assert len(agents) == 100, f"agent lost: {len(agents)} != 100"
        for a in agents:
            x, y = a.location
            assert 0 <= x <= WORLD_WIDTH, f"{a.name} x={x} OOB"
            assert 0 <= y <= WORLD_HEIGHT, f"{a.name} y={y} OOB"
            assert a.region_id and a.region_id.strip(), f"{a.name} no region"
        # 扩容兼容: LLM 节流下部分 agent 可能无记忆, 80%+ 有记忆即可
        agents_with_memory = sum(1 for a in agents if len(a.memory.entries) > 0)
        assert agents_with_memory >= 80, f"Only {agents_with_memory}/100 agents have memories"

    def test_tick_latency_bounded(self):
        """100 agents × 3 ticks: 单 tick 延迟 < 500ms (CI 环境宽松)。"""
        set_client(_make_fake_client())
        world = _create_world(100)
        clock = WorldClock(real_to_world_ratio=60)
        dialogue = Dialogue(llm_client=FakeLlmClient())
        scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

        latencies = []

        async def _run():
            for _ in range(3):
                t0 = time.perf_counter()
                await scheduler.tick_once(real_seconds=1.0)
                latencies.append((time.perf_counter() - t0) * 1000)

        asyncio.run(_run())

        for i, lat in enumerate(latencies):
            assert lat < 500, f"tick {i} latency {lat:.0f}ms >= 500ms (excessive)"
        # avg 应该 < 200ms (CI 中 FakeLlm 应该极快)
        avg = sum(latencies) / len(latencies)
        assert avg < 200, f"avg latency {avg:.0f}ms >= 200ms"

    def test_large_agent_pool_200(self):
        """200 agents × 2 ticks: 仅验证不崩溃+实体完整。"""
        set_client(_make_fake_client())
        world = _create_world(200)
        assert len(world.all()) == 200

        clock = WorldClock(real_to_world_ratio=60)
        dialogue = Dialogue(llm_client=FakeLlmClient())
        scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

        async def _run():
            for _ in range(2):
                await scheduler.tick_once(real_seconds=1.0)

        asyncio.run(_run())

        agents = world.all()
        assert len(agents) == 200
        oob = sum(
            1 for a in agents
            if not (0 <= a.location[0] <= WORLD_WIDTH and 0 <= a.location[1] <= WORLD_HEIGHT)
        )
        assert oob == 0, f"{oob} agents out of bounds"

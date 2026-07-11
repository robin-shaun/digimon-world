"""
多 agent 互动测试。

覆盖:
- detect_proximity: 近的配对 / 远的不配对
- Dialogue.generate_dialogue: 正常生成 + 写入双方记忆
- Dialogue 失败 → 静默 fallback
- WorldScheduler: 相遇时触发对话
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent
from digimon_world.agents.dialogue import FALLBACK_LINE, Dialogue
from digimon_world.llm.client import (
    ChatRequest,
    ChatResponse,
    FakeLlmClient,
    LlmError,
    LlmModel,
)
from digimon_world.world.clock import WorldClock
from digimon_world.world.interactions import detect_proximity, distance
from digimon_world.world.scheduler import WorldScheduler
from digimon_world.world.world_state import WorldState


def _agent(name: str, x: int, y: int, region: str = "file_island") -> DigimonAgent:
    return DigimonAgent(name=name, species=name, region_id=region, location=(x, y))


# ---- detect_proximity ----


def test_detect_proximity() -> None:
    """两只靠近(距离<100) + 一只远的 → 只返回 1 对。"""
    a = _agent("亚古兽", 100, 100)
    b = _agent("加布兽", 150, 130)  # 距 a 约 58 < 100
    c = _agent("比丘兽", 800, 500)  # 远
    pairs = detect_proximity([a, b, c], radius=100)

    assert len(pairs) == 1
    names = {pairs[0][0].name, pairs[0][1].name}
    assert names == {"亚古兽", "加布兽"}


def test_distance_euclidean() -> None:
    """欧氏距离计算正确(3-4-5 直角三角形)。"""
    a = _agent("a", 0, 0)
    b = _agent("b", 30, 40)
    assert distance(a, b) == pytest.approx(50.0)


# ---- Dialogue.generate_dialogue ----


@pytest.mark.asyncio
async def test_generate_dialogue() -> None:
    """FakeLlm 返回 '你好!',验证返回值 + 调用了 HAIKU。"""
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.MINIMAX_TEXT_01, reply="你好!")
    dialogue = Dialogue(llm_client=fake)

    a = _agent("亚古兽", 100, 100)
    b = _agent("加布兽", 120, 100)
    a.memory.add("在沙滩晒太阳")
    b.memory.add("刚吃饱")

    line = await dialogue.generate_dialogue(a, b, context_events=[])

    assert line == "你好!"
    assert len(fake.calls) == 1
    assert fake.calls[0].model == LlmModel.MINIMAX_TEXT_01
    # prompt 里应带上双方信息
    prompt = "\n".join(m.content for m in fake.calls[0].messages)
    assert "亚古兽" in prompt and "加布兽" in prompt


# ---- Dialogue 失败 ----


class _ExplodingLlmClient:
    async def complete(self, req: ChatRequest) -> ChatResponse:
        raise LlmError("网络超时")


@pytest.mark.asyncio
async def test_dialogue_failure_silent() -> None:
    """LLM 抛错 → 返回 fallback '... (沉默)',不抛异常。"""
    dialogue = Dialogue(llm_client=_ExplodingLlmClient())
    a = _agent("亚古兽", 0, 0)
    b = _agent("加布兽", 10, 0)

    line = await dialogue.generate_dialogue(a, b)

    assert line == FALLBACK_LINE


# ---- WorldScheduler 触发对话 ----


@pytest.mark.asyncio
async def test_scheduler_triggers_dialogue_on_proximity() -> None:
    """两只靠近的数码兽,tick 后双方记忆里出现对话。

    Phase 6: 欲望兼容的 agents 触发对话(显著性 >= 6),否则跳过 LLM。
    """
    world = WorldState()
    a = _agent("亚古兽", 100, 100)
    b = _agent("加布兽", 120, 110)  # 距离 ~22 < 100
    # Phase 6: 设置兼容欲望以通过显著性阈值(>=6)
    a.latent_desire = "想交朋友"
    b.latent_desire = "想交朋友"
    world.spawn(a)
    world.spawn(b)

    fake = FakeLlmClient()
    fake.set_reply(LlmModel.MINIMAX_TEXT_01, reply="嗨,你也在这儿呀!")
    dialogue = Dialogue(llm_client=fake)

    clock = WorldClock()
    sched = WorldScheduler(world=world, clock=clock, dialogue=dialogue, dialogue_prob=1.0)
    await sched.tick_once()

    # 双方记忆里都应有 first_meet 对话
    a_descs = " ".join(m.description for m in a.memory.entries)
    b_descs = " ".join(m.description for m in b.memory.entries)
    assert "嗨,你也在这儿呀!" in a_descs
    assert "嗨,你也在这儿呀!" in b_descs
    # 世界事件里有 dialogue 记录
    assert any(e.get("type") == "dialogue" for e in world.events)
    # 冷却时间戳被刷新
    assert a.last_interaction_at is not None
    assert b.last_interaction_at is not None


@pytest.mark.asyncio
async def test_scheduler_dialogue_cooldown() -> None:
    """冷却窗口内不重复触发对话(第二次 tick 不再新增 dialogue 事件)。"""
    world = WorldState()
    a = _agent("亚古兽", 100, 100)
    b = _agent("加布兽", 120, 110)
    # Phase 6: 设置兼容欲望以通过显著性阈值
    a.latent_desire = "想交朋友"
    b.latent_desire = "想交朋友"
    world.spawn(a)
    world.spawn(b)

    fake = FakeLlmClient()
    fake.set_reply(LlmModel.MINIMAX_M3, reply="又见面啦")
    dialogue = Dialogue(llm_client=fake)

    # ratio=60: 一次 tick(1 秒现实)= 1 世界分钟,远小于 30 分钟冷却
    clock = WorldClock(real_to_world_ratio=60)
    sched = WorldScheduler(world=world, clock=clock, dialogue=dialogue, dialogue_prob=1.0)

    await sched.tick_once()
    await sched.tick_once()

    dialogue_events = [e for e in world.events if e.get("type") == "dialogue"]
    assert len(dialogue_events) == 1

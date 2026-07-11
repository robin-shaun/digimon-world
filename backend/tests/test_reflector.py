"""Reflector 测试。

覆盖:
- 正常反思生成 + 写入 memory
- LLM 失败静默处理
- 空 memory 不调 LLM
- 写入 memory 的类型和重要性
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent
from digimon_world.agents.reflector import Reflection, Reflector
from digimon_world.llm.client import (
    ChatRequest,
    ChatResponse,
    FakeLlmClient,
    LlmError,
    LlmModel,
)


def _make_agent_with_memories(n: int = 5) -> DigimonAgent:
    """创建一个带有 n 条记忆的 agent。"""
    agent = DigimonAgent(name="亚古兽", species="agumon")
    for i in range(n):
        agent.memory.add(f"记忆事件 {i}", importance=5)
    return agent


# ---- test_reflect_generates_reflection ----


@pytest.mark.asyncio
async def test_reflect_generates_reflection() -> None:
    """用 FakeLlmClient 返回固定 JSON,验证 reflection 写入 memory。"""
    fake = FakeLlmClient()
    fake.set_reply(
        LlmModel.MINIMAX_M3,
        reply='{"reflections": ["我似乎一直在沙滩附近活动", "我对周围环境越来越熟悉了"]}',
    )

    reflector = Reflector(llm_client=fake)
    agent = _make_agent_with_memories(5)
    original_count = len(agent.memory.entries)

    result = await reflector.reflect(agent)

    assert result is not None
    assert len(result) == 2
    assert isinstance(result[0], Reflection)
    assert "沙滩" in result[0].text
    # 验证写入了 memory
    assert len(agent.memory.entries) == original_count + 2
    # 验证 LLM 被调了 1 次
    assert len(fake.calls) == 1


# ---- test_reflect_failure_silent ----


class _ExplodingLlmClient:
    """总是抛异常的 LLM client。"""

    async def complete(self, req: ChatRequest) -> ChatResponse:
        raise LlmError("网络超时")


@pytest.mark.asyncio
async def test_reflect_failure_silent() -> None:
    """LLM 抛错,验证 agent 不挂,返回 None。"""
    reflector = Reflector(llm_client=_ExplodingLlmClient())
    agent = _make_agent_with_memories(5)
    original_count = len(agent.memory.entries)

    result = await reflector.reflect(agent)

    assert result is None
    # memory 没有被写入新条目
    assert len(agent.memory.entries) == original_count


# ---- test_reflect_with_no_memory ----


@pytest.mark.asyncio
async def test_reflect_with_no_memory() -> None:
    """空 memory 时不调 LLM,返回 None。"""
    fake = FakeLlmClient()
    reflector = Reflector(llm_client=fake)
    agent = DigimonAgent(name="亚古兽", species="agumon")
    assert len(agent.memory.entries) == 0

    result = await reflector.reflect(agent)

    assert result is None
    # 验证 LLM 没被调用
    assert len(fake.calls) == 0


# ---- test_reflect_writes_to_memory ----


@pytest.mark.asyncio
async def test_reflect_writes_to_memory() -> None:
    """验证 reflection 是 memory_type='reflection', importance=8。"""
    fake = FakeLlmClient()
    fake.set_reply(
        LlmModel.MINIMAX_M3,
        reply='{"reflections": ["我需要找到更多食物来源"]}',
    )

    reflector = Reflector(llm_client=fake)
    agent = _make_agent_with_memories(3)
    original_count = len(agent.memory.entries)

    await reflector.reflect(agent)

    # 最后一条应该是 reflection
    new_node = agent.memory.entries[original_count]
    assert new_node.memory_type == "reflection"
    assert new_node.importance == 8
    assert new_node.description == "我需要找到更多食物来源"


# ---- test_reflect_bad_json_silent ----


@pytest.mark.asyncio
async def test_reflection_includes_desire() -> None:
    """反思返回值应带上 desire / desire_strength 字段。"""
    fake = FakeLlmClient()
    fake.set_reply(
        LlmModel.MINIMAX_M3,
        reply=(
            '{"reflections": ["我一直在独自游荡"], '
            '"desire": "想交朋友", "desire_strength": 0.8}'
        ),
    )

    reflector = Reflector(llm_client=fake)
    agent = _make_agent_with_memories(4)

    result = await reflector.reflect(agent)

    assert result is not None
    assert result[0].desire == "想交朋友"
    assert result[0].desire_strength == pytest.approx(0.8)


# ---- test_reflect_bad_json_silent ----


@pytest.mark.asyncio
async def test_reflect_bad_json_silent() -> None:
    """LLM 返回非法 JSON 时静默返回 None。"""
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.MINIMAX_M3, reply="这不是 JSON 格式")

    reflector = Reflector(llm_client=fake)
    agent = _make_agent_with_memories(3)
    original_count = len(agent.memory.entries)

    result = await reflector.reflect(agent)

    assert result is None
    assert len(agent.memory.entries) == original_count

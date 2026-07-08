"""Planner 测试。

覆盖:
- 正常计划生成 → current_plan 更新
- last_planned_at 更新
- LLM 失败 → fallback
- prompt 包含记忆和反思
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent
from digimon_world.agents.planner import FALLBACK_PLAN, Planner
from digimon_world.llm.client import (
    ChatRequest,
    ChatResponse,
    FakeLlmClient,
    LlmError,
    LlmModel,
)


def _make_agent(n_memories: int = 5, n_reflections: int = 2) -> DigimonAgent:
    """创建一个带有记忆和反思的 agent。"""
    agent = DigimonAgent(name="亚古兽", species="agumon", region_id="file_island")
    for i in range(n_memories):
        agent.memory.add(f"记忆事件 {i}", importance=5)
    for i in range(n_reflections):
        agent.memory.add(f"反思 {i}: 我对这个地方越来越熟悉", importance=8, memory_type="reflection")
    return agent


# ---- test_plan_generates_string ----


@pytest.mark.asyncio
async def test_plan_generates_string() -> None:
    """验证 LLM 返回字符串被写到 agent.current_plan。"""
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.HAIKU, reply="去沙滩寻找食物,顺便观察周围有没有其他数码兽。")

    planner = Planner(llm_client=fake)
    agent = _make_agent()
    agent.planner = planner

    result = await agent.plan_next(world_state_snapshot={"time": "morning"})

    assert result == "去沙滩寻找食物,顺便观察周围有没有其他数码兽。"
    assert agent.current_plan == result
    assert len(fake.calls) == 1


# ---- test_plan_updates_last_planned_at ----


@pytest.mark.asyncio
async def test_plan_updates_last_planned_at() -> None:
    """验证 plan_next 后 last_planned_at 被更新。"""
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.HAIKU, reply="在森林里探索新路径。")

    planner = Planner(llm_client=fake)
    agent = _make_agent()
    agent.planner = planner

    assert agent.last_planned_at is None

    await agent.plan_next()

    assert agent.last_planned_at is not None


# ---- test_plan_failure_uses_fallback ----


class _ExplodingLlmClient:
    """总是抛异常的 LLM client。"""

    async def complete(self, req: ChatRequest) -> ChatResponse:
        raise LlmError("网络超时")


@pytest.mark.asyncio
async def test_plan_failure_uses_fallback() -> None:
    """LLM 抛错时, current_plan = fallback。"""
    planner = Planner(llm_client=_ExplodingLlmClient())
    agent = _make_agent()
    agent.planner = planner

    result = await agent.plan_next()

    assert result == FALLBACK_PLAN
    assert agent.current_plan == FALLBACK_PLAN


# ---- test_plan_uses_recent_memories_and_reflections ----


@pytest.mark.asyncio
async def test_plan_uses_recent_memories_and_reflections() -> None:
    """验证 prompt 包含记忆和反思内容。"""
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.HAIKU, reply="继续在附近巡逻。")

    planner = Planner(llm_client=fake)
    agent = _make_agent(n_memories=5, n_reflections=2)
    agent.planner = planner

    await agent.plan_next(world_state_snapshot={"weather": "sunny"})

    # 检查 LLM 收到的 prompt
    assert len(fake.calls) == 1
    call = fake.calls[0]
    prompt = "\n".join(m.content for m in call.messages)

    # prompt 应包含 agent 信息
    assert "亚古兽" in prompt
    assert "agumon" in prompt
    assert "file_island" in prompt
    # prompt 应包含状态
    assert "HP=" in prompt
    assert "EP=" in prompt
    assert "calm" in prompt
    # prompt 应包含记忆
    assert "记忆事件" in prompt
    # prompt 应包含反思
    assert "反思" in prompt
    assert "越来越熟悉" in prompt
    # prompt 应包含世界状态
    assert "sunny" in prompt
    # 模型应该是 HAIKU
    assert call.model == LlmModel.HAIKU
    assert call.max_tokens == 100

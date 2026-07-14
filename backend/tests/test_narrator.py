"""Phase 14: 世界叙事系统测试。

测试 NarratorSystem 单例、事件收集、LLM 叙事生成、API 端点。
"""
from __future__ import annotations

import pytest


def test_narrator_singleton():
    """验证 NarratorSystem 单例模式。"""
    from digimon_world.world.narrator import get_narrator, NarratorSystem, reset_narrator

    reset_narrator()
    n1 = get_narrator()
    n2 = get_narrator()
    assert n1 is n2
    assert isinstance(n1, NarratorSystem)
    assert n1.journal == []
    assert n1.narration_interval == 100
    assert n1._tick_counter == 0
    assert n1._last_narrated_at == 0


def test_narrator_tick_skips_when_not_interval():
    """验证 tick 在未到间隔时不采集事件。"""
    from digimon_world.world.narrator import get_narrator, NarratorSystem
    from digimon_world.world import reset_narrator

    reset_narrator()
    n = get_narrator()
    # 前 99 tick 应该跳过
    for _ in range(99):
        n.tick(world=None, timeline_system=None)
    assert n._tick_counter == 99
    assert n.journal == []
    # 第 100 tick 触发
    n.tick(world=None, timeline_system=None)
    assert n._tick_counter == 100
    # 没有 world 时应该不会崩溃,也不会添加叙事


def test_narrator_interval_custom():
    """验证可自定义叙事间隔。"""
    from digimon_world.world.narrator import NarratorSystem

    n = NarratorSystem(interval=50)
    assert n.narration_interval == 50


def test_reset_narrator():
    """验证 reset 函数。"""
    from digimon_world.world.narrator import (
        get_narrator,
        reset_narrator,
    )

    n1 = get_narrator()
    assert n1 is not None
    reset_narrator()
    n2 = get_narrator()
    assert n2 is not None
    assert n1 is not n2


def test_collect_context_basic():
    """验证 _collect_context 统计各类型事件。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator
    from digimon_world.world.world_state import get_world, reset_world

    reset_world()
    reset_narrator()
    n = NarratorSystem()
    world = get_world()

    # 构造时间线条目 (模拟 TimelineSystem.build 的输出格式)
    timeline_entries = [
        {"type": "evolution", "icon": "✨", "title": "亚古兽进化暴龙兽", "importance": 9},
        {"type": "battle", "icon": "⚔️", "title": "暴龙兽 vs 恶魔兽", "importance": 8},
        {"type": "battle", "icon": "⚔️", "title": "加布兽 vs 邪龙兽", "importance": 7},
        {"type": "story_event", "icon": "📜", "title": "黑暗齿轮出现", "importance": 8},
        {"type": "first_meet", "icon": "🤝", "title": "巴鲁兽遇到哥玛兽", "importance": 5},
        {"type": "disaster", "icon": "🌋", "title": "火山爆发", "importance": 9},
    ]

    ctx = n._collect_context(world, timeline_entries)
    assert "events" in ctx
    assert ctx["evolution_count"] == 1
    assert ctx["battle_count"] == 2
    assert len(ctx["story_events"]) == 1
    assert len(ctx["first_meets"]) == 1
    assert ctx["disaster_count"] == 1
    assert ctx["agent_count"] == world.count()
    assert ctx["tick"] == n._tick_counter
    # 验证按重要性排序: 最高 importance 的事件应该在前
    assert ctx["events"][0]["importance"] >= ctx["events"][-1]["importance"]


def test_collect_context_empty():
    """验证空事件列表不崩溃。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator
    from digimon_world.world.world_state import get_world, reset_world

    reset_world()
    reset_narrator()
    n = NarratorSystem()
    world = get_world()

    ctx = n._collect_context(world, [])
    assert ctx["events"] == []
    assert ctx["evolution_count"] == 0
    assert ctx["battle_count"] == 0
    assert ctx["disaster_count"] == 0
    assert ctx["story_events"] == []
    assert ctx["first_meets"] == []


def test_compose_sync():
    """验证 _compose (同步版本) 返回正确的结构。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator

    reset_narrator()
    n = NarratorSystem()
    n._tick_counter = 100
    context = {
        "tick": 100,
        "agent_count": 30,
        "events": [],
        "evolution_count": 1,
        "battle_count": 2,
        "disaster_count": 0,
    }
    result = n._compose(context)
    assert "story" in result
    assert "title" in result
    assert "events_count" in result
    assert result["evolution_count"] == 1
    assert result["battle_count"] == 2
    assert result["tick"] == 100
    assert isinstance(result["story"], str)
    assert len(result["story"]) > 0


def test_narration_count_property():
    """验证 narration_count 属性。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator

    reset_narrator()
    n = NarratorSystem()
    assert n.narration_count == 0
    n.journal.append({"tick": 100, "title": "test", "story": "test"})
    assert n.narration_count == 1


@pytest.mark.asyncio
async def test_compose_async_fallback():
    """验证 _compose_async 在 FakeLlM 环境下工作 (回退到同步版本)。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator

    reset_narrator()
    n = NarratorSystem()
    context = {
        "tick": 500,
        "agent_count": 30,
        "events": [
            {"type": "evolution", "icon": "✨", "title": "亚古兽进化暴龙兽", "importance": 9},
            {"type": "battle", "icon": "⚔️", "title": "暴龙兽 vs 恶魔兽", "importance": 8},
        ],
        "evolution_count": 1,
        "battle_count": 1,
        "disaster_count": 0,
    }
    result = await n._compose_async(context)
    assert "story" in result
    assert "title" in result
    assert "events_count" in result
    assert result["evolution_count"] == 1
    assert result["battle_count"] == 1
    assert result["tick"] == 500


@pytest.mark.asyncio
async def test_compose_async_with_fake_llm():
    """验证 _compose_async 用 FakeLlmClient 正确解析 LLM 响应。"""
    from digimon_world.llm.client import (
        FakeLlmClient,
        LlmModel,
        set_client,
        get_client,
    )
    from digimon_world.world.narrator import NarratorSystem, reset_narrator

    # 注入 FakeClient 预设叙事回复
    fake = FakeLlmClient()
    fake.set_reply(
        model=LlmModel.MINIMAX_TEXT_01,
        contains="数码世界的说书人",
        reply="标题: 进化之光\n摘要: 亚古兽绽放出耀眼的光芒,进化成了暴龙兽!与此同时,暴龙兽与恶魔兽展开激烈战斗。",
    )
    set_client(fake)

    reset_narrator()
    n = NarratorSystem()
    context = {
        "tick": 800,
        "agent_count": 30,
        "events": [
            {"type": "evolution", "icon": "✨", "title": "亚古兽进化暴龙兽", "importance": 9},
            {"type": "battle", "icon": "⚔️", "title": "暴龙兽 vs 恶魔兽", "importance": 8},
        ],
        "evolution_count": 1,
        "battle_count": 1,
        "disaster_count": 0,
    }

    result = await n._compose_async(context)
    assert result["title"] == "进化之光"
    assert "亚古兽" in result["story"]
    assert result["events_count"] == 2
    assert result["evolution_count"] == 1

    # 还原
    set_client(get_client())


@pytest.mark.asyncio
async def test_tick_async_with_world():
    """验证 tick_async 在有 world 和 timeline 时触发叙事。"""
    from digimon_world.llm.client import (
        FakeLlmClient,
        LlmModel,
        set_client,
    )
    from digimon_world.world.narrator import (
        NarratorSystem,
        reset_narrator,
    )
    from digimon_world.world.timeline import TimelineSystem
    from digimon_world.world.world_state import get_world, reset_world

    # 注入 FakeClient
    fake = FakeLlmClient()
    fake.set_reply(
        model=LlmModel.MINIMAX_TEXT_01,
        contains="数码世界的说书人",
        reply="标题: 测试叙事\n摘要: 测试故事内容。",
    )
    set_client(fake)

    reset_world()
    reset_narrator()
    n = NarratorSystem(interval=1)  # 每 tick 都触发
    world = get_world()
    timeline = TimelineSystem()

    # 注入一个进化事件到 world.events
    world.events.append({
        "type": "evolution",
        "description": "亚古兽进化暴龙兽",
        "importance": 9,
    })

    assert n.narration_count == 0
    assert n._tick_counter == 0

    result = await n.tick_async(world, timeline)
    assert result is not None
    assert n.narration_count == 1
    assert "story" in n.journal[0]

    # 还原
    set_client(FakeLlmClient())


@pytest.mark.asyncio
async def test_compose_async_empty_events():
    """验证 _compose_async 在空事件列表时仍能工作。"""
    from digimon_world.llm.client import (
        FakeLlmClient,
        LlmModel,
        set_client,
    )
    from digimon_world.world.narrator import NarratorSystem, reset_narrator

    fake = FakeLlmClient()
    fake.set_reply(
        model=LlmModel.MINIMAX_TEXT_01,
        contains="数码世界的说书人",
        reply="标题: 平静之日\n摘要: 数码世界今天很平静。",
    )
    set_client(fake)

    reset_narrator()
    n = NarratorSystem()
    context = {
        "tick": 200,
        "agent_count": 30,
        "events": [],
        "evolution_count": 0,
        "battle_count": 0,
        "disaster_count": 0,
    }

    result = await n._compose_async(context)
    assert "story" in result
    assert result["events_count"] == 0

    set_client(FakeLlmClient())


@pytest.mark.asyncio
async def test_scheduler_integration_no_crash():
    """验证 Scheduler tick_once 在加入 _process_narrative 后不崩溃。"""
    from digimon_world.llm.client import FakeLlmClient, set_client
    from digimon_world.world.clock import WorldClock
    from digimon_world.world.narrator import reset_narrator, NarratorSystem
    from digimon_world.world.scheduler import WorldScheduler
    from digimon_world.world.world_state import get_world, reset_world

    # 用 FakeLlmClient 避免真实 LLM 调用
    set_client(FakeLlmClient(default_reply="标题: 测试\n摘要: 测试故事"))

    reset_world()
    reset_narrator()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)

    # 注入一个事件,确保有素材
    world.events.append({
        "type": "evolution",
        "description": "test evolution",
        "importance": 9,
    })

    # 用 interval=1 确保首次 tick 就触发
    NarratorSystem(interval=1)  # 切换单例
    reset_narrator()
    # 重新设置小间隔
    from digimon_world.world.narrator import _narrator
    from digimon_world.world.narrator import NarratorSystem as NS
    import digimon_world.world.narrator as narratormod
    narratormod._narrator = NS(interval=1)

    scheduler = WorldScheduler(world=world, clock=clock)

    # tick_once 不应崩溃
    events = await scheduler.tick_once(real_seconds=1.0)
    assert events is not None
    # 不应抛出异常

    set_client(FakeLlmClient())


# ---- Phase 14: API 端点测试 ----
def test_get_narratives_empty():
    """测试 /api/narratives 在无叙事时返回空列表。"""
    from fastapi.testclient import TestClient
    from digimon_world.api.app import app
    from digimon_world.world.narrator import reset_narrator

    reset_narrator()
    client = TestClient(app)
    resp = client.get("/api/narratives")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["entries"] == []


def test_get_narratives_latest_404():
    """测试 /api/narratives/latest 在无叙事时返回 404。"""
    from fastapi.testclient import TestClient
    from digimon_world.api.app import app
    from digimon_world.world.narrator import reset_narrator

    reset_narrator()
    client = TestClient(app)
    resp = client.get("/api/narratives/latest")
    assert resp.status_code == 404
    data = resp.json()
    assert "No narratives yet" in data["detail"]


def test_get_narratives_with_data():
    """测试 /api/narratives 和 /latest 在有叙事时返回数据。"""
    from fastapi.testclient import TestClient
    from digimon_world.api.app import app
    from digimon_world.world.narrator import reset_narrator, get_narrator

    reset_narrator()
    n = get_narrator()
    n.journal.append({
        "tick": 100,
        "title": "进化之光",
        "story": "亚古兽进化成了暴龙兽！",
        "events_count": 3,
        "evolution_count": 1,
        "battle_count": 1,
    })
    n.journal.append({
        "tick": 200,
        "title": "黑暗降临",
        "story": "黑暗齿轮感染了数码世界……",
        "events_count": 5,
        "evolution_count": 0,
        "battle_count": 3,
    })

    client = TestClient(app)

    # /api/narratives
    resp = client.get("/api/narratives")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["entries"]) == 2

    # /api/narratives?limit=1
    resp = client.get("/api/narratives?limit=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 1

    # /api/narratives/latest
    resp = client.get("/api/narratives/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "黑暗降临"
    assert data["tick"] == 200
    assert "story" in data

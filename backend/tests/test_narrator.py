"""Phase 14: 世界叙事系统测试。

测试 NarratorSystem 单例、事件收集、LLM 叙事生成、API 端点。
"""
from __future__ import annotations


def test_narrator_singleton():
    """验证 NarratorSystem 单例模式。"""
    from digimon_world.world.narrator import get_narrator, NarratorSystem

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

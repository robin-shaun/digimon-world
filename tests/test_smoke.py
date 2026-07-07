"""Smoke test: 验证 digimon_world 包能 import,基本数据结构能工作。"""

from datetime import datetime

import pytest

from digimon_world import __version__
from digimon_world.agents import DigimonAgent
from digimon_world.agents.digimon_agent import DigimonAttribute, EvolutionStage
from digimon_world.memory import MemoryNode, MemoryStream


def test_version():
    assert __version__ == "0.1.0"


def test_digimon_agent_creation():
    """一只亚古兽应该能创建出来。"""
    agumon = DigimonAgent(name="亚古兽", species="agumon")
    assert agumon.name == "亚古兽"
    assert agumon.stage == EvolutionStage.ROOKIE
    assert agumon.attribute == DigimonAttribute.VACCINE
    assert agumon.stats.hp == 100
    assert len(agumon.memory.entries) == 0


def test_digimon_observe_writes_memory():
    """观察事件应该写入记忆流。"""
    agumon = DigimonAgent(name="亚古兽", species="agumon")
    agumon.observe({"type": "first_meet", "description": "遇到了太一"})
    assert len(agumon.memory.entries) == 1
    assert agumon.memory.entries[0].description == "遇到了太一"
    # first_meet 启发式评 7 分
    assert agumon.memory.entries[0].importance == 7


def test_memory_stream_retrieve():
    """检索应该返回评分最高的记忆。"""
    stream = MemoryStream()
    stream.add("在沙滩上遇到了太一", importance=8)
    stream.add("吃了一块肉", importance=3)
    stream.add("经历了第一次战斗胜利", importance=9)

    # 关键词"战斗"
    results = stream.retrieve("战斗", top_k=2)
    assert len(results) >= 1
    # 重要性最高的那条应该排第一
    assert "战斗" in results[0].description


def test_digimon_serialization_roundtrip():
    """序列化应该可逆。"""
    agumon = DigimonAgent(name="加布兽", species="gabumon")
    agumon.observe({"type": "moved", "description": "向北移动了 10 步"})

    data = agumon.to_dict()
    assert data["name"] == "加布兽"
    assert data["stage"] == "rookie"
    assert data["attribute"] == "vaccine"
    assert len(data["memory"]) == 1


def test_evolution_stage_enum():
    """5 个进化阶段应该齐全。"""
    stages = [s.value for s in EvolutionStage]
    assert stages == ["baby_i", "baby_ii", "rookie", "champion", "mega"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

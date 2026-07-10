"""
SQLite 持久化测试
=================

覆盖 3 个 roundtrip:
- 数码兽全量 save + load(数值 / 位置 / 阶段 / 属性 / 战绩完整)
- 记忆 save + load(时间戳 / 描述 / 重要性 / 类型 / node_id 完整)
- 关系 save + load(对称分数完整)

每个测试用独立临时 db 文件,互不干扰。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest

from digimon_world.agents.digimon_agent import (
    DigimonAgent,
    DigimonAttribute,
    DigimonStats,
    EvolutionStage,
)
from digimon_world.world import persistence
from digimon_world.world.relationships import RelationshipTracker
from digimon_world.world.world_state import WorldState


@pytest.fixture
def db_path():
    """临时数据库文件路径,测试结束自动清理。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # persistence 自己建;这里只借用一个唯一路径
    yield path
    if os.path.exists(path):
        os.remove(path)


# ---- 1. 数码兽 roundtrip ----


async def test_digimon_roundtrip(db_path: str) -> None:
    """save 一个装了数码兽的世界,load 到新世界,agent 字段完整。"""
    src = WorldState()
    agent = DigimonAgent(
        name="亚古兽",
        species="agumon",
        stage=EvolutionStage.CHAMPION,
        attribute=DigimonAttribute.VACCINE,
        region_id="file_island",
        location=(123, 456),
        stats=DigimonStats(hp=88, ep=42, attack=30, defense=18, speed=22, bond=17),
        current_plan="去进化神殿看看",
        mood="excited",
        battle_victories=3,
    )
    src.spawn(agent)
    tracker = RelationshipTracker()

    await persistence.save(src, tracker, db_path)

    dst = WorldState()
    dst.agents.clear()  # 去掉默认地区没有的 agent(WorldState 默认不塞 agent,这里保险)
    ok = await persistence.load(dst, RelationshipTracker(), db_path)

    assert ok is True
    loaded = dst.get("亚古兽")
    assert loaded is not None
    assert loaded.species == "agumon"
    assert loaded.stage == EvolutionStage.CHAMPION
    assert loaded.attribute == DigimonAttribute.VACCINE
    assert loaded.region_id == "file_island"
    assert loaded.location == (123, 456)
    assert loaded.stats.hp == 88
    assert loaded.stats.ep == 42
    assert loaded.stats.attack == 30
    assert loaded.stats.defense == 18
    assert loaded.stats.speed == 22
    assert loaded.stats.bond == 17
    assert loaded.mood == "excited"
    assert loaded.battle_victories == 3
    assert loaded.current_plan == "去进化神殿看看"
    # 隐性欲望 / 渴望强度持久化
    assert loaded.latent_desire == ""
    assert loaded.desire_strength == 0.0


# ---- 2. 记忆 roundtrip ----


async def test_memories_roundtrip(db_path: str) -> None:
    """记忆流全量 save + load,每条 node 字段完整,顺序与 node_id 保持。"""
    src = WorldState()
    agent = DigimonAgent(name="加布兽", species="gabumon")
    agent.memory.add({"description": "在沙滩醒来"}, importance=4, memory_type="observation")
    agent.memory.add({"description": "遇到亚古兽"}, importance=7, memory_type="observation")
    agent.memory.add("我应该多交朋友", importance=8, memory_type="reflection")
    src.spawn(agent)

    await persistence.save(src, RelationshipTracker(), db_path)

    dst = WorldState()
    await persistence.load(dst, RelationshipTracker(), db_path)

    loaded = dst.get("加布兽")
    assert loaded is not None
    entries = loaded.memory.entries
    assert len(entries) == 3

    assert entries[0].description == "在沙滩醒来"
    assert entries[0].importance == 4
    assert entries[0].memory_type == "observation"
    assert entries[0].node_id == 0
    assert isinstance(entries[0].timestamp, datetime)

    assert entries[1].description == "遇到亚古兽"
    assert entries[1].importance == 7

    assert entries[2].description == "我应该多交朋友"
    assert entries[2].memory_type == "reflection"
    assert entries[2].node_id == 2

    # next_id 续到 max node_id + 1,新记忆不撞 id
    assert loaded.memory.next_id == 3
    new_node = loaded.memory.add("新记忆", importance=5)
    assert new_node.node_id == 3


# ---- 3. 关系 roundtrip ----


async def test_relationships_roundtrip(db_path: str) -> None:
    """关系表全量 save + load,双向对称分数完整。"""
    src = WorldState()
    # 关系表需要 agent 存在才有意义,但 save 只导出 tracker,这里塞不塞都行
    tracker = RelationshipTracker()
    tracker.update("亚古兽", "加布兽", 15.0)
    tracker.update("亚古兽", "暴龙兽", -8.0)
    tracker.update("加布兽", "暴龙兽", 3.0)

    await persistence.save(src, tracker, db_path)

    dst_tracker = RelationshipTracker()
    await persistence.load(WorldState(), dst_tracker, db_path)

    # 分数完整
    assert dst_tracker.get_relationship("亚古兽", "加布兽") == 15.0
    assert dst_tracker.get_relationship("亚古兽", "暴龙兽") == -8.0
    assert dst_tracker.get_relationship("加布兽", "暴龙兽") == 3.0

    # 对称: 反向查一致
    assert dst_tracker.get_relationship("加布兽", "亚古兽") == 15.0
    assert dst_tracker.get_relationship("暴龙兽", "亚古兽") == -8.0

    # 未记录的对仍是 0
    assert dst_tracker.get_relationship("亚古兽", "暴龙兽666") == 0.0


# ---- 4. load 不存在的库 → False(健壮性) ----


async def test_load_missing_db_returns_false(db_path: str) -> None:
    """库文件不存在时 load 返回 False,不抛异常。"""
    assert not os.path.exists(db_path)
    ok = await persistence.load(WorldState(), RelationshipTracker(), db_path)
    assert ok is False


async def test_latent_desire_roundtrip(db_path: str) -> None:
    """隐性欲望字段(save/load)完整保留。"""
    src = WorldState()
    agent = DigimonAgent(
        name="暴龙兽",
        species="greymon",
        latent_desire="想守护领土",
        desire_strength=0.85,
    )
    src.spawn(agent)
    tracker = RelationshipTracker()

    await persistence.save(src, tracker, db_path)

    dst = WorldState()
    await persistence.load(dst, RelationshipTracker(), db_path)

    loaded = dst.get("暴龙兽")
    assert loaded is not None
    assert loaded.latent_desire == "想守护领土"
    assert loaded.desire_strength == 0.85

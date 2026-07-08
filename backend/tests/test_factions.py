"""
派系系统测试
============

覆盖:
- 自动派系形成(关系 > 30 的传递闭包并入同一派系)
- 导演注入创建命名派系(inject_faction / faction_create API)
- 敌对度计算(跨派成员平均关系 * -1)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from digimon_world.api import app as fastapi_app
from digimon_world.world import get_world, reset_world
from digimon_world.world.factions import (
    EMERGENCE_THRESHOLD,
    FactionRegistry,
)
from digimon_world.world.factions import reset_registry
from digimon_world.world.relationships import RelationshipTracker, reset_tracker


# ---- 1. 自动派系形成 ----


def test_form_factions_emergence() -> None:
    """关系 > 30 的成员自动归入同一派系,含传递闭包。"""
    rt = RelationshipTracker()
    # 亚古兽 - 加布兽 强关系
    rt.update("亚古兽", "加布兽", 40)
    # 加布兽 - 比丘兽 强关系 → 传递: 亚古兽/加布兽/比丘兽 同派
    rt.update("加布兽", "比丘兽", 35)
    # 独立的一对: 暴龙兽 - 钢铁兽
    rt.update("暴龙兽", "钢铁兽", 50)
    # 弱关系(< 阈值)不成派系
    rt.update("孤独兽A", "孤独兽B", 10)

    reg = FactionRegistry()
    factions = reg.form_factions(rt)

    # 两个自动派系
    assert len(factions) == 2

    # 亚古兽那一派含三只(传递闭包)
    agu_fid = reg.faction_of("亚古兽")
    assert agu_fid is not None
    assert set(reg.get_faction_members(agu_fid)) == {"亚古兽", "加布兽", "比丘兽"}

    # 暴龙兽那一派含两只
    grey_fid = reg.faction_of("暴龙兽")
    assert set(reg.get_faction_members(grey_fid)) == {"暴龙兽", "钢铁兽"}

    # 弱关系的孤独兽无派系归属
    assert reg.faction_of("孤独兽A") is None
    # 阈值边界: 恰好等于阈值不算(需严格大于)
    assert EMERGENCE_THRESHOLD == 30.0


# ---- 2. 导演注入创建派系 ----


def test_director_inject_creates_faction() -> None:
    """POST /api/director/inject_event type='faction_create' → 派系登记处出现新派系。"""
    reset_world()
    reset_tracker()
    reset_registry()
    get_world()
    client = TestClient(fastapi_app)

    r = client.post(
        "/api/director/inject_event",
        json={
            "type": "faction_create",
            "description": "黑暗四天王",
            "faction_id": "dark_masters",
            "members": "怪兽古拉兽,皮艾蒙",
        },
    )
    assert r.status_code == 200, r.text

    reg = fastapi_app_registry()
    faction = reg.get_faction("dark_masters")
    assert faction is not None
    assert faction.origin == "director"
    assert faction.name == "黑暗四天王"
    assert set(faction.members) == {"怪兽古拉兽", "皮艾蒙"}

    reset_world()
    reset_tracker()
    reset_registry()


def fastapi_app_registry() -> FactionRegistry:
    """取 API 侧共享的派系登记处单例。"""
    from digimon_world.world import get_registry

    return get_registry()


def test_form_factions_keeps_director_factions() -> None:
    """重算自动派系时,导演注入的派系(origin='director')不被冲掉。"""
    rt = RelationshipTracker()
    rt.update("A", "B", 40)

    reg = FactionRegistry()
    reg.inject_faction("dark_masters", ["某兽"], name="黑暗四天王")
    reg.form_factions(rt)

    # 导演派系仍在
    assert reg.get_faction("dark_masters") is not None
    # 自动派系也建起来了
    assert reg.faction_of("A") == "faction_A"


# ---- 3. 敌对度计算 ----


def test_faction_hostility() -> None:
    """两派敌对度 = 跨派成员平均关系 * -1。"""
    rt = RelationshipTracker()
    # 派系 X = {a1, a2}, 派系 Y = {b1}
    # 跨派关系: a1-b1 = -40, a2-b1 = -20 → 平均 -30 → 敌对度 +30
    rt.update("a1", "b1", -40)
    rt.update("a2", "b1", -20)

    reg = FactionRegistry()
    reg.inject_faction("X", ["a1", "a2"])
    reg.inject_faction("Y", ["b1"])

    hostility = reg.faction_hostility("X", "Y", rt)
    assert hostility == 30.0

    # 同一派系恒 0
    assert reg.faction_hostility("X", "X", rt) == 0.0
    # 不存在的派系 → 0
    assert reg.faction_hostility("X", "不存在", rt) == 0.0

    # 友好的两派 → 敌对度为负
    reg.inject_faction("P", ["p1"])
    reg.inject_faction("Q", ["q1"])
    rt.update("p1", "q1", 20)
    assert reg.faction_hostility("P", "Q", rt) == -20.0

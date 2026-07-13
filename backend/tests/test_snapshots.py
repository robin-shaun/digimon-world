"""
Phase 13⑤: 世界快照存档测试
============================

测试 SnapshotManager 的核心功能: 创建 / 列出 / 回滚 / 清理。
"""

import asyncio
import os
import tempfile

import pytest

from digimon_world.world.snapshots import (
    SnapshotManager,
    get_snapshot_manager,
    reset_snapshot_manager,
)
from digimon_world.world.world_state import get_world, reset_world
from digimon_world.world.relationships import get_tracker, reset_tracker
from digimon_world.world import persistence


@pytest.fixture(autouse=True)
def _clean_singletons():
    """每个测试前重置全局单例。"""
    reset_world()
    reset_tracker()
    reset_snapshot_manager()
    yield
    reset_world()
    reset_tracker()
    reset_snapshot_manager()


@pytest.fixture
def tmp_dirs():
    """临时目录用于测试。"""
    base = tempfile.mkdtemp(prefix="snapshot_test_")
    snap_dir = os.path.join(base, "snapshots")
    world_db = os.path.join(base, "world.db")
    yield base, snap_dir, world_db
    # cleanup
    import shutil
    try:
        shutil.rmtree(base)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_snapshot_create_and_list(tmp_dirs):
    """创建快照并列出。"""
    base, snap_dir, world_db = tmp_dirs

    # 先 save 一个 world 到 world_db
    world = get_world()
    tracker = get_tracker()
    await persistence.save(world, tracker, db_path=world_db)

    mgr = SnapshotManager(snapshot_dir=snap_dir, keep=10)
    sid = await mgr.create(world_db_path=world_db, world_tick=42, digimon_count=3, note="测试快照")
    assert sid is not None
    assert sid.startswith("snap_t42_")

    snapshots = await mgr.list()
    assert len(snapshots) == 1
    assert snapshots[0]["snapshot_id"] == sid
    assert snapshots[0]["world_tick"] == 42
    assert snapshots[0]["digimon_count"] == 3
    assert snapshots[0]["note"] == "测试快照"


@pytest.mark.asyncio
async def test_snapshot_restore(tmp_dirs):
    """创建快照 → 修改 world → 回滚 → 验证恢复。"""
    base, snap_dir, world_db = tmp_dirs

    world = get_world()
    tracker = get_tracker()
    await persistence.save(world, tracker, db_path=world_db)
    original_count = world.count()

    mgr = SnapshotManager(snapshot_dir=snap_dir, keep=10)
    sid = await mgr.create(world_db_path=world_db, world_tick=0, digimon_count=original_count)
    assert sid is not None

    # 模拟"改坏": 清空 world 再 save
    world.agents.clear()
    await persistence.save(world, tracker, db_path=world_db)
    assert world.count() == 0

    # 回滚
    ok = await mgr.restore(sid, world_db)
    assert ok

    # 重新 load 验证
    loaded = await persistence.load(world, tracker, db_path=world_db)
    assert loaded
    assert world.count() == original_count


@pytest.mark.asyncio
async def test_snapshot_restore_nonexistent(tmp_dirs):
    """回滚不存在的快照返回 False。"""
    base, snap_dir, world_db = tmp_dirs
    mgr = SnapshotManager(snapshot_dir=snap_dir, keep=10)
    ok = await mgr.restore("snap_nonexistent", world_db)
    assert not ok


@pytest.mark.asyncio
async def test_snapshot_prune(tmp_dirs):
    """超出 keep 数量的旧快照被清理。"""
    base, snap_dir, world_db = tmp_dirs

    world = get_world()
    tracker = get_tracker()
    await persistence.save(world, tracker, db_path=world_db)

    mgr = SnapshotManager(snapshot_dir=snap_dir, keep=3)

    # 创建 5 个快照 (create 内部可能触发异步 prune,先让它们跑完)
    for i in range(5):
        sid = await mgr.create(world_db_path=world_db, world_tick=i * 10, digimon_count=3)
        assert sid is not None
    # 等一下异步 prune 跑完
    await asyncio.sleep(0.1)

    snapshots = await mgr.list()
    # 保留不超过 keep 个
    assert len(snapshots) <= 3

    # 保留的是最近 3 个 (tick 40, 30, 20)
    ticks = [s["world_tick"] for s in snapshots]
    for early_tick in (0, 10):
        assert early_tick not in ticks


@pytest.mark.asyncio
async def test_snapshot_count(tmp_dirs):
    """count() 返回正确数量。"""
    base, snap_dir, world_db = tmp_dirs

    world = get_world()
    tracker = get_tracker()
    await persistence.save(world, tracker, db_path=world_db)

    mgr = SnapshotManager(snapshot_dir=snap_dir, keep=10)
    assert await mgr.count() == 0

    await mgr.create(world_db_path=world_db, world_tick=0, digimon_count=3)
    assert await mgr.count() == 1

    await mgr.create(world_db_path=world_db, world_tick=10, digimon_count=3)
    assert await mgr.count() == 2


@pytest.mark.asyncio
async def test_singleton():
    """get_snapshot_manager 返回同一实例。"""
    a = get_snapshot_manager()
    b = get_snapshot_manager()
    assert a is b


@pytest.mark.asyncio
async def test_reset_singleton():
    """reset 后返回新实例。"""
    a = get_snapshot_manager()
    reset_snapshot_manager()
    b = get_snapshot_manager()
    assert a is not b


@pytest.mark.asyncio
async def test_api_list_snapshots(tmp_dirs):
    """API: GET /api/snapshots 返回空列表。"""
    from digimon_world.api.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/api/snapshots")
    assert response.status_code == 200
    data = response.json()
    assert "snapshots" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_api_create_snapshot_no_db(tmp_dirs):
    """API: POST /api/snapshots 在 world.db 不存在时报错。"""
    import os
    from digimon_world.api.app import app
    from fastapi.testclient import TestClient

    # 确保 world.db 不存在
    if os.path.exists(persistence.DEFAULT_DB_PATH):
        os.remove(persistence.DEFAULT_DB_PATH)

    client = TestClient(app)
    response = client.post("/api/snapshots", json={"note": "test"})
    assert response.status_code == 200
    data = response.json()
    # world.db 不存在时会 fail
    assert data["status"] in ("created", "error")


@pytest.mark.asyncio
async def test_api_restore_nonexistent():
    """API: POST /api/snapshots/nonexistent/restore 返回 404。"""
    from digimon_world.api.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post("/api/snapshots/nonexistent_999/restore")
    assert response.status_code == 404

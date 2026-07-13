"""
Phase 13③: 健康检查 + 性能监控端点测试
========================================
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="function")
async def test_health_perf_endpoint() -> None:
    """验证 /api/health/perf 返回正确的结构和数据。"""
    from digimon_world.api.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/health/perf")

    assert resp.status_code == 200
    data = resp.json()

    # 结构校验
    assert "pid" in data
    assert isinstance(data["pid"], int)
    assert "python_version" in data
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))

    # 内存指标
    assert "memory" in data
    assert "rss_mb" in data["memory"]
    assert "rss_bytes" in data["memory"]

    # 数据库指标
    assert "database" in data
    assert "path" in data["database"]
    assert "size_mb" in data["database"]
    assert "size_bytes" in data["database"]

    # 世界状态
    assert "world" in data
    assert "agent_count" in data["world"]
    assert "total_memories" in data["world"]
    assert "event_count" in data["world"]
    assert "ws_connections" in data["world"]
    assert "clock_tick" in data["world"]

    # agent_count 应该是非负整数
    assert data["world"]["agent_count"] >= 0


@pytest.mark.asyncio(loop_scope="function")
async def test_health_perf_returns_different_uptime() -> None:
    """验证 uptime 向前推进。"""
    import time
    from digimon_world.api.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    resp1 = client.get("/api/health/perf").json()
    time.sleep(0.1)
    resp2 = client.get("/api/health/perf").json()

    # uptime 应该增大 (或至少不缩小)
    assert resp2["uptime_seconds"] >= resp1["uptime_seconds"]


@pytest.mark.asyncio(loop_scope="function")
async def test_persistence_indexes_applied() -> None:
    """验证打开数据库时索引和 PRAGMA 正确应用。"""
    import os
    import tempfile

    import aiosqlite
    from digimon_world.world.persistence import _INDEXES, _ensure_schema

    # 临时数据库
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        async with aiosqlite.connect(tmp.name) as db:
            await _ensure_schema(db)

            # 检查索引是否创建
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ) as cur:
                indexes = [row[0] async for row in cur]
            for idx_sql in _INDEXES:
                # SQL: "CREATE INDEX IF NOT EXISTS idx_name ON ..."
                parts = idx_sql.split()
                idx_name = parts[5] if "NOT EXISTS" in idx_sql else parts[2]  # handle both forms
                assert idx_name in indexes, f"Index {idx_name} not found: got {indexes}"

            # 检查 WAL 模式
            async with db.execute("PRAGMA journal_mode") as cur:
                row = await cur.fetchone()
                assert row is not None
                assert row[0] == "wal", f"Expected WAL mode, got {row[0]}"

            # 检查 synchronous
            async with db.execute("PRAGMA synchronous") as cur:
                row = await cur.fetchone()
                assert row is not None
                assert row[0] == 1, f"Expected synchronous=NORMAL (1), got {row[0]}"
    finally:
        os.unlink(tmp.name)

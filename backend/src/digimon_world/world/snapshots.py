"""
Snapshot Manager — 世界快照存档系统
=====================================

定时全量快照世界状态,支持列出/回滚。用独立 SQLite 文件存储快照元数据,
快照文件放在 data/snapshots/ 下。

设计要点:
- 快照 = 复制 world.db 到快照目录,元数据存入 snapshots_meta.db
- 可选版本标签 (schema_version) 供未来迁移
- auto_prune: 保留最近 N 个快照,删除多余的
- 回滚: 把快照文件复制回 world.db

Phase 13⑤: 定时快照 + 版本迁移 + 回滚
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from datetime import datetime
from typing import TypedDict

import aiosqlite

logger = logging.getLogger(__name__)

# 快照目录 (相对于进程 cwd,即项目根)
DEFAULT_SNAPSHOT_DIR = os.path.join("data", "snapshots")
DEFAULT_META_DB = os.path.join(DEFAULT_SNAPSHOT_DIR, "snapshots_meta.db")

# 默认保留最近 N 个快照
DEFAULT_KEEP = 20

# 快照元数据 DDL
_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL UNIQUE,
    world_tick  INTEGER NOT NULL DEFAULT 0,
    digimon_count INTEGER NOT NULL DEFAULT 0,
    file_path   TEXT NOT NULL,
    file_size   INTEGER NOT NULL DEFAULT 0,
    schema_version TEXT NOT NULL DEFAULT '1',
    created_at  TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT ''
);
"""


class SnapshotMeta(TypedDict):
    snapshot_id: str
    world_tick: int
    digimon_count: int
    file_path: str
    file_size: int
    schema_version: str
    created_at: str
    note: str


class SnapshotManager:
    """世界快照管理器 — 创建 / 列出 / 回滚 / 清理。"""

    def __init__(
        self,
        snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
        meta_db_path: str | None = None,
        keep: int = DEFAULT_KEEP,
    ) -> None:
        self._dir = snapshot_dir
        self._meta_db = meta_db_path if meta_db_path is not None else os.path.join(snapshot_dir, "snapshots_meta.db")
        self._keep = keep

    # ── 公开 API ──────────────────────────────────────────────

    async def create(
        self,
        world_db_path: str,
        world_tick: int = 0,
        digimon_count: int = 0,
        note: str = "",
        schema_version: str = "1",
    ) -> str | None:
        """从 world_db_path 创建快照,返回 snapshot_id (失败返回 None)。

        流程:
        1. 确保快照目录存在 + 元数据 DB schema
        2. 生成 snapshot_id (tick+timestamp)
        3. 复制 world_db → 快照目录
        4. 写入元数据表
        5. auto_prune 清理旧快照
        """
        try:
            os.makedirs(self._dir, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_id = f"snap_t{world_tick}_{ts}"
            dest = os.path.join(self._dir, f"{snapshot_id}.db")

            # 复制 (同步,文件操作很快;源文件大时放后台线程)
            await asyncio.to_thread(shutil.copy2, world_db_path, dest)
            file_size = os.path.getsize(dest)

            # 写入元数据
            async with aiosqlite.connect(self._meta_db) as db:
                await db.execute(_META_SCHEMA)
                await db.execute(
                    "INSERT INTO snapshots "
                    "(snapshot_id, world_tick, digimon_count, file_path, file_size, schema_version, created_at, note) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        snapshot_id,
                        world_tick,
                        digimon_count,
                        dest,
                        file_size,
                        schema_version,
                        datetime.now().isoformat(),
                        note,
                    ),
                )
                await db.commit()

            logger.info(
                "snapshot %s created (tick=%d, digimons=%d, size=%d)",
                snapshot_id, world_tick, digimon_count, file_size,
            )

            # 异步清理旧快照 (不影响主流程)
            asyncio.create_task(self._auto_save_loop())  # noqa: RUF006

            return snapshot_id

        except Exception as e:
            logger.warning("snapshot create failed: %s", e)
            return None

    async def list(self) -> list[SnapshotMeta]:
        """列出所有快照 (按创建时间降序)。"""
        try:
            async with aiosqlite.connect(self._meta_db) as db:
                await db.execute(_META_SCHEMA)
                db.row_factory = aiosqlite.Row
                rows: list[SnapshotMeta] = []
                async with db.execute(
                    "SELECT snapshot_id, world_tick, digimon_count, file_path, "
                    "file_size, schema_version, created_at, note "
                    "FROM snapshots ORDER BY created_at DESC LIMIT 100"
                ) as cur:
                    async for row in cur:
                        rows.append(SnapshotMeta(
                            snapshot_id=row["snapshot_id"],
                            world_tick=row["world_tick"],
                            digimon_count=row["digimon_count"],
                            file_path=row["file_path"],
                            file_size=row["file_size"],
                            schema_version=row["schema_version"],
                            created_at=row["created_at"],
                            note=row["note"],
                        ))
                return rows
        except Exception as e:
            logger.warning("snapshot list failed: %s", e)
            return []

    async def restore(self, snapshot_id: str, world_db_path: str) -> bool:
        """从 snapshot_id 回滚到 world_db_path。返回是否成功。

        流程:
        1. 从元数据查快照文件路径
        2. 校验快照文件存在
        3. 复制快照 → world_db (覆盖)
        """
        try:
            # 查元数据
            async with aiosqlite.connect(self._meta_db) as db:
                await db.execute(_META_SCHEMA)
                async with db.execute(
                    "SELECT file_path FROM snapshots WHERE snapshot_id = ?",
                    (snapshot_id,),
                ) as cur:
                    row = await cur.fetchone()
                    if row is None:
                        logger.warning("snapshot %s not found in meta", snapshot_id)
                        return False
                    src = row[0]

            if not os.path.exists(src):
                logger.warning("snapshot file %s not found", src)
                return False

            # 确保目标目录存在
            os.makedirs(os.path.dirname(world_db_path), exist_ok=True)

            # 复制回 world_db
            await asyncio.to_thread(shutil.copy2, src, world_db_path)
            logger.info("world restored from snapshot %s", snapshot_id)
            return True

        except Exception as e:
            logger.warning("snapshot restore failed: %s", e)
            return False

    async def count(self) -> int:
        """快照总数。"""
        try:
            async with aiosqlite.connect(self._meta_db) as db:
                await db.execute(_META_SCHEMA)
                async with db.execute("SELECT COUNT(*) FROM snapshots") as cur:
                    row = await cur.fetchone()
                    return row[0] if row else 0
        except Exception:
            return 0

    async def _prune(self) -> int:
        """清理旧快照: 保留最近 self._keep 个,删除多余的文件和元数据。返回删除数量。"""
        try:
            async with aiosqlite.connect(self._meta_db) as db:
                await db.execute(_META_SCHEMA)

                # 找出需要删除的 snapshot_ids
                async with db.execute(
                    "SELECT snapshot_id, file_path FROM snapshots "
                    "ORDER BY created_at DESC"
                ) as cur:
                    raw = await cur.fetchall()
                    all_rows: list[tuple[str, str]] = [(r[0], r[1]) for r in raw]

                if len(all_rows) <= self._keep:
                    return 0

                to_delete = all_rows[self._keep:]
                deleted = 0
                for snap_id, file_path in to_delete:
                    # 删文件
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except OSError as e:
                            logger.warning("failed to remove snapshot file %s: %s", file_path, e)
                    # 删元数据
                    await db.execute("DELETE FROM snapshots WHERE snapshot_id = ?", (snap_id,))
                    deleted += 1

                await db.commit()

            if deleted:
                logger.info("pruned %d old snapshot(s)", deleted)
            return deleted

        except Exception as e:
            logger.warning("snapshot prune failed: %s", e)
            return 0


# 进程级单例
_snapshot_mgr: SnapshotManager | None = None


def get_snapshot_manager() -> SnapshotManager:
    """获取进程级 SnapshotManager 单例。"""
    global _snapshot_mgr
    if _snapshot_mgr is None:
        _snapshot_mgr = SnapshotManager()
    return _snapshot_mgr


def reset_snapshot_manager() -> None:
    """重置单例 (测试用)。"""
    global _snapshot_mgr
    _snapshot_mgr = None

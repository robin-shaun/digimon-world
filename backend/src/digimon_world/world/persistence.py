"""
Persistence - SQLite 持久化
===========================

把内存中的世界状态(WorldState + RelationshipTracker)全量落盘到 SQLite,
以及从 SQLite 全量恢复。异步实现,用 aiosqlite。

设计要点:
- 单文件数据库,默认 data/world.db(相对进程 cwd);目录不存在自动建。
- 全量 save / load:save 先清表再写,load 先清内存再灌;不做增量 diff
  (Phase 4 世界规模小,几十只数码兽,全量最简单且不易出错)。
- 只持久化"会变"的数据:数码兽、记忆、关系、事件、世界元数据(world_time / ratio)。
  地区(Region)是静态内置数据,不落盘。
- scheduler 每 100 tick 自动 save 一次(见 WorldScheduler)。

表:
- digimons     — 每只数码兽一行(数值 + 位置 + 计划)
- memories     — 每条记忆一行(外键 agent_name)
- relationships— 每对关系一行(agent_a <= agent_b)
- events       — 世界事件日志(type / description / at)
- world_meta   — 键值对(world_time / real_to_world_ratio)

详细设计: docs/DESIGN.md 第 2 节
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

import aiosqlite

from ..agents.digimon_agent import (
    DigimonAgent,
    DigimonAttribute,
    DigimonStats,
    EvolutionStage,
)
from ..memory.memory_stream import MemoryNode, MemoryStream
from .relationships import RelationshipVector, _key

if TYPE_CHECKING:
    from .relationships import RelationshipTracker
    from .world_state import WorldState

logger = logging.getLogger(__name__)

# 默认数据库路径(相对进程 cwd)。data/ 已在 .gitignore。
DEFAULT_DB_PATH = os.path.join("data", "world.db")

# 建表 DDL(幂等,IF NOT EXISTS)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS digimons (
    name             TEXT PRIMARY KEY,
    species          TEXT NOT NULL,
    stage            TEXT NOT NULL,
    attribute        TEXT NOT NULL,
    region_id        TEXT NOT NULL,
    x                INTEGER NOT NULL,
    y                INTEGER NOT NULL,
    hp               INTEGER NOT NULL,
    ep               INTEGER NOT NULL,
    attack           INTEGER NOT NULL,
    defense          INTEGER NOT NULL,
    speed            INTEGER NOT NULL,
    bond             INTEGER NOT NULL,
    mood             TEXT NOT NULL,
    mood_state       TEXT NOT NULL DEFAULT '{}',
    battle_victories INTEGER NOT NULL,
    current_plan     TEXT,
    latent_desire    TEXT NOT NULL DEFAULT '',
    desire_strength  REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS memories (
    agent_name  TEXT NOT NULL,
    node_id     INTEGER,
    timestamp   TEXT NOT NULL,
    description TEXT NOT NULL,
    importance  INTEGER NOT NULL,
    memory_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    score   REAL NOT NULL,          -- 综合倾向分(向后兼容)
    affinity REAL NOT NULL DEFAULT 0.0,
    rivalry  REAL NOT NULL DEFAULT 0.0,
    respect  REAL NOT NULL DEFAULT 0.0,
    fear     REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (agent_a, agent_b)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT,
    description TEXT,
    at          TEXT
);

CREATE TABLE IF NOT EXISTS world_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Phase 13③: Performance indexes for common query patterns
_INDEXES = [
    # memories: 按 agent 查询是最频繁的操作 (load 时按 agent_name 分组排序)
    "CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_name, node_id);",
    # memories: 按时间范围查询 (未来可能需要)
    "CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp);",
    # events: 按类型查询 (前端按类型筛选事件)
    "CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);",
    # events: 按时间排序查询 (最近 N 条事件)
    "CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);",
    # relationships: 从任一方向查找关系 (单 agent 详情页)
    "CREATE INDEX IF NOT EXISTS idx_relationships_a ON relationships(agent_a);",
    "CREATE INDEX IF NOT EXISTS idx_relationships_b ON relationships(agent_b);",
]

# Phase 13③: SQLite PRAGMA optimizations for performance
PRAGMA_OPTIMIZE = [
    "PRAGMA journal_mode=WAL;",       # Write-Ahead Logging: 读写不互斥, 大幅提升并发
    "PRAGMA synchronous=NORMAL;",      # 正常同步 (WAL 模式下安全, 比 FULL 快 10-50x)
    "PRAGMA cache_size=-64000;",       # 64MB 页缓存 (适合 175MB+ 数据库)
    "PRAGMA mmap_size=268435456;",     # 256MB 内存映射 (大库加速)
    "PRAGMA temp_store=MEMORY;",       # 临时表放内存
    "PRAGMA busy_timeout=5000;",       # 5s 忙等待 (减少 "database is locked")
]


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    """建表 + 索引 + 性能优化(幂等)。"""
    await db.executescript(_SCHEMA)
    # Phase 13③: Apply indexes and PRAGMA optimizations
    for idx_sql in _INDEXES:
        await db.execute(idx_sql)
    for pragma_sql in PRAGMA_OPTIMIZE:
        await db.execute(pragma_sql)


def _ensure_parent_dir(db_path: str) -> None:
    """确保数据库文件所在目录存在。"""
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


async def save(
    world_state: WorldState,
    tracker: RelationshipTracker,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """全量保存世界状态到 SQLite。

    先清空所有表(除自增序列外),再写入当前内存快照。整个操作在一个事务里,
    出错则回滚,避免落下半个损坏的世界。
    """
    _ensure_parent_dir(db_path)
    async with aiosqlite.connect(db_path) as db:
        await _ensure_schema(db)

        # 全量覆盖: 先清表
        for table in ("digimons", "memories", "relationships", "events", "world_meta"):
            await db.execute(f"DELETE FROM {table}")

        # ---- 数码兽 + 记忆 ----
        for agent in world_state.all():
            st = agent.stats
            await db.execute(
                """
                INSERT INTO digimons (
                    name, species, stage, attribute, region_id, x, y,
                    hp, ep, attack, defense, speed, bond, mood, mood_state,
                    battle_victories, current_plan, latent_desire, desire_strength
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    agent.name,
                    agent.species,
                    agent.stage.value,
                    agent.attribute.value,
                    agent.region_id,
                    int(agent.location[0]),
                    int(agent.location[1]),
                    st.hp,
                    st.ep,
                    st.attack,
                    st.defense,
                    st.speed,
                    st.bond,
                    agent.mood,
                    json.dumps(agent.mood_state, ensure_ascii=False),
                    agent.battle_victories,
                    agent.current_plan,
                    agent.latent_desire,
                    agent.desire_strength,
                ),
            )
            for node in agent.memory.entries:
                await db.execute(
                    """
                    INSERT INTO memories (
                        agent_name, node_id, timestamp, description,
                        importance, memory_type
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (
                        agent.name,
                        node.node_id,
                        node.timestamp.isoformat(),
                        node.description,
                        node.importance,
                        node.memory_type,
                    ),
                )

        # ---- 关系 ----
        for pair in tracker.all_pairs():
            vec = pair.get("vector", {})
            await db.execute(
                "INSERT INTO relationships (agent_a, agent_b, score, affinity, rivalry, respect, fear) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    pair["a"], pair["b"], pair["score"],
                    vec.get("affinity", 0.0),
                    vec.get("rivalry", 0.0),
                    vec.get("respect", 0.0),
                    vec.get("fear", 0.0),
                ),
            )

        # ---- 事件 ----
        for ev in world_state.events:
            # description 优先取 description 字段,没有就把整个事件塞成 JSON,保证可回溯
            desc = ev.get("description")
            if desc is None:
                desc = json.dumps(ev, ensure_ascii=False)
            await db.execute(
                "INSERT INTO events (type, description, at) VALUES (?,?,?)",
                (ev.get("type"), desc, ev.get("at")),
            )

        # ---- 世界元数据 ----
        meta = {
            "world_time": datetime.now().isoformat(),
            "real_to_world_ratio": str(world_state.real_to_world_ratio),
        }
        for key, value in meta.items():
            await db.execute(
                "INSERT INTO world_meta (key, value) VALUES (?,?)",
                (key, value),
            )

        await db.commit()
    logger.info("world saved to %s (%d digimons)", db_path, world_state.count())


async def load(
    world_state: WorldState,
    tracker: RelationshipTracker,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """从 SQLite 全量恢复世界状态到内存。

    先清空内存(agents / events / 关系表),再从库里灌入。数据库文件不存在时
    直接返回 False(没什么可加载的),不报错。

    Returns:
        True 表示成功加载;False 表示库不存在。
    """
    if not os.path.exists(db_path):
        logger.info("no db at %s, skip load", db_path)
        return False

    async with aiosqlite.connect(db_path) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row

        # 先把库里的记忆按 agent 分好组
        mem_by_agent: dict[str, list[MemoryNode]] = {}
        async with db.execute(
            "SELECT agent_name, node_id, timestamp, description, importance, memory_type "
            "FROM memories ORDER BY node_id"
        ) as cur:
            async for row in cur:
                node = MemoryNode(
                    timestamp=_parse_dt(row["timestamp"]),
                    description=row["description"],
                    importance=row["importance"],
                    memory_type=row["memory_type"],
                    node_id=row["node_id"],
                )
                mem_by_agent.setdefault(row["agent_name"], []).append(node)

        # ---- 数码兽 ----
        new_agents: dict[str, DigimonAgent] = {}
        async with db.execute(
            "SELECT name, species, stage, attribute, region_id, x, y, hp, ep, "
            "attack, defense, speed, bond, mood, mood_state, battle_victories, current_plan, "
            "latent_desire, desire_strength "
            "FROM digimons"
        ) as cur:
            async for row in cur:
                agent = _row_to_agent(row, mem_by_agent.get(row["name"], []))
                new_agents[agent.name] = agent

        # ---- 关系 ----
        rel_rows: list[dict[str, Any]] = []
        async with db.execute(
            "SELECT agent_a, agent_b, score, affinity, rivalry, respect, fear FROM relationships"
        ) as cur:
            async for row in cur:
                rel_rows.append(dict(row))

        # ---- 事件 ----
        new_events: list[dict] = []
        async with db.execute(
            "SELECT type, description, at FROM events ORDER BY id"
        ) as cur:
            async for row in cur:
                new_events.append(
                    {"type": row["type"], "description": row["description"], "at": row["at"]}
                )

        # ---- 世界元数据 ----
        meta: dict[str, str] = {}
        async with db.execute("SELECT key, value FROM world_meta") as cur:
            async for row in cur:
                meta[row["key"]] = row["value"]

    # 全部读完再一次性覆写内存,避免读一半失败留下半个世界
    world_state.agents = new_agents
    world_state.events = new_events
    if "real_to_world_ratio" in meta:
        with contextlib.suppress(TypeError, ValueError):
            world_state.real_to_world_ratio = int(meta["real_to_world_ratio"])

    # 关系表: 清空后重灌
    tracker._vectors.clear()
    for row in rel_rows:
        a, b = row["agent_a"], row["agent_b"]
        # 尝试恢复四维向量(旧库可能没有这些列)
        vec = RelationshipVector(
            affinity=float(row.get("affinity", row.get("score", 0.0))),
            rivalry=float(row.get("rivalry", 0.0)),
            respect=float(row.get("respect", 0.0)),
            fear=float(row.get("fear", 0.0)),
        )
        tracker._vectors[_key(a, b)] = vec

    logger.info("world loaded from %s (%d digimons)", db_path, len(new_agents))
    return True


def _parse_dt(value: str) -> datetime:
    """把 ISO 字符串还原成 datetime;解析失败退化为当前时间。"""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.utcnow()


def _row_to_agent(row: aiosqlite.Row, memories: list[MemoryNode]) -> DigimonAgent:
    """把 digimons 表的一行 + 它的记忆重建成 DigimonAgent。"""
    stats = DigimonStats(
        hp=row["hp"],
        max_hp=row["hp"],
        ep=row["ep"],
        max_ep=row["ep"],
        attack=row["attack"],
        defense=row["defense"],
        speed=row["speed"],
        bond=row["bond"],
    )
    stream = MemoryStream(entries=list(memories))
    # next_id 续到已有最大 node_id + 1,避免新增记忆撞 id
    if memories:
        stream.next_id = max((m.node_id or 0) for m in memories) + 1

    return DigimonAgent(
        name=row["name"],
        species=row["species"],
        stage=EvolutionStage(row["stage"]),
        attribute=DigimonAttribute(row["attribute"]),
        region_id=row["region_id"],
        location=(row["x"], row["y"]),
        stats=stats,
        memory=stream,
        current_plan=row["current_plan"],
        mood=row["mood"],
        mood_state=_parse_mood_state(row["mood_state"]),
        battle_victories=row["battle_victories"],
        latent_desire=row["latent_desire"] if row["latent_desire"] else "",
        desire_strength=row["desire_strength"] if row["desire_strength"] is not None else 0.0,
    )


def _parse_mood_state(value: str | None) -> dict[str, float]:
    """从 JSON 字符串还原 mood_state;解析失败返回默认零向量。"""
    if not value:
        return {"joy": 0.0, "sadness": 0.0, "anger": 0.0, "fear": 0.0}
    try:
        data = json.loads(value)
        return {
            "joy": float(data.get("joy", 0.0)),
            "sadness": float(data.get("sadness", 0.0)),
            "anger": float(data.get("anger", 0.0)),
            "fear": float(data.get("fear", 0.0)),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"joy": 0.0, "sadness": 0.0, "anger": 0.0, "fear": 0.0}

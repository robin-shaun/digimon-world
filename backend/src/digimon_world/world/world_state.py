"""
WorldState - 内存中的世界状态
==============================

维护世界中的所有数码兽、地区、事件。
这是后端服务的单一数据源(单一进程内,后续 Phase 会加持久化)。

设计要点 (Phase 1):
- 进程内单例(模块级 _state),FastAPI 启动时初始化几只数码兽
- 提供线程/协程安全的访问(getter / setter)
- 序列化友好:to_dict() 可 dump 给前端 / 落盘

详细设计: docs/DESIGN.md 第 2 节
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..agents.digimon_agent import DigimonAgent


@dataclass
class Region:
    """一个地区(文件岛 / 无限山 / 沙拔大陆等)。"""

    region_id: str
    name: str
    description: str
    # 地图范围(像素,前端 canvas 用)
    bounds: tuple[int, int, int, int] = (0, 0, 960, 600)
    # 兴趣点(POI): id -> (x, y, label)
    pois: dict[str, tuple[int, int, str]] = field(default_factory=dict)


# ---- 内置地区数据 ----
FILE_ISLAND = Region(
    region_id="file_island",
    name="文件岛",
    description="被选召的孩子们最初登陆的小岛,生活着幼年期~成熟期数码兽。",
    bounds=(0, 0, 960, 600),
    pois={
        "beach_of_departure": (173, 468, "启程海滩"),
        "evolution_shrine": (470, 230, "进化神殿"),
        "ogremon_shop": (745, 480, "奥加兽的商店"),
    },
)

INFINITY_MOUNTAIN = Region(
    region_id="infinity_mountain",
    name="无限山",
    description="数码世界中心,创世神栖息地。",
    bounds=(0, 0, 960, 600),
    pois={
        "creators_altar": (480, 120, "创世者祭坛"),
    },
)

DEFAULT_REGIONS: dict[str, Region] = {
    "file_island": FILE_ISLAND,
    "infinity_mountain": INFINITY_MOUNTAIN,
}


class WorldState:
    """整个世界的当前状态(单例)。

    Phase 1: 内存中维护,单进程。
    Phase 4: 加 SQLite 持久化,加多进程同步(可能用 asyncio Lock 替代 threading.Lock)。
    """

    def __init__(self, regions: Optional[dict[str, Region]] = None) -> None:
        self._lock = threading.RLock()
        self.regions: dict[str, Region] = regions or dict(DEFAULT_REGIONS)
        self.agents: dict[str, DigimonAgent] = {}
        self.events: list[dict[str, Any]] = []
        self.created_at: datetime = datetime.now()
        # 世界时间(独立于现实时间): 现实 1 秒 = 世界 1 分钟 (默认)
        self.real_to_world_ratio: int = 60
        # Phase 7: 因果链 —— 事件 ID 自增计数器
        self._next_event_id: int = 0

    # ---- Phase 7: 因果链支持 ----
    def _next_id(self) -> int:
        """分配下一个事件 ID(线程安全)。"""
        with self._lock:
            eid = self._next_event_id
            self._next_event_id += 1
            return eid

    def append_event(
        self,
        event: dict[str, Any],
        cause_event_id: int | None = None,
        cause_type: str | None = None,
    ) -> int:
        """添加一条世界事件,自动注入因果链字段和事件 ID。

        Args:
            event: 事件 dict
            cause_event_id: 触发此事件的上游事件 ID (None 为根因事件)
            cause_type: 因果类型: proximity/dialogue/battle/disaster/festival/story/agent

        Returns:
            分配的事件 ID
        """
        eid = self._next_id()
        event["event_id"] = eid
        event["causality"] = {
            "cause_event_id": cause_event_id,
            "cause_type": cause_type,
        }
        with self._lock:
            self.events.append(event)
        return eid

    def build_causality_chain(self, event_id: int) -> dict[str, Any]:
        """Phase 7: 回溯任意事件的因果链。

        从 event_id 开始向上追溯 cause_event_id,直到根因(None)。
        返回 {"event": 目标事件, "chain": [...], "root_cause": 根因事件}。

        Args:
            event_id: 要追溯的事件 ID

        Returns:
            因果链字典; 如果 event_id 不存在则返回 {"error": "not found"}
        """
        with self._lock:
            # 建立 event_id -> event 索引
            index: dict[int, dict[str, Any]] = {}
            for ev in self.events:
                eid = ev.get("event_id")
                if eid is not None:
                    index[eid] = ev

        target = index.get(event_id)
        if target is None:
            return {"error": f"Event {event_id} not found"}

        chain: list[dict[str, Any]] = []
        current = target
        visited: set[int] = set()

        while current is not None:
            eid = current.get("event_id")
            if eid is None or eid in visited:
                break
            visited.add(eid)
            chain.append({
                "event_id": eid,
                "type": current.get("type", ""),
                "description": current.get("description", current.get("line", "")),
                "at": current.get("at", ""),
                "causality": current.get("causality", {}),
            })
            # 向上追溯
            cause_id = current.get("causality", {}).get("cause_event_id")
            current = index.get(cause_id) if cause_id is not None else None

        return {
            "event": chain[0] if chain else {},
            "chain": chain,
            "root_cause": chain[-1] if chain else {},
            "depth": len(chain),
        }

    # ---- 注册数码兽 ----
    def spawn(self, agent: DigimonAgent) -> None:
        with self._lock:
            self.agents[agent.name] = agent

    def get(self, name: str) -> Optional[DigimonAgent]:
        with self._lock:
            return self.agents.get(name)

    def all(self) -> list[DigimonAgent]:
        with self._lock:
            return list(self.agents.values())

    def count(self) -> int:
        with self._lock:
            return len(self.agents)

    # ---- 移动 ----
    def move(self, name: str, dx: int, dy: int) -> Optional[tuple[int, int]]:
        """移动一只数码兽(dx, dy 像素),返回新坐标。如果超出地区边界则夹紧。"""
        with self._lock:
            agent = self.agents.get(name)
            if agent is None:
                return None
            x, y = agent.location
            region = self.regions.get(agent.region_id)
            if region is None:
                return None
            min_x, min_y, max_x, max_y = region.bounds
            new_x = max(min_x, min(max_x, x + dx))
            new_y = max(min_y, min(max_y, y + dy))
            agent.location = (new_x, new_y)
            event = {
                "type": "moved",
                "agent": name,
                "from": [x, y],
                "to": [new_x, new_y],
                "at": datetime.now().isoformat(),
            }
            # Phase 7: 使用 append_event 注入 event_id + causality
            eid = self._next_id()
            event["event_id"] = eid
            event["causality"] = {
                "cause_event_id": None,
                "cause_type": "agent",
            }
            self.events.append(event)
            return (new_x, new_y)

    @property
    def memory_stats(self) -> dict[str, Any]:
        """Phase 7: 所有 agent 记忆压缩统计汇总。"""
        total = 0
        total_deduped = 0
        total_summarized = 0
        total_pruned = 0
        per_agent: list[dict[str, Any]] = []
        for agent in self.all():
            ms = agent.memory
            total += len(ms.entries)
            total_deduped += ms.total_deduped
            total_summarized += ms.total_summarized
            total_pruned += ms.total_pruned
            per_agent.append({
                "name": agent.name,
                "entries": len(ms.entries),
                "deduped": ms.total_deduped,
                "summarized": ms.total_summarized,
                "pruned": ms.total_pruned,
            })
        return {
            "total_entries": total,
            "total_deduped": total_deduped,
            "total_summarized": total_summarized,
            "total_pruned": total_pruned,
            "per_agent": per_agent,
        }

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "regions": [
                    {
                        "id": r.region_id,
                        "name": r.name,
                        "description": r.description,
                        "bounds": list(r.bounds),
                        "pois": {k: {"x": v[0], "y": v[1], "label": v[2]} for k, v in r.pois.items()},
                    }
                    for r in self.regions.values()
                ],
                "agents": [a.to_dict() for a in self.agents.values()],
                "world_time": datetime.now().isoformat(),
                "real_to_world_ratio": self.real_to_world_ratio,
                "memory_stats": self.memory_stats,
            }


# ---- 进程级单例 ----
_state: Optional[WorldState] = None


def get_world() -> WorldState:
    """获取(或延迟初始化)世界单例。

    启动时塞几只数码兽到文件岛,方便前端联调。
    """
    global _state
    if _state is None:
        _state = WorldState()
        # 启动数据
        _state.spawn(DigimonAgent(
            name="亚古兽",
            species="agumon",
            region_id="file_island",
            location=(200, 400),
            current_plan="在沙滩附近闲逛",
        ))
        _state.spawn(DigimonAgent(
            name="加布兽",
            species="gabumon",
            region_id="file_island",
            location=(700, 350),
            current_plan="安静地观察周围",
        ))
        _state.spawn(DigimonAgent(
            name="比丘兽",
            species="biyomon",
            region_id="file_island",
            location=(480, 180),
            current_plan="从空中巡视",
        ))
    return _state


def reset_world() -> None:
    """重置世界(测试用)。"""
    global _state
    _state = None

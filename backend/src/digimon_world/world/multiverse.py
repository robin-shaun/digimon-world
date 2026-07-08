"""
MultiverseManager - 多世界实例
===============================

Phase 1~4 里整个后端只有一个 WorldState 单例。Phase 5 把它推广成"多元宇宙":
同一进程内并存多个独立的 WorldState,每个都是一条平行的数码世界时间线,拥有
自己的数码兽、事件、季节。

两个世界之间通过 "digital_gate"(数码之门)事件联通 —— 一只数码兽可以穿过门
从世界 A 迁移到世界 B,把自己连同记忆带过去。这是"世界之间发生关系"的唯一
通道,平时各世界完全隔离。

创建世界的入口统一走导演接口 POST /api/director/inject_event:
- type == 'world_create'  → 新建一个平行世界(create_world)
- type == 'digital_gate'  → 打开数码之门,把某只数码兽从一个世界送到另一个
                            (open_gate)

设计要点:
- 纯内存、纯同步、无 LLM 依赖。
- 默认宇宙 id = 'prime'(对应原来的进程级 get_world 单例语义)。
- 每个世界独立 id,create_world 若不给 id 则确定性生成 'world_<序号>'。
- open_gate 通过"从源世界移除 agent → 落到目标世界"迁移,同时两边各记一条
  digital_gate 事件,保证 Director 视角双向可见。
"""

from __future__ import annotations

from typing import Any, Optional

from ..agents.digimon_agent import DigimonAgent
from .world_state import WorldState

# 主宇宙(默认世界)的 id
PRIME_WORLD_ID: str = "prime"


class MultiverseManager:
    """管理多个平行 WorldState 实例。

    Attributes:
        worlds: world_id -> WorldState
    """

    def __init__(self, prime: Optional[WorldState] = None) -> None:
        # 主宇宙:允许注入(测试 / 复用现有单例),否则新建
        self.worlds: dict[str, WorldState] = {
            PRIME_WORLD_ID: prime if prime is not None else WorldState()
        }

    # ---- 查询 ----
    def get_world(self, world_id: str = PRIME_WORLD_ID) -> Optional[WorldState]:
        """取某个世界(不存在返回 None)。"""
        return self.worlds.get(world_id)

    def all_world_ids(self) -> list[str]:
        """所有世界 id(主宇宙优先,其余按创建顺序)。"""
        return list(self.worlds.keys())

    def count(self) -> int:
        return len(self.worlds)

    # ---- 创建世界 ----
    def create_world(
        self,
        world_id: Optional[str] = None,
        regions: Optional[dict[str, Any]] = None,
    ) -> WorldState:
        """新建一个平行世界并登记。

        Args:
            world_id: 世界 id。不给则确定性生成 'world_<序号>'(序号 = 当前世界数)。
            regions: 传给 WorldState 的地区表(不给则用默认地区)。

        Returns:
            新建(或已存在同 id 时返回既有)的 WorldState。
        """
        if world_id is None:
            world_id = f"world_{len(self.worlds)}"
        # 已存在则不覆盖,直接返回既有世界(幂等)
        existing = self.worlds.get(world_id)
        if existing is not None:
            return existing
        world = WorldState(regions=regions)
        self.worlds[world_id] = world
        return world

    def remove_world(self, world_id: str) -> bool:
        """移除一个世界(主宇宙不可移除)。返回是否成功。"""
        if world_id == PRIME_WORLD_ID:
            return False
        return self.worlds.pop(world_id, None) is not None

    # ---- 数码之门:跨世界迁移 ----
    def open_gate(
        self,
        agent_name: str,
        from_world_id: str,
        to_world_id: str,
    ) -> Optional[DigimonAgent]:
        """打开数码之门,把一只数码兽从 from_world 送到 to_world。

        迁移动作:
        - 从源世界移除该 agent(连同记忆一起搬走)
        - 落到目标世界(spawn)
        - 两个世界各写一条 digital_gate 事件(离开 / 到达),Director 双向可见

        Returns:
            成功迁移的 agent;任一世界不存在 / agent 不在源世界 / 源与目标相同
            时返回 None。
        """
        if from_world_id == to_world_id:
            return None
        src = self.worlds.get(from_world_id)
        dst = self.worlds.get(to_world_id)
        if src is None or dst is None:
            return None

        agent = src.get(agent_name)
        if agent is None:
            return None

        # 从源世界移除
        with src._lock:
            src.agents.pop(agent_name, None)
        # 落到目标世界
        dst.spawn(agent)

        # 两边各记一条事件(方向相反),Director 视角双向可见
        src.events.append({
            "type": "digital_gate",
            "agent": agent_name,
            "direction": "depart",
            "from_world": from_world_id,
            "to_world": to_world_id,
            "source": "multiverse",
        })
        dst.events.append({
            "type": "digital_gate",
            "agent": agent_name,
            "direction": "arrive",
            "from_world": from_world_id,
            "to_world": to_world_id,
            "source": "multiverse",
        })
        return agent

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        """多元宇宙概览(每个世界只给轻量摘要,不展开全部 agent)。"""
        return {
            "count": self.count(),
            "worlds": [
                {
                    "world_id": wid,
                    "agent_count": world.count(),
                    "event_count": len(world.events),
                }
                for wid, world in self.worlds.items()
            ],
        }


# ---- 进程级单例 ----
_multiverse: Optional[MultiverseManager] = None


def get_multiverse() -> MultiverseManager:
    """获取(或延迟初始化)多元宇宙单例。

    主宇宙复用 world_state 的进程级单例,保证 get_world() 与
    get_multiverse().get_world('prime') 指向同一个 WorldState。
    """
    global _multiverse
    if _multiverse is None:
        # 局部 import 避免与 world_state 的循环依赖
        from .world_state import get_world

        _multiverse = MultiverseManager(prime=get_world())
    return _multiverse


def reset_multiverse() -> None:
    """重置多元宇宙(测试用)。"""
    global _multiverse
    _multiverse = None

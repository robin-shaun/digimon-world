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

from typing import Any

from ..agents.digimon_agent import DigimonAgent
from .world_state import WorldState

# 主宇宙(默认世界)的 id
PRIME_WORLD_ID: str = "prime"


def _seed_default_digimon(world: WorldState) -> None:
    """往一个空世界里注入默认的 10 只数码兽,与 prime 世界初始化一致。

    包含: 亚古兽 / 加布兽 / 比丘兽 / 甲虫兽 / 巴鲁兽 /
          哥玛兽 / 巴达兽 / 迪路兽 / 小狗兽 / 艾力兽
    """
    from ..agents.digimon_agent import DigimonAgent

    defaults = [
        ("亚古兽", "agumon", "file_island", (200, 400), "在沙滩附近闲逛"),
        ("加布兽", "gabumon", "file_island", (700, 350), "安静地观察周围"),
        ("比丘兽", "biyomon", "file_island", (480, 180), "从空中巡视"),
        ("甲虫兽", "tentomon", "file_island", (350, 300), "在树林里找食物"),
        ("巴鲁兽", "palmon", "file_island", (600, 250), "晒太阳光合作用"),
        ("哥玛兽", "gomamon", "file_island", (150, 500), "在海边玩水"),
        ("巴达兽", "patamon", "file_island", (400, 100), "在空中飞行"),
        ("迪路兽", "tailmon", "infinity_mountain", (500, 150), "守护创世者祭坛"),
        ("小狗兽", "plotmon", "file_island", (300, 450), "在草地上玩耍"),
        ("艾力兽", "elecmon", "file_island", (800, 500), "在发电站巡逻"),
    ]
    for name, species, region_id, (x, y), plan in defaults:
        world.spawn(DigimonAgent(
            name=name,
            species=species,
            region_id=region_id,
            location=(x, y),
            current_plan=plan,
        ))


class MultiverseManager:
    """管理多个平行 WorldState 实例。

    Attributes:
        worlds: world_id -> WorldState
    """

    def __init__(self, prime: WorldState | None = None) -> None:
        # 主宇宙:允许注入(测试 / 复用现有单例),否则新建
        self.worlds: dict[str, WorldState] = {
            PRIME_WORLD_ID: prime if prime is not None else WorldState()
        }
        # 确保主宇宙 world_id 正确(可能从外部注入且未设置)
        if self.worlds[PRIME_WORLD_ID].world_id is None:
            self.worlds[PRIME_WORLD_ID].world_id = PRIME_WORLD_ID

    # ---- 查询 ----
    def get_world(self, world_id: str = PRIME_WORLD_ID) -> WorldState | None:
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
        world_id: str | None = None,
        regions: dict[str, Any] | None = None,
        seasons_enabled: bool = True,
        seed_agents: bool = False,
    ) -> WorldState:
        """新建一个平行世界并登记。

        Args:
            world_id: 世界 id。不给则确定性生成 'world_<序号>'(序号 = 当前世界数)。
            regions: 传给 WorldState 的地区表(不给则用默认地区)。
            seasons_enabled: 是否启用季节系统(默认 True)。
            seed_agents: 是否注入默认数码兽(默认 False,空世界)。

        Returns:
            新建(或已存在同 id 时返回既有)的 WorldState。
        """
        if world_id is None:
            world_id = f"world_{len(self.worlds)}"
        # 已存在则不覆盖,直接返回既有世界(幂等)
        existing = self.worlds.get(world_id)
        if existing is not None:
            return existing
        world = WorldState(
            regions=regions,
            seasons_enabled=seasons_enabled,
            world_id=world_id,
        )
        # 注入默认数码兽
        if seed_agents:
            _seed_default_digimon(world)
        self.worlds[world_id] = world
        return world

    def remove_world(self, world_id: str) -> bool:
        """移除一个世界(主宇宙不可移除)。返回是否成功。"""
        if world_id == PRIME_WORLD_ID:
            return False
        return self.worlds.pop(world_id, None) is not None

    def seed_world(self, world_id: str) -> int:
        """向已有世界注入默认数码兽,返回新注入的数量。

        世界不存在返回 -1,世界已有数码兽时仍追加(不跳过)。
        主宇宙也允许 seed(可重复注入)。
        """
        world = self.worlds.get(world_id)
        if world is None:
            return -1
        before = world.count()
        _seed_default_digimon(world)
        return world.count() - before

    # ---- 数码之门:跨世界迁移 ----
    def open_gate(
        self,
        agent_name: str,
        from_world_id: str,
        to_world_id: str,
    ) -> DigimonAgent | None:
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

    # ---- 批量迁移 ----
    def migrate_batch(
        self,
        agent_names: list[str],
        from_world_id: str,
        to_world_id: str,
    ) -> dict[str, Any]:
        """批量数码之门: 把多只数码兽从 from_world 迁移到 to_world。

        与 open_gate 不同: 支持一次传多只,部分失败不阻塞其他。
        每只 agent 独立迁移,各自记录 digital_gate 事件。

        Args:
            agent_names: 要迁移的数码兽名字列表
            from_world_id: 源世界 id
            to_world_id: 目标世界 id

        Returns:
            {
                "migrated": [...],   # 成功迁移的名字
                "failed": [...],      # 失败的名字 + 原因
                "total": int,         # 请求总数
            }
        """
        if from_world_id == to_world_id:
            return {
                "migrated": [],
                "failed": [
                    {"name": name, "reason": "same world"}
                    for name in agent_names
                ],
                "total": len(agent_names),
            }
        src = self.worlds.get(from_world_id)
        dst = self.worlds.get(to_world_id)
        if src is None or dst is None:
            reason = f"world '{from_world_id}' not found" if src is None else f"world '{to_world_id}' not found"
            return {
                "migrated": [],
                "failed": [{"name": name, "reason": reason} for name in agent_names],
                "total": len(agent_names),
            }

        migrated: list[str] = []
        failed: list[dict[str, str]] = []
        for name in agent_names:
            agent = src.get(name)
            if agent is None:
                failed.append({"name": name, "reason": "agent not found"})
                continue
            # 从源世界移除
            with src._lock:
                src.agents.pop(name, None)
            # 落到目标世界
            dst.spawn(agent)
            # 事件记录
            src.events.append({
                "type": "digital_gate",
                "agent": name,
                "direction": "depart",
                "from_world": from_world_id,
                "to_world": to_world_id,
                "source": "multiverse",
                "method": "batch",
            })
            dst.events.append({
                "type": "digital_gate",
                "agent": name,
                "direction": "arrive",
                "from_world": from_world_id,
                "to_world": to_world_id,
                "source": "multiverse",
                "method": "batch",
            })
            migrated.append(name)

        return {
            "migrated": migrated,
            "failed": failed,
            "total": len(agent_names),
        }

    def auto_migrate(
        self,
        max_per_pair: int = 3,
    ) -> list[dict[str, Any]]:
        """自动跨世界迁移: 在非 prime 世界之间随机迁移数码兽。

        算法:
        1. 找出所有非 prime 世界(至少 2 个才有意义)
        2. 随机配对世界 (from, to)
        3. 从 from 世界随机挑 1~max_per_pair 只数码兽, 迁移到 to
        4. 返回迁移摘要列表

        设计目的: 让平行世界之间保持数码兽"自然流动",模拟跨世界
        生态,同时为⑤长期一致性测试提供持续的跨世界数据流。

        Returns:
            [{from_world, to_world, count, agents: [...]}, ...]
        """
        non_prime = [wid for wid in self.worlds if wid != PRIME_WORLD_ID]
        if len(non_prime) < 2:
            return []

        import random
        results: list[dict[str, Any]] = []
        # 随机配对: 先打乱,相邻两个配对
        shuffled = non_prime[:]
        random.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            from_wid = shuffled[i]
            to_wid = shuffled[i + 1]
            src = self.worlds[from_wid]
            # 从源世界随机挑数码兽
            all_agents = src.all()
            if not all_agents:
                continue
            count = min(random.randint(1, max_per_pair), len(all_agents))
            chosen = random.sample(all_agents, count)
            names = [a.name for a in chosen]
            result = self.migrate_batch(names, from_wid, to_wid)
            results.append({
                "from_world": from_wid,
                "to_world": to_wid,
                "count": len(result["migrated"]),
                "agents": result["migrated"],
            })

        return results

    # ---- 聚合统计 ----
    def stats(self) -> dict[str, Any]:
        """跨世界聚合统计: 世界数、总 agent 数、总事件数、各世界摘要。"""
        world_summaries = []
        total_agents = 0
        total_events = 0
        for wid, world in self.worlds.items():
            agents = world.count()
            events = len(world.events)
            total_agents += agents
            total_events += events
            world_summaries.append({
                "world_id": wid,
                "agent_count": agents,
                "event_count": events,
                "region_count": len(world.regions),
            })
        return {
            "world_count": self.count(),
            "total_agents": total_agents,
            "total_events": total_events,
            "worlds": world_summaries,
        }

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
_multiverse: MultiverseManager | None = None


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

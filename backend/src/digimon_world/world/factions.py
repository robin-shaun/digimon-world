"""
FactionRegistry - 数码兽派系
============================

把零散的两两关系 (RelationshipTracker) 聚合成"群体归属"。前端画阵营图、
Director 观察势力版图时,派系比一堆边更直观。

两种派系来源:

1. 自动涌现 (form_factions): 扫描关系表,凡是关系 > EMERGENCE_THRESHOLD 的两只
   自动归入同一派系(并查集连通分量)。人以群分,朋友的朋友也是一伙。
2. 导演注入 (inject_faction): POST /api/director/inject_event 且 type='faction_create'
   时,手动建一个命名派系并塞进指定成员。剧情需要时凭空造一个阵营。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(高频调用 / 好测试)。
- 自动派系用连通分量算法(并查集),保证"传递闭包": A-B 友好、B-C 友好 →
  A/B/C 同派,即使 A-C 从未直接互动。
- 导演注入的派系带 origin='director' 标记,form_factions 重算时不会被冲掉。
- 派系 id 确定性: 自动派系用 "faction_" + 成员排序后首名; 导演派系用传入 id。

典型用法:

    reg = FactionRegistry()
    reg.form_factions(tracker)                      # 扫描关系自动建派系
    reg.get_faction_members("faction_亚古兽")        # -> ["亚古兽", "加布兽"]
    reg.inject_faction("dark_masters", ["某兽"])     # 导演凭空造一个
    reg.faction_hostility("a", "b", tracker)        # 两派敌对度
"""

from __future__ import annotations

from typing import Any

# 关系高于此值的两只自动归入同一派系
EMERGENCE_THRESHOLD: float = 30.0


class Faction:
    """一个派系: 数码兽的群体归属。

    Attributes:
        faction_id: 派系唯一标识
        name: 显示名(自动派系用 id,导演派系可自定义)
        members: 成员名字集合
        origin: 'emergent'(自动涌现) 或 'director'(导演注入)
    """

    def __init__(
        self,
        faction_id: str,
        members: set[str] | None = None,
        name: str | None = None,
        origin: str = "emergent",
    ) -> None:
        self.faction_id = faction_id
        self.name = name if name is not None else faction_id
        self.members: set[str] = set(members) if members else set()
        self.origin = origin

    def to_dict(self) -> dict[str, Any]:
        return {
            "faction_id": self.faction_id,
            "name": self.name,
            "members": sorted(self.members),
            "origin": self.origin,
        }


class FactionRegistry:
    """派系登记处: 维护所有派系(自动涌现 + 导演注入)。"""

    def __init__(self) -> None:
        self._factions: dict[str, Faction] = {}

    # ---- 自动涌现 ----
    def form_factions(self, tracker: Any) -> list[Faction]:
        """扫描关系表,把关系 > EMERGENCE_THRESHOLD 的成员并入同一派系。

        用并查集求连通分量,得到传递闭包(朋友的朋友也是一伙)。
        导演注入的派系(origin='director')保留不动,只重算自动派系。

        Returns:
            本次重算后的全部自动派系(按 id 排序)。
        """
        # 并查集: name -> parent
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            root = x
            while parent[root] != root:
                root = parent[root]
            # 路径压缩
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            # 确定性: 字典序小的当根
            if ra <= rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

        for pair in tracker.all_pairs():
            if pair["score"] > EMERGENCE_THRESHOLD:
                union(pair["a"], pair["b"])

        # 按根聚合成分组
        groups: dict[str, set[str]] = {}
        for name in list(parent.keys()):
            root = find(name)
            groups.setdefault(root, set()).add(name)

        # 清掉旧的自动派系,保留导演派系
        self._factions = {
            fid: f for fid, f in self._factions.items() if f.origin == "director"
        }

        emergent: list[Faction] = []
        for root, members in groups.items():  # noqa: B007
            # 单成员(无任何强关系)不成派系
            if len(members) < 2:
                continue
            faction_id = "faction_" + min(members)
            faction = Faction(faction_id=faction_id, members=members, origin="emergent")
            self._factions[faction_id] = faction
            emergent.append(faction)

        return sorted(emergent, key=lambda f: f.faction_id)

    # ---- 导演注入 ----
    def inject_faction(
        self,
        faction_id: str,
        members: list[str],
        name: str | None = None,
    ) -> Faction:
        """导演凭空创建(或覆盖)一个命名派系。origin 标记为 'director'。"""
        faction = Faction(
            faction_id=faction_id,
            members=set(members),
            name=name,
            origin="director",
        )
        self._factions[faction_id] = faction
        return faction

    # ---- 查询 ----
    def get_faction_members(self, faction_id: str) -> list[str]:
        """某派系的成员列表(排序)。不存在 → 空列表。"""
        faction = self._factions.get(faction_id)
        return sorted(faction.members) if faction is not None else []

    def get_faction(self, faction_id: str) -> Faction | None:
        return self._factions.get(faction_id)

    def all_factions(self) -> list[Faction]:
        """全部派系,按 id 排序(确定性)。"""
        return [self._factions[fid] for fid in sorted(self._factions)]

    def faction_of(self, name: str) -> str | None:
        """某只数码兽所属派系 id(命中多个时取 id 字典序最小)。无归属 → None。"""
        hits = sorted(fid for fid, f in self._factions.items() if name in f.members)
        return hits[0] if hits else None

    # ---- 敌对度 ----
    def faction_hostility(self, a_faction: str, b_faction: str, tracker: Any) -> float:
        """两派系之间的敌对度 = 跨派成员两两关系的平均值 * -1。

        - 正的敌对度 = 两派整体互相敌视(成员平均关系为负)。
        - 负的敌对度 = 两派其实挺友好(成员平均关系为正)。
        - 任一派系不存在 / 无成员 / 无跨派对 → 0.0(无从判断)。
        同一派系 (a == b) 恒返回 0.0。
        """
        if a_faction == b_faction:
            return 0.0
        fa = self._factions.get(a_faction)
        fb = self._factions.get(b_faction)
        if fa is None or fb is None or not fa.members or not fb.members:
            return 0.0

        total = 0.0
        count = 0
        for x in fa.members:
            for y in fb.members:
                if x == y:
                    continue
                total += tracker.get_relationship(x, y)
                count += 1
        if count == 0:
            return 0.0
        return (total / count) * -1

    def to_dict(self) -> dict[str, Any]:
        return {"factions": [f.to_dict() for f in self.all_factions()]}


# ---- 进程级单例 ----
_registry: FactionRegistry | None = None


def get_registry() -> FactionRegistry:
    """获取(或延迟初始化)派系登记处单例。"""
    global _registry
    if _registry is None:
        _registry = FactionRegistry()
    return _registry


def reset_registry() -> None:
    """重置派系登记处(测试用)。"""
    global _registry
    _registry = None

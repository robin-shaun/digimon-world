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
class SubRegion:
    """一个子区域(如文件岛内部的 14 个区域)。

    数码宝贝大冒险 01 中文件岛由多个子区域组成:
    启程海滩 → 迷乱森林 → 齿轮草原 → 龙眼湖 → 无人商店 →
    玩具城 → 工厂地带 → 古代恐龙境 → 无限山 → ...

    每个子区域有边界矩形(bounds)和 POI,用于:
    - agent 定位(当前在哪个子区)
    - 前端地图渲染(不同颜色/纹理)
    - 剧情事件触发(如黑暗齿轮感染特定子区)
    """

    sub_region_id: str
    name: str
    name_en: str
    description: str
    # 边界矩形的四角 (min_x, min_y, max_x, max_y),像素坐标
    bounds: tuple[int, int, int, int]
    # 子区域内的 POI (与父 Region 的 pois 可以重叠)
    pois: dict[str, tuple[int, int, str]] = field(default_factory=dict)
    # 父 region_id
    parent_region_id: str = "file_island"


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
    # 子区域列表 (Phase 8: 文件岛有 14 个)
    sub_regions: tuple[SubRegion, ...] = field(default_factory=tuple)

    def find_sub_region(self, x: int, y: int) -> SubRegion | None:
        """通过坐标查找所属子区域(点在矩形内即命中,按定义顺序优先)。

        用于: agent 当前的 sub_region 定位、前端地图着色、剧情事件触发。
        """
        for sr in self.sub_regions:
            min_x, min_y, max_x, max_y = sr.bounds
            if min_x <= x <= max_x and min_y <= y <= max_y:
                return sr
        return None


# ---- 文件岛 14 子区域 (数码宝贝大冒险 01 原作复刻) ----

# 文件岛地图 960×600 分成 14 个矩形子区域:
#   北带(上): 冰冻地带 / 密哈拉西山 / 古代恐龙境
#   中上带:     怪蛙皇城  / 迷乱森林  / 齿轮草原  / 无限山
#   中下带:     暗黑洞窟  / 龙眼湖    / 欧加兽堡垒 / 工厂地带
#   南带(下): 启程海滩               / 无人商店  / 玩具城
_FILE_ISLAND_SUB_REGIONS: tuple[SubRegion, ...] = (
    # ── 北带 (y: 0-120) ──
    SubRegion(
        sub_region_id="freezing_area",
        name="冰冻地带",
        name_en="Freezing Area",
        description="常年冰封的极寒之地,居住着雪人兽等冰系数码兽。",
        bounds=(0, 0, 240, 120),
        pois={"freezing_peak": (120, 50, "冰冻峰")},
    ),
    SubRegion(
        sub_region_id="miharashi_mountain",
        name="密哈拉西山",
        name_en="Miharashi Mountain",
        description="可以俯瞰整座文件岛的瞭望山,常作为数码兽们的集合点。",
        bounds=(240, 0, 720, 120),
        pois={"lookout_rock": (480, 60, "瞭望岩")},
    ),
    SubRegion(
        sub_region_id="ancient_dino_region",
        name="古代恐龙境",
        name_en="Ancient Dino Region",
        description="暴龙兽族群栖息的原始峡谷,到处是巨型恐龙化石。",
        bounds=(720, 0, 960, 120),
        pois={"dino_bones": (840, 55, "巨兽骸骨")},
    ),
    # ── 中上带 (y: 120-260) ──
    SubRegion(
        sub_region_id="shogungekomon_castle",
        name="怪蛙皇城",
        name_en="ShogunGekomon's Castle",
        description="怪蛙皇控制的城堡,回荡着令人昏睡的歌声。",
        bounds=(0, 120, 240, 260),
        pois={"castle_gate": (100, 170, "城门")},
    ),
    SubRegion(
        sub_region_id="confusion_forest",
        name="迷乱森林",
        name_en="Confusion Forest",
        description="密林覆盖的迷宫地带,古加兽等昆虫系数码兽出没其中。初次遭遇危险的地方。",
        bounds=(240, 120, 480, 260),
        pois={"deep_woods": (360, 190, "密林深处"), "kuwagamon_nest": (400, 220, "古加兽巢穴")},
    ),
    SubRegion(
        sub_region_id="gear_savannah",
        name="齿轮草原",
        name_en="Gear Savannah",
        description="由黑色齿轮驱动的机械草原,击败梅拉兽后恢复了原本的宁静。",
        bounds=(480, 120, 720, 260),
        pois={"gear_remains": (600, 180, "齿轮残骸"), "meramon_spot": (620, 220, "梅拉兽遗迹")},
    ),
    SubRegion(
        sub_region_id="infinity_mountain_peak",
        name="无限山",
        name_en="Infinity Mountain",
        description="文件岛中央的圣山,数码蛋的起源地,Devimon 的据点。",
        bounds=(720, 120, 960, 260),
        pois={"evolution_shrine": (840, 190, "进化神殿"), "summit": (870, 150, "山顶祭坛")},
    ),
    # ── 中下带 (y: 260-400) ──
    SubRegion(
        sub_region_id="dark_cave",
        name="暗黑洞窟",
        name_en="Dark Cave",
        description="恶魔兽盘踞的地下迷宫,深处供奉着黑色齿轮的核心。",
        bounds=(0, 260, 240, 400),
        pois={"cave_entrance": (110, 270, "洞口"), "black_gear_altar": (70, 360, "黑齿轮祭坛")},
    ),
    SubRegion(
        sub_region_id="dragon_eye_lake",
        name="龙眼湖",
        name_en="Dragon Eye Lake",
        description="清澈如龙眼的湖泊,海龙兽守护着湖下的秘密。",
        bounds=(240, 260, 480, 400),
        pois={"lake_shore": (360, 320, "湖岸"), "seadramon_deep": (330, 380, "海龙兽深渊")},
    ),
    SubRegion(
        sub_region_id="ogremon_fortress",
        name="欧加兽的堡垒",
        name_en="Ogremon's Fortress",
        description="莽撞的欧加兽镇守的石堡,被击败后沦为他的杂货铺。",
        bounds=(480, 260, 720, 400),
        pois={"ogremon_shop": (600, 340, "奥加兽商店"), "fortress_wall": (550, 370, "堡垒外墙")},
    ),
    SubRegion(
        sub_region_id="factory_area",
        name="工厂地带",
        name_en="Factory Area",
        description="安杜路兽运行的机械工厂,齿轮与蒸汽构成的地下迷宫。",
        bounds=(720, 260, 960, 400),
        pois={"andromon_factory": (830, 320, "安杜路兽工厂"), "assembly_line": (870, 370, "流水线")},
    ),
    # ── 南带 (y: 400-600) ──
    SubRegion(
        sub_region_id="beach_of_departure",
        name="启程海滩",
        name_en="Beach of Departure",
        description="被选召的孩子们从夏令营坠落数码世界时最先到达的海滩。一切冒险的起点。",
        bounds=(0, 400, 320, 600),
        pois={"landing_spot": (160, 520, "降落点"), "campfire": (100, 560, "篝火营地")},
    ),
    SubRegion(
        sub_region_id="vending_machine_area",
        name="无人商店",
        name_en="Abandoned Vending Area",
        description="荒野中孤零零的自动售货机,为饥饿的被选召孩子提供生命线。",
        bounds=(320, 400, 640, 600),
        pois={"vending_machine": (460, 530, "自动售货机"), "open_field": (500, 470, "开阔地")},
    ),
    SubRegion(
        sub_region_id="toy_town",
        name="玩具城",
        name_en="Toy Town",
        description="熊仔兽(Monzaemon)统治的童话小镇,看似可爱却暗藏黑暗齿轮的控制。",
        bounds=(640, 400, 960, 600),
        pois={"toy_castle": (800, 520, "玩具城堡"), "monzaemon_throne": (750, 570, "熊仔兽王座")},
    ),
)

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
    sub_regions=_FILE_ISLAND_SUB_REGIONS,
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
    def get_sub_region(self, agent: DigimonAgent) -> dict[str, Any] | None:
        """获取数码兽当前所在的子区域信息。"""
        region = self.regions.get(agent.region_id)
        if region is None:
            return None
        x, y = agent.location
        sr = region.find_sub_region(x, y)
        if sr is None:
            return None
        return {
            "id": sr.sub_region_id,
            "name": sr.name,
            "name_en": sr.name_en,
        }

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
                        "sub_regions": [
                            {
                                "id": sr.sub_region_id,
                                "name": sr.name,
                                "name_en": sr.name_en,
                                "bounds": list(sr.bounds),
                                "pois": {k: {"x": v[0], "y": v[1], "label": v[2]} for k, v in sr.pois.items()},
                            }
                            for sr in r.sub_regions
                        ],
                    }
                    for r in self.regions.values()
                ],
                "agents": [
                    {
                        **a.to_dict(),
                        "sub_region": self.get_sub_region(a),
                    }
                    for a in self.agents.values()
                ],
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
        _state.spawn(DigimonAgent(
            name="甲虫兽",
            species="tentomon",
            region_id="file_island",
            location=(350, 300),
            current_plan="在树林里找食物",
        ))
        _state.spawn(DigimonAgent(
            name="巴鲁兽",
            species="palmon",
            region_id="file_island",
            location=(600, 250),
            current_plan="晒太阳光合作用",
        ))
        _state.spawn(DigimonAgent(
            name="哥玛兽",
            species="gomamon",
            region_id="file_island",
            location=(150, 500),
            current_plan="在海边玩水",
        ))
        _state.spawn(DigimonAgent(
            name="巴达兽",
            species="patamon",
            region_id="file_island",
            location=(400, 100),
            current_plan="在空中飞行",
        ))
        _state.spawn(DigimonAgent(
            name="迪路兽",
            species="tailmon",
            region_id="infinity_mountain",
            location=(500, 150),
            current_plan="守护创世者祭坛",
        ))
        _state.spawn(DigimonAgent(
            name="小狗兽",
            species="plotmon",
            region_id="file_island",
            location=(300, 450),
            current_plan="在草地上玩耍",
        ))
        _state.spawn(DigimonAgent(
            name="艾力兽",
            species="elecmon",
            region_id="file_island",
            location=(750, 400),
            current_plan="在发电站附近巡逻",
        ))
    return _state


def reset_world() -> None:
    """重置世界(测试用)。"""
    global _state
    _state = None

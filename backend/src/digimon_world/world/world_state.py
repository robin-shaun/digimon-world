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

import random as _random
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..agents.digimon_agent import DigimonAgent, DigimonAttribute, DigimonStats, EvolutionStage

# ═══ 世界尺寸常量 (Phase 17: 扩展至完整数码世界) ═══
WORLD_WIDTH = 4000
WORLD_HEIGHT = 3000


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
    bounds: tuple[int, int, int, int] = (0, 0, WORLD_WIDTH, WORLD_HEIGHT)
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

# 文件岛地图 (Phase 17: 平移到右下角 2900,2300 起点) 960×600 分成 14 个矩形子区域:
#   北带(上): 冰冻地带 / 密哈拉西山 / 古代恐龙境
#   中上带:     怪蛙皇城  / 迷乱森林  / 齿轮草原  / 无限山
#   中下带:     暗黑洞窟  / 龙眼湖    / 欧加兽堡垒 / 工厂地带
#   南带(下): 启程海滩               / 无人商店  / 玩具城
_FILE_ISLAND_SUB_REGIONS: tuple[SubRegion, ...] = (
    # ── 北带 (y: 2300-2420) ──
    SubRegion(
        sub_region_id="freezing_area",
        name="冰冻地带",
        name_en="Freezing Area",
        description="常年冰封的极寒之地,居住着雪人兽等冰系数码兽。",
        bounds=(2900, 2300, 3140, 2420),
        pois={"freezing_peak": (3020, 2350, "冰冻峰")},
    ),
    SubRegion(
        sub_region_id="miharashi_mountain",
        name="密哈拉西山",
        name_en="Miharashi Mountain",
        description="可以俯瞰整座文件岛的瞭望山,常作为数码兽们的集合点。",
        bounds=(3140, 2300, 3620, 2420),
        pois={"lookout_rock": (3380, 2360, "瞭望岩")},
    ),
    SubRegion(
        sub_region_id="ancient_dino_region",
        name="古代恐龙境",
        name_en="Ancient Dino Region",
        description="暴龙兽族群栖息的原始峡谷,到处是巨型恐龙化石。",
        bounds=(3620, 2300, 3860, 2420),
        pois={"dino_bones": (3740, 2355, "巨兽骸骨")},
    ),
    # ── 中上带 (y: 2420-2560) ──
    SubRegion(
        sub_region_id="shogungekomon_castle",
        name="怪蛙皇城",
        name_en="ShogunGekomon's Castle",
        description="怪蛙皇控制的城堡,回荡着令人昏睡的歌声。",
        bounds=(2900, 2420, 3140, 2560),
        pois={"castle_gate": (3000, 2470, "城门")},
    ),
    SubRegion(
        sub_region_id="confusion_forest",
        name="迷乱森林",
        name_en="Confusion Forest",
        description="密林覆盖的迷宫地带,古加兽等昆虫系数码兽出没其中。初次遭遇危险的地方。",
        bounds=(3140, 2420, 3380, 2560),
        pois={"deep_woods": (3260, 2490, "密林深处"), "kuwagamon_nest": (3300, 2520, "古加兽巢穴")},
    ),
    SubRegion(
        sub_region_id="gear_savannah",
        name="齿轮草原",
        name_en="Gear Savannah",
        description="由黑色齿轮驱动的机械草原,击败梅拉兽后恢复了原本的宁静。",
        bounds=(3380, 2420, 3620, 2560),
        pois={"gear_remains": (3500, 2480, "齿轮残骸"), "meramon_spot": (3520, 2520, "梅拉兽遗迹")},
    ),
    SubRegion(
        sub_region_id="infinity_mountain_peak",
        name="无限山",
        name_en="Infinity Mountain",
        description="文件岛中央的圣山,数码蛋的起源地,Devimon 的据点。",
        bounds=(3620, 2420, 3860, 2560),
        pois={"evolution_shrine": (3740, 2490, "进化神殿"), "summit": (3770, 2450, "山顶祭坛")},
    ),
    # ── 中下带 (y: 2560-2700) ──
    SubRegion(
        sub_region_id="dark_cave",
        name="暗黑洞窟",
        name_en="Dark Cave",
        description="恶魔兽盘踞的地下迷宫,深处供奉着黑色齿轮的核心。",
        bounds=(2900, 2560, 3140, 2700),
        pois={"cave_entrance": (3010, 2570, "洞口"), "black_gear_altar": (2970, 2660, "黑齿轮祭坛")},
    ),
    SubRegion(
        sub_region_id="dragon_eye_lake",
        name="龙眼湖",
        name_en="Dragon Eye Lake",
        description="清澈如龙眼的湖泊,海龙兽守护着湖下的秘密。",
        bounds=(3140, 2560, 3380, 2700),
        pois={"lake_shore": (3260, 2620, "湖岸"), "seadramon_deep": (3230, 2680, "海龙兽深渊")},
    ),
    SubRegion(
        sub_region_id="ogremon_fortress",
        name="欧加兽的堡垒",
        name_en="Ogremon's Fortress",
        description="莽撞的欧加兽镇守的石堡,被击败后沦为他的杂货铺。",
        bounds=(3380, 2560, 3620, 2700),
        pois={"ogremon_shop": (3500, 2640, "奥加兽商店"), "fortress_wall": (3450, 2670, "堡垒外墙")},
    ),
    SubRegion(
        sub_region_id="factory_area",
        name="工厂地带",
        name_en="Factory Area",
        description="安杜路兽运行的机械工厂,齿轮与蒸汽构成的地下迷宫。",
        bounds=(3620, 2560, 3860, 2700),
        pois={"andromon_factory": (3730, 2620, "安杜路兽工厂"), "assembly_line": (3770, 2670, "流水线")},
    ),
    # ── 南带 (y: 2700-2900) ──
    SubRegion(
        sub_region_id="beach_of_departure",
        name="启程海滩",
        name_en="Beach of Departure",
        description="被选召的孩子们从夏令营坠落数码世界时最先到达的海滩。一切冒险的起点。",
        bounds=(2900, 2700, 3220, 2900),
        pois={"landing_spot": (3060, 2820, "降落点"), "campfire": (3000, 2860, "篝火营地")},
    ),
    SubRegion(
        sub_region_id="vending_machine_area",
        name="无人商店",
        name_en="Abandoned Vending Area",
        description="荒野中孤零零的自动售货机,为饥饿的被选召孩子提供生命线。",
        bounds=(3220, 2700, 3540, 2900),
        pois={"vending_machine": (3360, 2830, "自动售货机"), "open_field": (3400, 2770, "开阔地")},
    ),
    SubRegion(
        sub_region_id="toy_town",
        name="玩具城",
        name_en="Toy Town",
        description="熊仔兽(Monzaemon)统治的童话小镇,看似可爱却暗藏黑暗齿轮的控制。",
        bounds=(3540, 2700, 3860, 2900),
        pois={"toy_castle": (3700, 2820, "玩具城堡"), "monzaemon_throne": (3650, 2870, "熊仔兽王座")},
    ),
)

# ---- 内置地区数据 (Phase 17: 扩展至完整数码世界) ----
FILE_ISLAND = Region(
    region_id="file_island",
    name="文件岛",
    description="被选召的孩子们最初登陆的小岛,生活着幼年期~成熟期数码兽。位于数码世界右下角的近海岛屿。",
    bounds=(2900, 2300, 3860, 2900),
    pois={
        "beach_of_departure": (3073, 2768, "启程海滩"),
        "evolution_shrine": (3370, 2530, "进化神殿"),
        "ogremon_shop": (3645, 2780, "奥加兽的商店"),
    },
    sub_regions=_FILE_ISLAND_SUB_REGIONS,
)

INFINITY_MOUNTAIN = Region(
    region_id="infinity_mountain",
    name="无限山",
    description="数码世界中心,创世神栖息地。",
    bounds=(0, 0, WORLD_WIDTH, WORLD_HEIGHT),
    pois={
        "creators_altar": (480, 120, "创世者祭坛"),
    },
)

# Phase 8: 创始村 — 数码蛋重生的圣地
VILLAGE_OF_BEGINNINGS = Region(
    region_id="village_of_beginnings",
    name="创始村",
    description="数码世界的生命之源,战败的数码兽化作数码蛋在此重生。被选召的孩子们最初降落时最先感受到的温暖光芒。",
    bounds=(0, 0, WORLD_WIDTH, WORLD_HEIGHT),
    pois={
        "digitama_spring": (480, 500, "数码蛋之泉"),
        "elecmon_nursery": (400, 520, "艾力兽育幼院"),
    },
)

# ═══ Phase 17: 服务器大陆 — 左上主大陆 ═══
_SERVER_CONTINENT_SUB_REGIONS: tuple[SubRegion, ...] = (
    SubRegion(
        sub_region_id="desert_zone",
        name="沙漠地带",
        name_en="Desert Zone",
        description="一望无际的炽热沙漠,地面下埋藏着古代数码兽的化石。滚石兽群在此栖息,沙暴中隐约可见金字塔的轮廓。",
        bounds=(200, 200, 1000, 900),
        pois={"pyramid": (600, 500, "沙漠金字塔"), "oasis": (350, 700, "绿洲")},
        parent_region_id="server_continent",
    ),
    SubRegion(
        sub_region_id="steel_city",
        name="钢铁都市",
        name_en="Steel City",
        description="全金属构造的未来都市,摩天大楼直入云霄,大量机械系数码兽在此生活。安杜路兽的故乡。",
        bounds=(1000, 200, 1800, 900),
        pois={"central_tower": (1400, 400, "中央塔"), "steel_bridge": (1250, 650, "钢铁大桥")},
        parent_region_id="server_continent",
    ),
    SubRegion(
        sub_region_id="ancient_forest",
        name="古代森林",
        name_en="Ancient Forest",
        description="数码世界最古老的原始森林,巨树参天、藤蔓缠绕。妖精系数码兽的家园,据说隐藏着通往数码世界的初始之门。",
        bounds=(1800, 200, 2600, 900),
        pois={"world_tree": (2200, 450, "世界树"), "fairy_spring": (2400, 650, "妖精之泉")},
        parent_region_id="server_continent",
    ),
    SubRegion(
        sub_region_id="dark_city",
        name="黑暗之城",
        name_en="Dark City",
        description="被黑暗笼罩的破败都市,吸血魔兽的势力范围。街道空荡,只有暗巷中偶尔传来低语。",
        bounds=(2600, 200, 3200, 900),
        pois={"vamdemon_castle": (2900, 400, "吸血魔兽城堡"), "shadow_alley": (2750, 650, "暗影小巷")},
        parent_region_id="server_continent",
    ),
    SubRegion(
        sub_region_id="dragon_mountains",
        name="龙眠山脉",
        name_en="Dragon Mountains",
        description="横亘大陆的巍峨山脉,传说中远古龙系数码兽的沉睡之地。山巅终年积雪,山腹中流淌着熔岩河。",
        bounds=(200, 900, 1200, 1500),
        pois={"dragon_peak": (700, 1050, "龙神峰"), "lava_cave": (500, 1300, "熔岩洞")},
        parent_region_id="server_continent",
    ),
    SubRegion(
        sub_region_id="fairy_canyon",
        name="妖精峡谷",
        name_en="Fairy Canyon",
        description="两侧峭壁间流淌着发光的溪流,空气中弥漫着魔法花粉。仙女兽与妖精兽在此嬉戏,据说峡谷深处藏有神圣计划碎片。",
        bounds=(1200, 900, 2200, 1500),
        pois={"crystal_cave": (1700, 1100, "水晶洞穴"), "rainbow_bridge": (1500, 1350, "彩虹桥")},
        parent_region_id="server_continent",
    ),
    SubRegion(
        sub_region_id="machine_factory",
        name="机械工厂",
        name_en="Machine Factory",
        description="永不停歇的巨大工厂区,齿轮与传送带充斥每一寸土地。金属帝国的基础,大量机械系数码兽在这里被制造。",
        bounds=(2200, 900, 3200, 1500),
        pois={"main_forge": (2700, 1050, "主锻造炉"), "assembly_hall": (2500, 1350, "组装大厅")},
        parent_region_id="server_continent",
    ),
    SubRegion(
        sub_region_id="dark_ocean",
        name="暗黑海洋",
        name_en="Dark Ocean",
        description="服务器大陆南岸的漆黑海域,深不见底。达贡兽等深海恐怖生物潜伏其中,被选召的孩子曾在此迷失。",
        bounds=(200, 1500, 3200, 2100),
        pois={"abyss_edge": (1700, 1700, "深渊边缘"), "dark_whirlpool": (800, 1900, "黑暗漩涡")},
        parent_region_id="server_continent",
    ),
)

SERVER_CONTINENT = Region(
    region_id="server_continent",
    name="服务器大陆",
    description="数码世界的核心大陆,数码兽文明的主要发源地。四大天王曾在此建立各自的领地,留下了无数遗迹与传说。",
    bounds=(200, 200, 3200, 2100),
    pois={
        "central_plaza": (1700, 1000, "中央广场"),
        "dark_masters_gate": (1700, 1600, "四大天王之门"),
    },
    sub_regions=_SERVER_CONTINENT_SUB_REGIONS,
)

# ═══ Phase 17: 螺旋山 — 四大天王合体后的黑暗核心 ═══
_SPIRAL_MOUNTAIN_SUB_REGIONS: tuple[SubRegion, ...] = (
    SubRegion(
        sub_region_id="piedmon_palace",
        name="小丑皇宫",
        name_en="Piedmon's Palace",
        description="小丑皇的疯狂宫殿,布满机关陷阱和镜面迷宫。天花板上悬挂着被变成玩偶的数码兽,空气中回荡着小丑皇的尖笑。",
        bounds=(3300, 800, 3625, 1150),
        pois={"throne_room": (3462, 950, "王座之间"), "mirror_hall": (3400, 1050, "镜面大厅")},
        parent_region_id="spiral_mountain",
    ),
    SubRegion(
        sub_region_id="puppetmon_forest",
        name="木偶兽森林",
        name_en="Puppetmon's Forest",
        description="木偶兽用线操控的玩偶森林,看似童话般美丽却暗藏杀机。树木都是他的傀儡,任何闯入者都会变成新的「玩具」。",
        bounds=(3625, 800, 3950, 1150),
        pois={"puppet_house": (3787, 900, "木偶小屋"), "toy_graveyard": (3850, 1050, "玩具坟场")},
        parent_region_id="spiral_mountain",
    ),
    SubRegion(
        sub_region_id="metalseadramon_waters",
        name="钢铁海龙水域",
        name_en="MetalSeadramon's Waters",
        description="金属海龙兽统治的深海区域,水面覆盖着金属光泽的油膜。螺旋山的底部被这片漆黑水域包围,任何船只都无法靠近。",
        bounds=(3300, 1150, 3625, 1500),
        pois={"deep_trench": (3462, 1350, "海底深渊"), "metal_reef": (3400, 1250, "金属暗礁")},
        parent_region_id="spiral_mountain",
    ),
    SubRegion(
        sub_region_id="machinedramon_city",
        name="机械邪龙都市",
        name_en="Machinedramon's City",
        description="机械邪龙兽的机械化要塞,整座城市就是一台巨大的杀戮机器。无数炮台对准天空,任何飞过的数码兽都会被击落。",
        bounds=(3625, 1150, 3950, 1500),
        pois={"cannon_array": (3787, 1250, "无限炮台"), "central_core": (3850, 1400, "中央核心")},
        parent_region_id="spiral_mountain",
    ),
)

SPIRAL_MOUNTAIN = Region(
    region_id="spiral_mountain",
    name="螺旋山",
    description="四大天王合体后重塑的黑暗核心,数码世界最危险的地带。小丑皇、木偶兽、金属海龙兽、机械邪龙兽在此各自盘踞。",
    bounds=(3300, 800, 3950, 1500),
    pois={
        "spiral_summit": (3625, 900, "螺旋山顶"),
        "dark_masters_altar": (3625, 1150, "四大天王祭坛"),
    },
    sub_regions=_SPIRAL_MOUNTAIN_SUB_REGIONS,
)

# ═══ Phase 17: 无尽海 — 环绕大陆的广阔海洋 ═══
ENDLESS_OCEAN = Region(
    region_id="endless_ocean",
    name="无尽海",
    description="环绕数码世界的广袤海洋,连接文件岛与服务器大陆的水域。据说海底深处居住着钢铁海龙兽的残余部队和远古的深海数码兽。",
    bounds=(0, 0, WORLD_WIDTH, WORLD_HEIGHT),
    pois={
        "whirlpool_gate": (3500, 2000, "漩涡之门"),
        "sunken_ship": (1000, 2500, "沉船遗迹"),
        "coral_reef": (4000, 3000, "珊瑚礁群"),
    },
)

DEFAULT_REGIONS: dict[str, Region] = {
    "file_island": FILE_ISLAND,
    "infinity_mountain": INFINITY_MOUNTAIN,
    "village_of_beginnings": VILLAGE_OF_BEGINNINGS,
    "server_continent": SERVER_CONTINENT,
    "spiral_mountain": SPIRAL_MOUNTAIN,
    "endless_ocean": ENDLESS_OCEAN,
}


class WorldState:
    """整个世界的当前状态(单例)。

    Phase 1: 内存中维护,单进程。
    Phase 4: 加 SQLite 持久化,加多进程同步(可能用 asyncio Lock 替代 threading.Lock)。
    """

    def __init__(
        self,
        regions: Optional[dict[str, Region]] = None,
        seasons_enabled: bool = True,
        world_id: str | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.regions: dict[str, Region] = regions or dict(DEFAULT_REGIONS)
        self.agents: dict[str, DigimonAgent] = {}
        self.events: list[dict[str, Any]] = []
        self.created_at: datetime = datetime.now()
        # 世界时间(独立于现实时间): 现实 1 秒 = 世界 1 分钟 (默认)
        self.real_to_world_ratio: int = 60
        # Phase 7: 因果链 —— 事件 ID 自增计数器
        self._next_event_id: int = 0
        # Phase 9: 季节系统开关(创建世界时可关闭)
        self.seasons_enabled: bool = seasons_enabled
        # Phase 9: 世界 id(多元宇宙中唯一标识,默认新建时不设置)
        self.world_id: str | None = world_id

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

    # ---- 创始村重生 (Phase 8) ----

    def rebirth_at_village(self, agent: DigimonAgent) -> dict[str, Any]:
        """战败数码兽在创始村重生为数码蛋。

        规则:
        - 重置 location 到创始村 (digitama_spring 附近)
        - 重置 region_id 为 village_of_beginnings
        - 重置 stage 为 BABY_I (数码蛋)
        - 重置 stats 为基础值
        - 保留 importance >= 7 的记忆,其余清空
        - HP 恢复为初始值
        - battle_victories 清零

        Returns:
            重生事件字典。
        """
        # 保留高重要性记忆
        kept_memories = [
            m for m in agent.memory.entries
            if m.importance >= 7
        ]

        # 清空并恢复
        agent.memory.entries.clear()
        for m in kept_memories:
            agent.memory.entries.append(m)

        # 重置状态
        agent.stage = EvolutionStage.BABY_I
        agent.species = f"{agent.name}_digitama"  # 数码蛋状态
        agent.region_id = "village_of_beginnings"
        agent.location = (480, 500)  # digitama_spring
        agent.stats = DigimonStats(
            hp=20, max_hp=20, ep=10, max_ep=10,
            attack=5, defense=5, speed=5,
        )
        agent.battle_victories = 0
        agent.mood = "calm"
        agent.mood_state = {"joy": 0.0, "sadness": 0.0, "anger": 0.0, "fear": 0.0}
        agent.current_plan = "从数码蛋中苏醒,感受创始村的温暖"

        # 写重生记忆
        desc = "I was defeated but reborn as a Digitama at the Village of Beginnings."
        agent.memory.add(
            event={"description": desc, "type": "rebirth"},
            importance=10,
            memory_type="observation",
        )

        rebirth_event = {
            "type": "rebirth",
            "agent": agent.name,
            "description": f"{agent.name} 在创始村重生为数码蛋,新一轮冒险开始了。",
            "importance": 10,
            "source": "village_of_beginnings",
        }
        self.events.append(rebirth_event)
        return rebirth_event
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
                "seasons_enabled": self.seasons_enabled,
                "world_id": self.world_id,
            }


# ---- 进程级单例 ----
_state: Optional[WorldState] = None

# Phase 11: 数码兽种群数据 (共 100 只)
# Phase 17 更新: 分散到服务器大陆、螺旋山、文件岛、无限山
# Phase 扩容 30→100: 文件岛20 + 服务器大陆50 + 螺旋山20 + 无限山10
# 分类: 疫苗种(VACCINE) / 数据种(DATA) / 病毒种(VIRUS) / 自由种(FREE)
# 每个物种最多出现4次, 每个名字独一无二, 位置不重叠
_ALL_DIGIMON_SEEDS: tuple[dict, ...] = (
    # ═══ 文件岛 (20只) — 疫苗种为主,核心8只+12只进化体/幼体 ═══
    {"name": "亚古兽", "species": "agumon", "attribute": "vaccine", "region": "file_island", "pos": (3569, 2429), "plan": "在启程海滩附近闲逛觅食"},
    {"name": "加布兽", "species": "gabumon", "attribute": "vaccine", "region": "file_island", "pos": (2940, 2596), "plan": "安静地观察周围的动静"},
    {"name": "比丘兽", "species": "biyomon", "attribute": "vaccine", "region": "file_island", "pos": (3165, 2543), "plan": "在天空中巡视文件岛"},
    {"name": "甲虫兽", "species": "tentomon", "attribute": "vaccine", "region": "file_island", "pos": (3057, 2419), "plan": "在迷乱森林里寻找食物"},
    {"name": "巴鲁兽", "species": "palmon", "attribute": "vaccine", "region": "file_island", "pos": (3607, 2873), "plan": "在齿轮草原晒太阳光合作用"},
    {"name": "哥玛兽", "species": "gomamon", "attribute": "vaccine", "region": "file_island", "pos": (3004, 2747), "plan": "在启程海滩玩水嬉戏"},
    {"name": "巴达兽", "species": "patamon", "attribute": "vaccine", "region": "file_island", "pos": (2947, 2345), "plan": "在空中飞行俯瞰全岛"},
    {"name": "迪路兽", "species": "tailmon", "attribute": "vaccine", "region": "file_island", "pos": (3010, 2538), "plan": "在无限山上巡视警戒"},
    {"name": "暴龙亚古", "species": "agumon", "attribute": "vaccine", "region": "file_island", "pos": (3153, 2832), "plan": "在古代恐龙境散步巡查"},
    {"name": "森林加布", "species": "gabumon", "attribute": "vaccine", "region": "file_island", "pos": (3531, 2342), "plan": "在迷乱森林深处巡逻"},
    {"name": "冰原亚古", "species": "agumon", "attribute": "vaccine", "region": "file_island", "pos": (3489, 2518), "plan": "在冰冻地带抵御寒冷"},
    {"name": "山地加布", "species": "gabumon", "attribute": "vaccine", "region": "file_island", "pos": (3648, 2873), "plan": "在密哈拉西山瞭望"},
    {"name": "小狗兽", "species": "plotmon", "attribute": "vaccine", "region": "file_island", "pos": (3344, 2540), "plan": "在玩具城附近嬉戏玩耍"},
    {"name": "荒野暴龙", "species": "greymon", "attribute": "vaccine", "region": "file_island", "pos": (3374, 2599), "plan": "在古代恐龙境守护领地"},
    {"name": "雪狼加鲁鲁", "species": "garurumon", "attribute": "vaccine", "region": "file_island", "pos": (3743, 2321), "plan": "在冰冻地带狩猎"},
    {"name": "烈焰巴多拉", "species": "birdramon", "attribute": "vaccine", "region": "file_island", "pos": (3692, 2478), "plan": "从空中巡逻齿轮草原"},
    {"name": "荆棘仙人掌", "species": "togemon", "attribute": "data", "region": "file_island", "pos": (3629, 2747), "plan": "在无人商店附近寻找水源"},
    {"name": "铁甲比多", "species": "kabuterimon", "attribute": "vaccine", "region": "file_island", "pos": (3263, 2599), "plan": "在迷乱森林上空飞行"},
    {"name": "圣翼天使", "species": "angemon", "attribute": "vaccine", "region": "file_island", "pos": (3074, 2535), "plan": "在无限山顶守护进化神殿"},
    {"name": "雪域海狮", "species": "ikkakumon", "attribute": "vaccine", "region": "file_island", "pos": (3696, 2659), "plan": "在龙眼湖中游泳凉快"},
    # ═══ 服务器大陆 (50只) ═══
    {"name": "沙地亚古", "species": "agumon", "attribute": "vaccine", "region": "server_continent", "pos": (319, 309), "plan": "在沙漠中寻找绿洲水源"},
    {"name": "炽热艾力", "species": "elecmon", "attribute": "data", "region": "server_continent", "pos": (604, 314), "plan": "在沙漠金字塔附近巡逻"},
    {"name": "沙漠独角", "species": "tsunomon", "attribute": "free", "region": "server_continent", "pos": (582, 567), "plan": "在绿洲附近躲避烈日"},
    {"name": "烈火暴龙", "species": "greymon", "attribute": "vaccine", "region": "server_continent", "pos": (833, 485), "plan": "在沙漠中巡逻寻找食物"},
    {"name": "沙暴比丘", "species": "biyomon", "attribute": "vaccine", "region": "server_continent", "pos": (259, 685), "plan": "在沙漠上空寻找绿洲"},
    {"name": "沙漠狮子", "species": "leomon", "attribute": "free", "region": "server_continent", "pos": (764, 342), "plan": "在沙漠中守护金字塔"},
    {"name": "安杜路兽", "species": "andromon", "attribute": "data", "region": "server_continent", "pos": (1402, 295), "plan": "在中央塔维护系统运行"},
    {"name": "守卫兽", "species": "guardromon", "attribute": "data", "region": "server_continent", "pos": (1580, 515), "plan": "在钢铁大桥巡逻警戒"},
    {"name": "钢铁齿轮", "species": "hagurumon", "attribute": "data", "region": "server_continent", "pos": (1658, 848), "plan": "在城市管道中穿梭巡检"},
    {"name": "重装守卫", "species": "guardromon", "attribute": "data", "region": "server_continent", "pos": (1385, 806), "plan": "在都市外围巡逻"},
    {"name": "机械安杜", "species": "andromon", "attribute": "data", "region": "server_continent", "pos": (1211, 286), "plan": "在钢铁大桥检修设备"},
    {"name": "精密齿轮", "species": "hagurumon", "attribute": "data", "region": "server_continent", "pos": (1061, 448), "plan": "在中央塔计算数据"},
    {"name": "森林暴龙", "species": "greymon", "attribute": "vaccine", "region": "server_continent", "pos": (2111, 296), "plan": "在世界树下守护领地"},
    {"name": "丛林加鲁鲁", "species": "garurumon", "attribute": "vaccine", "region": "server_continent", "pos": (2053, 318), "plan": "在古代森林中巡视狩猎"},
    {"name": "密林比多", "species": "kabuterimon", "attribute": "vaccine", "region": "server_continent", "pos": (2204, 499), "plan": "在巨树间飞行觅食"},
    {"name": "翠绿巴鲁", "species": "palmon", "attribute": "vaccine", "region": "server_continent", "pos": (2279, 865), "plan": "在世界树下光合作用"},
    {"name": "森之妖精", "species": "tailmon", "attribute": "vaccine", "region": "server_continent", "pos": (2188, 381), "plan": "在妖精之泉附近守护"},
    {"name": "古木仙人掌", "species": "togemon", "attribute": "data", "region": "server_continent", "pos": (2194, 578), "plan": "在密林中巡逻警戒"},
    {"name": "恶魔兽", "species": "devimon", "attribute": "virus", "region": "server_continent", "pos": (2829, 488), "plan": "在城堡中策划黑暗阴谋"},
    {"name": "奥加兽", "species": "ogremon", "attribute": "virus", "region": "server_continent", "pos": (2688, 838), "plan": "在暗影小巷中巡逻恐吓"},
    {"name": "暗影恶魔", "species": "devimon", "attribute": "virus", "region": "server_continent", "pos": (2790, 761), "plan": "在黑暗之城中潜伏等待"},
    {"name": "狂战士奥加", "species": "ogremon", "attribute": "virus", "region": "server_continent", "pos": (2865, 382), "plan": "在城堡外围巡逻警戒"},
    {"name": "漆黑恶魔", "species": "devimon", "attribute": "virus", "region": "server_continent", "pos": (3088, 603), "plan": "在城堡深处研究黑魔法"},
    {"name": "暴怒奥加", "species": "ogremon", "attribute": "virus", "region": "server_continent", "pos": (2891, 870), "plan": "在暗影小巷中埋伏猎物"},
    {"name": "罪痕恶魔", "species": "devimon", "attribute": "virus", "region": "server_continent", "pos": (3185, 439), "plan": "在城墙上巡视领地"},
    {"name": "暗影狮子", "species": "leomon", "attribute": "free", "region": "server_continent", "pos": (2947, 272), "plan": "在废墟中潜伏收集情报"},
    {"name": "海龙兽", "species": "seadramon", "attribute": "data", "region": "server_continent", "pos": (449, 947), "plan": "在龙神湖中游弋觅食"},
    {"name": "龙角幼兽", "species": "tsunomon", "attribute": "free", "region": "server_continent", "pos": (1039, 1238), "plan": "在龙神峰附近修炼"},
    {"name": "熔岩海龙", "species": "seadramon", "attribute": "data", "region": "server_continent", "pos": (625, 1189), "plan": "在熔岩河中游弋"},
    {"name": "山脉加鲁鲁", "species": "garurumon", "attribute": "vaccine", "region": "server_continent", "pos": (282, 1131), "plan": "在山脊上巡视狩猎"},
    {"name": "龙脉巨鲸", "species": "whamon", "attribute": "vaccine", "region": "server_continent", "pos": (1150, 1237), "plan": "在龙神湖深处沉睡"},
    {"name": "妖精巴多拉", "species": "birdramon", "attribute": "vaccine", "region": "server_continent", "pos": (1432, 1426), "plan": "在峡谷上空盘旋巡视"},
    {"name": "彩虹海狮", "species": "ikkakumon", "attribute": "vaccine", "region": "server_continent", "pos": (1620, 1384), "plan": "在妖精之泉中嬉戏"},
    {"name": "水晶比丘", "species": "biyomon", "attribute": "vaccine", "region": "server_continent", "pos": (1361, 1186), "plan": "在水晶洞穴附近飞行"},
    {"name": "彩虹巴鲁", "species": "palmon", "attribute": "vaccine", "region": "server_continent", "pos": (1357, 1167), "plan": "在彩虹桥附近开花绽放"},
    {"name": "妖精甲虫", "species": "tentomon", "attribute": "vaccine", "region": "server_continent", "pos": (1977, 1466), "plan": "在花丛中采集花粉"},
    {"name": "峡谷哥玛", "species": "gomamon", "attribute": "vaccine", "region": "server_continent", "pos": (1484, 1353), "plan": "在发光溪流中游泳"},
    {"name": "晶翼巴达", "species": "patamon", "attribute": "vaccine", "region": "server_continent", "pos": (2134, 1323), "plan": "在水晶洞穴中探索"},
    {"name": "花仙迪路", "species": "tailmon", "attribute": "vaccine", "region": "server_continent", "pos": (1585, 1139), "plan": "在妖精峡谷中巡视"},
    {"name": "工厂齿轮", "species": "hagurumon", "attribute": "data", "region": "server_continent", "pos": (2356, 1436), "plan": "在主锻造炉计算数据"},
    {"name": "组装比多", "species": "kabuterimon", "attribute": "vaccine", "region": "server_continent", "pos": (2720, 1008), "plan": "在组装大厅巡视检查"},
    {"name": "钢铁安杜", "species": "andromon", "attribute": "data", "region": "server_continent", "pos": (2988, 963), "plan": "在流水线上监控生产"},
    {"name": "焊接齿轮", "species": "hagurumon", "attribute": "data", "region": "server_continent", "pos": (3096, 1027), "plan": "在机械臂间穿梭维修"},
    {"name": "机械守卫", "species": "guardromon", "attribute": "data", "region": "server_continent", "pos": (2371, 1078), "plan": "在工厂门口站岗警戒"},
    {"name": "锻造海龙", "species": "seadramon", "attribute": "data", "region": "server_continent", "pos": (3026, 1347), "plan": "在冷却池中巡逻"},
    {"name": "深渊巨鲸", "species": "whamon", "attribute": "vaccine", "region": "server_continent", "pos": (2657, 1580), "plan": "在深渊海域巡游守卫"},
    {"name": "暗海狮子", "species": "leomon", "attribute": "free", "region": "server_continent", "pos": (1791, 1905), "plan": "在黑暗漩涡附近守卫正义"},
    {"name": "深海海龙", "species": "seadramon", "attribute": "data", "region": "server_continent", "pos": (2655, 1994), "plan": "在暗黑海洋深处游弋"},
    {"name": "白浪海狮", "species": "ikkakumon", "attribute": "vaccine", "region": "server_continent", "pos": (2382, 1772), "plan": "在海面浮冰上休息"},
    {"name": "深渊艾力", "species": "elecmon", "attribute": "data", "region": "server_continent", "pos": (2481, 1526), "plan": "在海岸附近巡逻放电"},
    # ═══ 螺旋山 (20只) — 高级数码兽(完全体/究极体) ═══
    {"name": "机械暴龙兽", "species": "metal_greymon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3432, 1364), "plan": "在小丑皇宫外围巡逻警戒"},
    {"name": "兽人加鲁鲁", "species": "were_garurumon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3588, 1471), "plan": "在钢铁海龙水域侦察敌情"},
    {"name": "伽楼达兽", "species": "garudamon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3663, 929), "plan": "在木偶兽森林上空巡视"},
    {"name": "超比多兽", "species": "atlur_kabuterimon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3615, 1260), "plan": "在机械邪龙都市侦察情报"},
    {"name": "武装暴龙", "species": "metal_greymon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3476, 1279), "plan": "在木偶兽森林中搜索玩具兵"},
    {"name": "暗夜加鲁鲁", "species": "were_garurumon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3318, 1084), "plan": "在暗处监视机械邪龙动向"},
    {"name": "烈焰伽楼达", "species": "garudamon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3827, 997), "plan": "在小丑皇宫上方侦察"},
    {"name": "装甲比多", "species": "atlur_kabuterimon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3834, 923), "plan": "在钢铁海龙水域巡逻"},
    {"name": "螺旋巴鲁", "species": "palmon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3620, 1469), "plan": "在木偶兽森林中悄悄穿行"},
    {"name": "钢铁加鲁鲁", "species": "garurumon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3834, 1438), "plan": "在机械邪龙都市附近侦察"},
    {"name": "暗黑巴多拉", "species": "birdramon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3518, 971), "plan": "在螺旋山上空盘旋侦察"},
    {"name": "毒刺仙人掌", "species": "togemon", "attribute": "data", "region": "spiral_mountain", "pos": (3697, 980), "plan": "在玩具坟场中埋伏"},
    {"name": "堕天使兽", "species": "angemon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3867, 1358), "plan": "在小丑皇宫深处潜伏"},
    {"name": "风暴比多", "species": "kabuterimon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3315, 1428), "plan": "在螺旋山风暴中飞行"},
    {"name": "巨型海狮", "species": "ikkakumon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3646, 1315), "plan": "在钢铁海龙水域巡逻"},
    {"name": "冥海巨鲸", "species": "whamon", "attribute": "vaccine", "region": "spiral_mountain", "pos": (3334, 929), "plan": "在黑暗水域中巡游"},
    {"name": "黑暗艾力", "species": "elecmon", "attribute": "data", "region": "spiral_mountain", "pos": (3686, 1129), "plan": "在机械邪龙都市充电"},
    {"name": "螺旋守卫", "species": "guardromon", "attribute": "data", "region": "spiral_mountain", "pos": (3560, 874), "plan": "在小丑皇宫入口守卫"},
    {"name": "邪龙安杜", "species": "andromon", "attribute": "data", "region": "spiral_mountain", "pos": (3561, 1395), "plan": "在螺旋山顶维修设备"},
    {"name": "噩梦幻兽", "species": "ogremon", "attribute": "virus", "region": "spiral_mountain", "pos": (3395, 902), "plan": "在四大天王祭坛巡逻"},
    # ═══ 无限山 (10只) — 守护者+天使系数码兽 ═══
    {"name": "圣天使兽", "species": "angemon", "attribute": "vaccine", "region": "infinity_mountain", "pos": (3012, 2005), "plan": "守护创世者祭坛"},
    {"name": "圣光小狗", "species": "plotmon", "attribute": "vaccine", "region": "infinity_mountain", "pos": (3357, 298), "plan": "在无限山修炼祈祷"},
    {"name": "神圣巴达", "species": "patamon", "attribute": "vaccine", "region": "infinity_mountain", "pos": (3130, 2196), "plan": "在无限山上空飞翔"},
    {"name": "天光迪路", "species": "tailmon", "attribute": "vaccine", "region": "infinity_mountain", "pos": (3151, 530), "plan": "在祭坛附近巡逻"},
    {"name": "守护狮子", "species": "leomon", "attribute": "free", "region": "infinity_mountain", "pos": (540, 2717), "plan": "守护无限山入口"},
    {"name": "圣翼巴多拉", "species": "birdramon", "attribute": "vaccine", "region": "infinity_mountain", "pos": (1961, 2266), "plan": "在无限山上空盘旋守护"},
    {"name": "明光比丘", "species": "biyomon", "attribute": "vaccine", "region": "infinity_mountain", "pos": (691, 1100), "plan": "在祭坛附近歌唱"},
    {"name": "辉光小狗", "species": "plotmon", "attribute": "vaccine", "region": "infinity_mountain", "pos": (2176, 2499), "plan": "在圣山脚下巡逻"},
    {"name": "神殿艾力", "species": "elecmon", "attribute": "data", "region": "infinity_mountain", "pos": (1748, 882), "plan": "在神殿外围放哨"},
    {"name": "圣山独角", "species": "tsunomon", "attribute": "free", "region": "infinity_mountain", "pos": (3819, 2223), "plan": "在山脚下安静修炼"},
)

# 随机欲望池
_LATENT_DESIRES = (
    "想变强", "想交朋友", "想吃东西", "想探索新区域",
    "想保护家园", "想成为最强数码兽", "想找到数码蛋", "想独自安静生活",
    "想组建团队", "想复仇", "想学习新技能", "想守护同伴",
    "想支配数码世界", "想找到训练师", "想到达进化神殿", "想回到创始村",
)

def _spawn_from_seed(world: WorldState, seed: dict) -> DigimonAgent:
    """从种子数据创建一只数码兽,附随机欲望。"""
    attr_map = {
        "vaccine": DigimonAttribute.VACCINE,
        "data": DigimonAttribute.DATA,
        "virus": DigimonAttribute.VIRUS,
        "free": DigimonAttribute.FREE,
    }
    agent = DigimonAgent(
        name=seed["name"],
        species=seed["species"],
        attribute=attr_map.get(seed["attribute"], DigimonAttribute.FREE),
        region_id=seed["region"],
        location=seed["pos"],
        current_plan=seed["plan"],
    )
    agent.latent_desire = _random.choice(_LATENT_DESIRES)
    agent.desire_strength = round(_random.uniform(0.3, 0.9), 2)
    return agent


def get_world() -> WorldState:
    """获取(或延迟初始化)世界单例。

    Phase 扩容 30→100: 文件岛(20只)、服务器大陆(50只)、螺旋山(20只)、无限山(10只)。
    不同属性: 疫苗种/数据种/病毒种/自由种。
    每只初始 latent_desire 随机生成。
    """
    global _state
    if _state is None:
        _state = WorldState(world_id="prime")
        for seed in _ALL_DIGIMON_SEEDS:
            agent = _spawn_from_seed(_state, seed)
            _state.spawn(agent)
    return _state


def reset_world() -> None:
    """重置世界(测试用)。"""
    global _state
    _state = None

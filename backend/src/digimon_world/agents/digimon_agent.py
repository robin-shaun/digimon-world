"""
DigimonAgent - 数码兽智能体核心循环
====================================

参考 Stanford Generative Agents (Park et al., 2023) 的 persona.py,
本类实现数码兽自主行为循环: Observe → Memory → Reflect → Plan → Act

设计要点:
- 循环在 WorldClock 驱动下周期性执行(不是自己 sleep)
- 每个 agent 独立,有自己的 LLM 客户端引用(分模型: opus 反思, haiku 移动)
- 状态可序列化,跨进程持久化

详细设计: docs/DESIGN.md 第 3 节
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, ClassVar, Optional, TYPE_CHECKING

from ..memory.memory_stream import MemoryStream

if TYPE_CHECKING:
    from .planner import Planner
    from .reflector import Reflector
    from ..world.world_state import Region

logger = logging.getLogger(__name__)


class EvolutionStage(str, Enum):
    """数码兽的进化阶段。"""

    BABY_I = "baby_i"          # 幼年期 I
    BABY_II = "baby_ii"        # 幼年期 II / 成长期
    ROOKIE = "rookie"          # 成熟期
    CHAMPION = "champion"      # 完全体
    MEGA = "mega"              # 究极体


class DigimonAttribute(str, Enum):
    """数码兽的属性(克制关系)。"""

    VACCINE = "vaccine"        # 疫苗种 - 克制 virus
    DATA = "data"              # 数据种 - 克制 vaccine
    VIRUS = "virus"            # 病毒种 - 克制 data
    FREE = "free"              # 自由种 - 无克制


@dataclass
class DigimonStats:
    """数码兽的基础数值。"""

    hp: int = 100          # 生命值
    max_hp: int = 100
    ep: int = 50           # 能量(技能消耗)
    max_ep: int = 50
    attack: int = 20
    defense: int = 15
    speed: int = 15
    bond: int = 0          # 羁绊值(0-100),与训练师/被选召孩子
    # TODO(Phase 3): 战斗技能列表
    skills: list[str] = field(default_factory=list)


@dataclass
class DigimonAgent:
    """一只数码兽。

    Attributes:
        name: 数码兽名字(如"亚古兽")
        species: 物种(如"亚古兽"对应 digimon_species_id="agumon")
        stage: 当前进化阶段
        attribute: 属性(疫苗/数据/病毒/自由)
        region_id: 所在地区
        location: 所在具体地点(用坐标或地点 ID 表示)
        stats: 战斗数值
        memory: 记忆流
        current_plan: 当前计划(简短字符串,Phase 2 实现完整 Plan 树)
    """

    name: str
    species: str
    stage: EvolutionStage = EvolutionStage.ROOKIE
    attribute: DigimonAttribute = DigimonAttribute.VACCINE
    region_id: str = "file_island"
    location: tuple[int, int] = (0, 0)
    stats: DigimonStats = field(default_factory=DigimonStats)
    memory: MemoryStream = field(default_factory=MemoryStream)
    current_plan: Optional[str] = None
    mood: str = "calm"  # calm/excited/tired/scared/curious
    # 隐性目标: 反思时由 LLM 浮现出的一句内心渴望(如"想变强"),
    # 以及它的强烈度(0-1)。影响 plan_next() 的行动倾向。
    latent_desire: str = ""
    desire_strength: float = 0.0
    reflector: Optional["Reflector"] = field(default=None, repr=False)
    planner: Optional["Planner"] = field(default=None, repr=False)
    last_reflection_at: Optional[datetime] = None
    last_planned_at: Optional[datetime] = None
    # 最近一次与其它数码兽互动(对话)的世界时刻,用于互动冷却
    last_interaction_at: Optional[datetime] = None
    # Phase 3: 战斗胜利累计(用于触发进化)。由 battle API 在赢家身上 +1。
    battle_victories: int = 0

    def observe(self, event: dict[str, Any]) -> None:
        """观察一个世界事件,写入记忆流。

        重要程度评分: TODO(Phase 2) 接入 LLM 评估,先用启发式。
        """
        importance = self._heuristic_importance(event)
        self.memory.add(event=event, importance=importance)

    def _heuristic_importance(self, event: dict[str, Any]) -> int:
        """启发式重要性评分(1-10),Phase 2 替换为 LLM。"""
        et = event.get("type", "")
        if et in {"battle_victory", "evolution", "near_death"}:
            return 9
        if et in {"first_meet", "gift_received", "threat"}:
            return 7
        if et in {"moved", "ate", "rested"}:
            return 3
        return 5

    async def reflect_if_needed(self) -> None:
        """如果记忆累积到阈值,触发反思。

        反思频率: 30 分钟世界时间内最多一次。
        需要 self.reflector 已设置,否则静默跳过。
        """
        if self.reflector is None:
            return
        if not self.memory.should_reflect():
            return
        # 30 分钟冷却
        now = datetime.utcnow()
        if self.last_reflection_at is not None:
            elapsed = (now - self.last_reflection_at).total_seconds()
            if elapsed < 30 * 60:
                return
        result = await self.reflector.reflect(self)
        if result:
            self.last_reflection_at = now
            # 用最后一条反思浮现出的渴望更新隐性目标(仅当非空时覆盖,
            # 避免一次没解析出 desire 的反思清掉已有渴望)。
            latest = result[-1]
            if latest.desire:
                self.latent_desire = latest.desire
                self.desire_strength = latest.desire_strength

    async def plan_next(self, world_state_snapshot: dict | None = None) -> str:
        """根据记忆和当前状态,调用 Planner 生成下一段计划。

        Returns:
            计划字符串,同时写入 self.current_plan 和 self.last_planned_at。
        """
        if self.planner is None:
            from .planner import FALLBACK_PLAN
            self.current_plan = FALLBACK_PLAN
            return FALLBACK_PLAN

        plan = await self.planner.plan(self, world_state_snapshot or {})
        self.current_plan = plan
        self.last_planned_at = datetime.utcnow()
        return plan

    # 默认步长(像素/一次 act),Phase 2 暂用常量;后续可由 mood/性格/EP 决定
    DEFAULT_STEP: ClassVar[int] = 12

    # 方向关键词 → (dx, dy) 的多对多映射
    # 中文世界偏好: 左/右/东/西 + 上/下/北/南
    DIRECTION_KEYWORDS: ClassVar[dict[str, tuple[int, int]]] = {
        "左": (-1, 0), "西": (-1, 0),
        "右": (1, 0),  "东": (1, 0),
        "上": (0, -1), "北": (0, -1), "天": (0, -1), "空中": (0, -1), "高处": (0, -1),
        "下": (0, 1),  "南": (0, 1),  "地": (0, 1),  "低处": (0, 1),
    }

    def get_bounds(
        self, regions: dict[str, "Region"] | None
    ) -> Optional[tuple[int, int, int, int]]:
        """查自己所在 region 的移动边界 (min_x, min_y, max_x, max_y)。

        Args:
            regions: region_id -> Region 的映射(通常是 WorldState.regions)。
                     传 None 或查不到对应 region 时返回 None。

        Returns:
            边界四元组;拿不到时返回 None(调用方据此跳过移动)。
        """
        if not regions:
            return None
        region = regions.get(self.region_id)
        if region is None:
            return None
        return region.bounds

    def act(
        self, regions: dict[str, "Region"] | None = None
    ) -> dict[str, Any]:
        """执行当前计划的第一步,产生世界事件。

        Phase 2 简化版: 不调 LLM,直接用关键词解析当前计划,
        推断一个方向位移,更新 self.location,返回世界事件 dict。

        支持的意图(按 plan 文本里的关键词识别):
        - 移动: 含 "走 / 移动 / 去 / 飞 / 爬 / 跑 / 逛" + 方向词
        - 巡视/观察: 位置不变,返回 "observed" 事件
        - 休息/睡觉/等待: 位置不变,返回 "rested" 事件
        - 其它/无计划: 兜底为小幅随机走一步(伪随机,基于 self.next_id 做种子)

        Args:
            regions: region_id -> Region 映射,用于把移动夹紧在地区边界内。
                     传 None(如单元测试直接调 act())时退化为仅夹紧非负,
                     行为与旧版一致。传了但查不到自己的 region_id 时,
                     跳过本次移动并记 warning(避免走出世界)。

        Returns:
            世界事件 dict, 例如:
                {"type": "moved", "agent": name,
                 "from": [x, y], "to": [x', y'],
                 "plan": "...", "at": iso}

            调用方负责把事件写入 WorldState.events 与自身记忆。
        """
        plan = self.current_plan or ""
        now_iso = datetime.utcnow().isoformat()

        # 拿边界: regions 显式传入时才生效。
        # - regions 为 None(如直接单测 act()) → bounds=None,退化为仅非负夹紧。
        # - regions 传了但查不到自己的 region_id → 跳过所有移动,记 warning。
        bounds = self.get_bounds(regions)
        region_unknown = regions is not None and bounds is None

        def _clamp(nx: int, ny: int) -> tuple[int, int]:
            """把坐标夹紧到边界内(无边界时仅保证非负)。"""
            if bounds is not None:
                min_x, min_y, max_x, max_y = bounds
                return (max(min_x, min(max_x, nx)), max(min_y, min(max_y, ny)))
            return (max(0, nx), max(0, ny))

        # ---- 1. 移动意图 ----
        move_triggers = {"走", "移动", "去", "飞", "爬", "跑", "逛", "前往", "溜达", "赶"}
        if any(k in plan for k in move_triggers):
            if region_unknown:
                logger.warning(
                    "agent %s 的 region_id=%r 不在 regions 中,跳过移动",
                    self.name, self.region_id,
                )
                return self._stay_event(plan, now_iso)

            dx_total = dy_total = 0
            for kw, (dx, dy) in self.DIRECTION_KEYWORDS.items():
                if kw in plan:
                    dx_total += dx
                    dy_total += dy
            # 没识别出方向 → 4 方向伪随机之一
            # 旧实现固定 (1, 0) 永远向右,会让所有数码兽一路贴到右边界。
            # 必须不依赖 wall clock(测试稳定),不依赖 memory.next_id 单调
            # (act() 单测里 next_id 不递增,只有 step() 才会)。
            # 解法: hash(agent_id + fallback_call_count) % 4
            #   - fallback_call_count 是实例级,每次 act() 触发 fallback 递增
            #   - 不同 agent 起始方向不同,避免群体同步
            #   - 完全确定性,无 wall clock,测试稳定
            if dx_total == 0 and dy_total == 0:
                if not hasattr(self, "_fallback_count"):
                    self._fallback_count = 0
                self._fallback_count += 1
                import hashlib
                seed_str = f"{self.name}:{self._fallback_count}"
                h = hashlib.md5(seed_str.encode()).hexdigest()
                idx = int(h, 16) % 4
                dx_total, dy_total = [(0, -1), (1, 0), (0, 1), (-1, 0)][idx]

            step = self.DEFAULT_STEP
            dx = dx_total * step
            dy = dy_total * step
            old_x, old_y = self.location
            new_x, new_y = _clamp(old_x + dx, old_y + dy)
            self.location = (new_x, new_y)
            return {
                "type": "moved",
                "agent": self.name,
                "from": [old_x, old_y],
                "to": [new_x, new_y],
                "plan": plan,
                "at": now_iso,
            }

        # ---- 2. 观察/巡视 ----
        observe_triggers = {"观察", "巡视", "看", "注意", "听", "嗅", "探查"}
        if any(k in plan for k in observe_triggers):
            return {
                "type": "observed",
                "agent": self.name,
                "location": list(self.location),
                "plan": plan,
                "at": now_iso,
            }

        # ---- 3. 休息 ----
        rest_triggers = {"休息", "睡觉", "睡", "等待", "发呆", "停"}
        if any(k in plan for k in rest_triggers):
            return {
                "type": "rested",
                "agent": self.name,
                "location": list(self.location),
                "plan": plan,
                "at": now_iso,
            }

        # ---- 4. 兜底: 伪随机小步 ----
        if region_unknown:
            logger.warning(
                "agent %s 的 region_id=%r 不在 regions 中,跳过兜底移动",
                self.name, self.region_id,
            )
            return self._stay_event(plan, now_iso, fallback=True)

        # 用 self.memory.next_id 当种子(保证可复现)
        seed = self.memory.next_id
        # 4 个方向之一
        idx = seed % 4
        direction = [(0, -1), (1, 0), (0, 1), (-1, 0)][idx]
        step = self.DEFAULT_STEP // 2  # 兜底步长小一点
        old_x, old_y = self.location
        new_x, new_y = _clamp(old_x + direction[0] * step, old_y + direction[1] * step)
        self.location = (new_x, new_y)
        return {
            "type": "moved",
            "agent": self.name,
            "from": [old_x, old_y],
            "to": [new_x, new_y],
            "plan": plan,
            "at": now_iso,
            "fallback": True,
        }

    def _stay_event(
        self, plan: str, now_iso: str, fallback: bool = False
    ) -> dict[str, Any]:
        """region 未知时用的原地事件: 位置不动,标记 skipped 原因。"""
        old_x, old_y = self.location
        event = {
            "type": "moved",
            "agent": self.name,
            "from": [old_x, old_y],
            "to": [old_x, old_y],
            "plan": plan,
            "at": now_iso,
            "skipped": "unknown_region",
        }
        if fallback:
            event["fallback"] = True
        return event

    async def step(
        self, regions: dict[str, "Region"] | None = None
    ) -> dict[str, Any]:
        """主循环一步: observe → reflect_if_needed → plan_next → act。

        Args:
            regions: region_id -> Region 映射,透传给 act() 做边界夹紧。
                     scheduler 会传 WorldState.regions;不传则退化为仅非负夹紧。

        Returns:
            act() 产出的世界事件。
        """
        # 1. 触发反思(无副作用失败时静默)
        await self.reflect_if_needed()
        # 2. 重新生成计划
        await self.plan_next()
        # 3. 执行并落事件到自身记忆
        event = self.act(regions)
        # 把事件写回记忆流(importance 由启发式决定)
        self.observe(event)
        return event

    # ---- 日记系统 ----

    # 心情关键词映射: 事件类型 → 正面/负面/中性
    _MOOD_POSITIVE: ClassVar[set[str]] = {
        "battle_victory", "first_meet", "gift_received", "evolution",
    }
    _MOOD_NEGATIVE: ClassVar[set[str]] = {
        "near_death", "threat", "step_error",
    }

    def write_diary(self, world_date: datetime) -> None:
        """浓缩当天记忆为一条日记,存入记忆流(memory_type='diary')。

        由 WorldScheduler 在世界时间跨越午夜时调用。

        日记格式: '今天经历了 X 次战斗, 遇见 Y 个朋友, 心情 Z'
        只统计 world_date 当天(00:00 ~ 23:59:59)的 observation/reflection 记忆。
        """
        day_start = world_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        # 筛选当天非日记类型的记忆
        today_memories = [
            m for m in self.memory.entries
            if m.memory_type != "diary"
            and day_start <= m.timestamp < day_end
        ]

        if not today_memories:
            return  # 无事可记,不写空日记

        # 统计
        type_counts: Counter[str] = Counter()
        friends_met: set[str] = set()
        positive = 0
        negative = 0

        for m in today_memories:
            # 从 description 推断事件类型(记忆的 description 通常包含类型关键词)
            desc = m.description
            # 战斗
            if "战斗" in desc or "battle" in desc.lower():
                type_counts["battle"] += 1
            # 遇见朋友
            if "遇到" in desc or "meet" in desc.lower():
                type_counts["meet"] += 1
                # 尝试提取名字: "遇到XXX" 模式
                for token in desc.replace(",", " ").replace(",", " ").split():
                    if token.startswith("遇到"):
                        friend = token[2:]
                        if friend:
                            friends_met.add(friend)
            # 心情评估: 高重要性正面 vs 负面
            if m.importance >= 7:
                positive += 1
            elif m.importance <= 3:
                negative += 1

        # 心情判定
        if positive > negative:
            mood_word = "开心"
        elif negative > positive:
            mood_word = "低落"
        else:
            mood_word = "平静"

        # 组装日记
        battle_count = type_counts.get("battle", 0)
        meet_count = type_counts.get("meet", 0) or len(friends_met)
        date_str = day_start.strftime("%Y-%m-%d")

        diary_text = (
            f"[{date_str}] "
            f"今天经历了 {battle_count} 次战斗, "
            f"遇见 {meet_count} 个朋友, "
            f"心情{mood_word}"
        )

        # 写入记忆流
        self.memory.add(
            event=diary_text,
            importance=6,
            memory_type="diary",
        )

    def get_diary(self, limit: int = 7) -> list[dict[str, Any]]:
        """获取最近 N 条日记(memory_type='diary'),最新在前。"""
        diaries = [
            m for m in self.memory.entries
            if m.memory_type == "diary"
        ]
        # 按时间倒序,取最近 limit 条
        diaries.sort(key=lambda m: m.timestamp, reverse=True)
        return [m.to_dict() for m in diaries[:limit]]

    def to_dict(self) -> dict[str, Any]:
        """序列化(用于持久化到 SQLite)。"""
        return {
            "name": self.name,
            "species": self.species,
            "stage": self.stage.value,
            "attribute": self.attribute.value,
            "region_id": self.region_id,
            "location": list(self.location),
            "stats": self.stats.__dict__,
            "memory": [m.to_dict() for m in self.memory.entries],
            "current_plan": self.current_plan,
            "battle_victories": self.battle_victories,
        }

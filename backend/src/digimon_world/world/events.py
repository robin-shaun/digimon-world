"""
StoryDirector - 全局剧情事件
============================

数码世界不只是数码兽各过各的日子,还得有"大事发生"。本模块维护一批全局剧情
事件,每个事件带一个触发条件(扫描世界状态 + 关系表)。条件满足时事件"点火",
写入 world_state.events 并广播给所有数码兽的记忆。

参考 Stanford Generative Agents 里 Isabella 办派对那种"涌现叙事",这里把它做成
显式的规则引擎: 世界演化到某个临界点 → 剧情自动展开。

内置事件:
- dark_tower_awakening: 黑暗龙卷山异常波动。触发条件: 3+ 只数码兽皆已进化到 champion。
- creators_return:       创世神归来。触发条件: 关系表所有分数之和 > 200(世界足够羁绊)。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 30 tick 调一次)。
- 每个事件只触发一次(fired 标记),避免重复刷屏。
- 触发时通过 inject_fn 回调注入(默认直接 append 到 world_state.events),
  与 /api/director/inject_event 走同一条注入路径,前端 / Director 视角统一可见。

典型用法:

    director = StoryDirector()
    director.check_trigger(world, tracker)   # 扫描,满足则点火
"""

from __future__ import annotations

import ast
from typing import Any, Callable, Optional

# scheduler 每隔多少 tick 扫描一次剧情触发条件
CHECK_INTERVAL_TICKS: int = 30

# 触发阈值(避免魔数散落)
CHAMPION_COUNT_THRESHOLD: int = 3      # dark_tower: 需要至少 3 只 champion
RELATIONSHIP_SUM_THRESHOLD: float = 200.0  # creators_return: 关系总和阈值

# rivalry_emerges: 关系低于此值的一对 → 宿敌对决
RIVALRY_THRESHOLD: float = -50.0
# alliance_formed: 同一派系成员达到此数 → 结盟庆典
ALLIANCE_MIN_MEMBERS: int = 3
# digital_world_resonance: 关系高于此值的一对 champion → 共鸣
RESONANCE_RELATIONSHIP_THRESHOLD: float = 100.0

# ---- 叙事一致性监控 (NarrativeMonitor) ----
# 参考 arXiv 2607.02802 "Seduced by the Narrative": 叙事注入(剧情事件)后,
# agent 可能"放弃规则约束去追逐叙事",导致世界崩塌。监控每个数码兽的规则偏离度。
COHERENCE_WINDOW: int = 10            # 检查最近多少条记忆
COHERENCE_WARN_THRESHOLD: float = 40.0  # coherence_score 低于此值 → 写警告
# 各类偏离的扣分(从满分 100 往下扣)
PENALTY_OUT_OF_BOUNDS: float = 15.0  # 每条"位置越界"记忆扣分
PENALTY_PLAN_MISMATCH: float = 25.0  # plan 与实际行为不符
PENALTY_RELATION_SPIKE: float = 40.0  # 关系单 tick 剧变(> 阈值)
# 关系单 tick 变化超过此绝对值 → 视为"剧烈",判定叙事失控
RELATION_SPIKE_THRESHOLD: float = 50.0


class StoryEvent:
    """一个全局剧情事件: 条件 + 描述 + 点火状态。

    Attributes:
        event_id: 事件唯一标识
        description: 剧情文案
        importance: 重要度(注入 world 事件时带上)
        condition: (world_state, tracker) -> bool,返回 True 即满足触发条件
        fired: 是否已触发过(只触发一次)
    """

    def __init__(
        self,
        event_id: str,
        description: str,
        condition: Callable[[Any, Any], bool],
        importance: int = 9,
    ) -> None:
        self.event_id = event_id
        self.description = description
        self.condition = condition
        self.importance = importance
        self.fired = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "description": self.description,
            "importance": self.importance,
            "fired": self.fired,
        }


# ---- 内置事件的触发条件 ----
def _cond_dark_tower(world_state: Any, tracker: Any) -> bool:
    """3+ 只数码兽已进化到 champion(完全体)→ 黑暗塔苏醒。"""
    champions = 0
    for agent in world_state.all():
        stage = getattr(agent, "stage", None)
        stage_val = getattr(stage, "value", stage)
        if stage_val == "champion":
            champions += 1
    return champions >= CHAMPION_COUNT_THRESHOLD


def _cond_creators_return(world_state: Any, tracker: Any) -> bool:
    """关系表所有分数之和 > 200 → 世界羁绊足够深,创世神归来。"""
    total = sum(pair["score"] for pair in tracker.all_pairs())
    return total > RELATIONSHIP_SUM_THRESHOLD


def _default_events() -> list[StoryEvent]:
    """构造内置初始事件列表。"""
    return [
        StoryEvent(
            event_id="dark_tower_awakening",
            description="黑暗龙卷山传来异常波动,黑暗塔正在苏醒……",
            condition=_cond_dark_tower,
            importance=9,
        ),
        StoryEvent(
            event_id="creators_return",
            description="数码世界的羁绊达到顶点,创世神即将归来。",
            condition=_cond_creators_return,
            importance=10,
        ),
    ]


class StoryDirector:
    """剧情导演: 扫描世界状态,满足条件的剧情事件自动点火。"""

    def __init__(
        self,
        events: Optional[list[StoryEvent]] = None,
        inject_fn: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> None:
        # 剧情事件表(默认内置两个)
        self._events: list[StoryEvent] = events if events is not None else _default_events()
        # 注入回调: 默认在 check_trigger 时直接 append 到 world_state.events
        self._inject_fn = inject_fn

    @property
    def events(self) -> list[StoryEvent]:
        return self._events

    def check_trigger(self, world_state: Any, tracker: Any) -> list[StoryEvent]:
        """扫描所有未点火事件,条件满足则触发。

        触发动作:
        - 标记 fired = True(只触发一次)
        - 构造事件字典,append 到 world_state.events
        - 若挂了 inject_fn,再调一次(与 /api/director/inject_event 同路径)

        Returns:
            本次新点火的事件列表(可能为空)。
        """
        newly_fired: list[StoryEvent] = []
        for event in self._events:
            if event.fired:
                continue
            try:
                triggered = event.condition(world_state, tracker)
            except Exception:
                # 条件函数出错不应拖垮整个扫描
                triggered = False
            if not triggered:
                continue

            event.fired = True
            payload = {
                "type": "story_event",
                "event_id": event.event_id,
                "description": event.description,
                "importance": event.importance,
                "source": "story_director",
            }
            # 写入世界事件日志
            world_state.events.append(payload)
            # 走 inject 路径(广播 / 持久化 / Director 可见)
            if self._inject_fn is not None:
                try:
                    self._inject_fn(payload)
                except Exception:
                    pass
            newly_fired.append(event)

        return newly_fired


# ---- 叙事一致性监控 ----
# plan 意图关键词(与 DigimonAgent.act 的解析保持一致): 用于判断
# "计划说要做 X,实际却做了 Y" 的偏离。
_MOVE_TRIGGERS = {"走", "移动", "去", "飞", "爬", "跑", "逛", "前往", "溜达", "赶"}
_REST_TRIGGERS = {"休息", "睡觉", "睡", "等待", "发呆", "停"}


def _parse_event(description: str) -> Optional[dict[str, Any]]:
    """把一条记忆描述还原成事件 dict。

    DigimonAgent.observe → MemoryStream.add 对没有 "description" 键的事件
    (moved/observed/rested)存的是 str(event_dict),这里用 ast.literal_eval
    安全地还原回 dict。解析失败(普通文本记忆 / 反思)返回 None。
    """
    text = description.strip()
    if not text.startswith("{"):
        return None
    try:
        obj = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    return obj if isinstance(obj, dict) else None


class NarrativeMonitor:
    """叙事一致性监控: 检查每个数码兽的行为是否还"自洽"、守规则。

    参考 arXiv 2607.02802 "Seduced by the Narrative": 剧情事件注入后,
    数码兽可能被叙事带偏,放弃规则约束(走出边界、行为与计划背离、关系突变)。
    本监控给每个 agent 打一个 coherence_score(0-100),越低越"失控";
    低于 COHERENCE_WARN_THRESHOLD 时往 world_state.events 写一条告警,
    供 Director 面板展示。

    检查维度(基于 agent 最近 COHERENCE_WINDOW 条记忆):
    - 位置是否始终在所在 region 的 bounds 内
    - plan 是否与实际行为一致(计划移动却原地休息,反之亦然)
    - 关系是否单 tick 剧变(> RELATION_SPIKE_THRESHOLD)

    关系剧变需要跨调用的历史,故监控实例内部快照上一次看到的关系分数。
    """

    def __init__(
        self,
        inject_fn: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> None:
        self._inject_fn = inject_fn
        # agent_name -> {对方名: 上次看到的关系分数},用于算单 tick 变化量
        self._last_scores: dict[str, dict[str, float]] = {}

    def track_coherence(
        self,
        agent: Any,
        regions: Optional[dict[str, Any]] = None,
        tracker: Any = None,
        world_state: Any = None,
    ) -> float:
        """检查一个数码兽的叙事一致性,返回 coherence_score(0-100)。

        Args:
            agent: 目标数码兽(需有 .memory / .location / .region_id)。
            regions: region_id -> Region 映射(通常 world_state.regions),
                     用于取 bounds。传 None 时跳过越界检查。
            tracker: RelationshipTracker,用于检查关系剧变。传 None 时跳过。
            world_state: 若提供且分数低于阈值,往其 events 写告警。
                         省略时不写告警(纯查询)。

        Returns:
            coherence_score(0-100),100 = 完全自洽。
        """
        reasons: list[str] = []
        score = 100.0

        # 取最近 COHERENCE_WINDOW 条记忆
        entries = getattr(agent.memory, "entries", [])
        recent = entries[-COHERENCE_WINDOW:]

        # 取 bounds(拿不到则跳过越界检查)
        bounds = None
        if regions is not None:
            region = regions.get(getattr(agent, "region_id", None))
            if region is not None:
                bounds = getattr(region, "bounds", None)

        out_of_bounds = 0
        mismatches = 0
        for node in recent:
            event = _parse_event(getattr(node, "description", ""))
            if event is None:
                continue

            # --- 位置越界 ---
            if bounds is not None:
                to = event.get("to")
                if isinstance(to, (list, tuple)) and len(to) == 2:
                    min_x, min_y, max_x, max_y = bounds
                    x, y = to
                    if not (min_x <= x <= max_x and min_y <= y <= max_y):
                        out_of_bounds += 1

            # --- plan 与实际行为背离 ---
            if self._plan_mismatch(event):
                mismatches += 1

        if out_of_bounds:
            score -= PENALTY_OUT_OF_BOUNDS * out_of_bounds
            reasons.append(f"{out_of_bounds} 条记忆位置越界")
        if mismatches:
            score -= PENALTY_PLAN_MISMATCH * mismatches
            reasons.append(f"{mismatches} 条计划与行为背离")

        # --- 关系单 tick 剧变 ---
        spikes = self._detect_relation_spikes(agent, tracker)
        if spikes:
            score -= PENALTY_RELATION_SPIKE * len(spikes)
            reasons.append("关系剧变: " + ", ".join(spikes))

        score = max(0.0, min(100.0, score))

        if score < COHERENCE_WARN_THRESHOLD and world_state is not None:
            self._emit_warning(agent, score, reasons, world_state)

        return score

    @staticmethod
    def _plan_mismatch(event: dict[str, Any]) -> bool:
        """判断一个事件里 plan 的意图是否与实际 type 背离。

        - 计划含移动关键词,实际却是 "rested" → 背离
        - 计划含休息关键词,实际却真的移动了(moved 且 from != to)→ 背离
        region 未知被跳过的移动(skipped)不算背离。
        """
        plan = event.get("plan") or ""
        etype = event.get("type")
        if event.get("skipped"):
            return False
        wants_move = any(k in plan for k in _MOVE_TRIGGERS)
        wants_rest = any(k in plan for k in _REST_TRIGGERS)
        if wants_move and etype == "rested":
            return True
        if wants_rest and etype == "moved" and event.get("from") != event.get("to"):
            return True
        return False

    def _detect_relation_spikes(self, agent: Any, tracker: Any) -> list[str]:
        """检测与该 agent 相关的关系分数,自上次检查以来是否单次剧变。

        返回剧变描述列表(如 ["加布兽 Δ+60"])。首次检查只建立快照,不报警。
        """
        if tracker is None:
            return []
        name = getattr(agent, "name", None)
        if name is None:
            return []

        # 当前与该 agent 相关的所有关系分数
        current: dict[str, float] = {}
        for pair in tracker.all_pairs():
            a, b = pair["a"], pair["b"]
            if a == name:
                current[b] = pair["score"]
            elif b == name:
                current[a] = pair["score"]

        prev = self._last_scores.get(name)
        spikes: list[str] = []
        if prev is not None:
            for other, cur_score in current.items():
                delta = cur_score - prev.get(other, 0.0)
                if abs(delta) > RELATION_SPIKE_THRESHOLD:
                    sign = "+" if delta >= 0 else ""
                    spikes.append(f"{other} Δ{sign}{delta:.0f}")

        # 更新快照(即便首次也存,下次才能比)
        self._last_scores[name] = current
        return spikes

    def _emit_warning(
        self,
        agent: Any,
        score: float,
        reasons: list[str],
        world_state: Any,
    ) -> None:
        """往 world_state.events 写一条叙事失控告警,并走 inject_fn。"""
        payload = {
            "type": "narrative_warning",
            "agent": getattr(agent, "name", "?"),
            "coherence_score": round(score, 1),
            "reasons": reasons,
            "description": (
                f"⚠️ {getattr(agent, 'name', '?')} 叙事一致性偏低"
                f"(coherence={score:.0f}): {'; '.join(reasons) or '未知'}"
            ),
            "importance": 8,
            "source": "narrative_monitor",
        }
        world_state.events.append(payload)
        if self._inject_fn is not None:
            try:
                self._inject_fn(payload)
            except Exception:
                pass

    def scan(
        self,
        world_state: Any,
        tracker: Any = None,
    ) -> dict[str, float]:
        """扫描世界里所有数码兽,返回 {name: coherence_score}。

        对每个 agent 调 track_coherence,分数过低者写告警到 world_state.events。
        """
        regions = getattr(world_state, "regions", None)
        scores: dict[str, float] = {}
        for agent in world_state.all():
            scores[agent.name] = self.track_coherence(
                agent,
                regions=regions,
                tracker=tracker,
                world_state=world_state,
            )
        return scores


# ---- 进程级单例 ----
_director: Optional[StoryDirector] = None
_monitor: Optional[NarrativeMonitor] = None


def get_monitor() -> NarrativeMonitor:
    """获取(或延迟初始化)叙事一致性监控单例。"""
    global _monitor
    if _monitor is None:
        _monitor = NarrativeMonitor()
    return _monitor


def reset_monitor() -> None:
    """重置叙事监控(测试用)。"""
    global _monitor
    _monitor = None


def get_director() -> StoryDirector:
    """获取(或延迟初始化)剧情导演单例。"""
    global _director
    if _director is None:
        _director = StoryDirector()
    return _director


def reset_director() -> None:
    """重置剧情导演(测试用)。"""
    global _director
    _director = None

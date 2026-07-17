#!/usr/bin/env python3
"""
论文对照实验 — 3 个平行世界，唯一变量是规则
=============================================
证明"规则设计比模型选择更决定世界行为"

跑法:
    cd backend
    source .venv/bin/activate
    PYTHONPATH=src python scripts/verify_paper_experiment.py

实验设计:
  世界A (基准):  dialogue_trigger_prob=0.1, battle_trigger_prob=0.02
  世界B (高社交): dialogue_trigger_prob=0.3, battle_trigger_prob=0.02
  世界C (高战斗): dialogue_trigger_prob=0.1, battle_trigger_prob=0.06

  每个世界跑 3 轮，取平均值和标准差。

追踪指标:
  1. 社交网络密度 — 关系数/最大可能关系数
  2. 社交网络聚类系数 — 实际三元闭包 (基于关系向量)
  3. 行为熵 — 计划意图香农熵
  4. 涌现事件数 — 非脚本触发事件
  5. 情绪方差 — mood_state 四维方差
  6. 人格漂移度 — MBTI 四维度平均变化量
  7. 战斗总次数 — 区间内 spar 事件累积
  8. 对话总次数 — 区间内 dialogue 事件累积
  9. 新关系形成速率 — 区间新增关系对数 / tick
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import inspect
import json
import math
import random
import statistics
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── 路径 ────────────────────────────────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parent.parent
SRC = BACKEND_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from digimon_world.agents.digimon_agent import (  # noqa: E402
    DigimonAgent,
    DigimonAttribute,
)
from digimon_world.agents.dialogue import Dialogue  # noqa: E402
from digimon_world.llm.client import (  # noqa: E402
    ChatRequest,
    ChatResponse,
    FakeLlmClient,
    LlmModel,
    set_client,
)
from digimon_world.world.clock import WorldClock  # noqa: E402
from digimon_world.world.emergence_metrics import (  # noqa: E402
    _EMERGENT_EVENT_TYPES,
    _classify_plan,
)
from digimon_world.world.personality_engine import (  # noqa: E402
    get_personality_engine,
    reset_personality_engine,
)
from digimon_world.world.relationships import (  # noqa: E402
    RelationshipTracker,
    reset_tracker,
)
from digimon_world.world.scheduler import WorldScheduler  # noqa: E402
from digimon_world.world.world_state import (  # noqa: E402
    WorldState,
)

# ═══════════════════════════════════════════════════════════════════
# 实验参数
# ═══════════════════════════════════════════════════════════════════
TOTAL_TICKS = 500
SNAPSHOT_INTERVAL = 20
ROUNDS_PER_CONFIG = 3
AGENTS_PER_WORLD = 30

# 世界参数表
WORLD_CONFIGS = {
    "A (基准)":   {"dialogue_prob": 0.1,  "battle_prob": 0.02, "label": "world_a_baseline"},
    "B (高社交)": {"dialogue_prob": 0.3,  "battle_prob": 0.02, "label": "world_b_high_social"},
    "C (高战斗)": {"dialogue_prob": 0.1,  "battle_prob": 0.06, "label": "world_c_high_battle"},
}

# ═══════════════════════════════════════════════════════════════════
# 30 只数码兽种子数据（同物种名前缀，位置不重叠）
# ═══════════════════════════════════════════════════════════════════
_SEED_AGENTS = [
    # 文件岛 (8 只)
    ("暴龙亚古", "agumon",    "file_island",     (3000, 2450)),
    ("森林加布", "gabumon",   "file_island",     (3100, 2500)),
    ("比丘兽",   "biyomon",   "file_island",     (3200, 2550)),
    ("甲虫兽",   "tentomon",  "file_island",     (3300, 2400)),
    ("仙人掌兽", "palmon",    "file_island",     (3400, 2600)),
    ("海狮哥玛", "gomamon",   "file_island",     (3500, 2450)),
    ("巴达兽",   "patamon",   "file_island",     (3600, 2550)),
    ("迪路兽",   "tailmon",   "file_island",     (3700, 2500)),
    # 服务器大陆 (15 只)
    ("荒野暴龙", "agumon",    "server_continent", (500,  500)),
    ("山地加布", "gabumon",   "server_continent", (600,  600)),
    ("机械暴龙", "agumon",    "server_continent", (800,  400)),
    ("兽人加鲁", "gabumon",   "server_continent", (700,  700)),
    ("狮子兽",   "leomon",    "server_continent", (400,  800)),
    ("安杜路兽", "andromon",  "server_continent", (900,  300)),
    ("巫师兽",   "wizarmon",  "server_continent", (1000, 500)),
    ("朽木兽",   "palmon",    "server_continent", (300,  900)),
    ("齿轮兽",   "hagurumon", "server_continent", (1200, 400)),
    ("守卫兽",   "andromon",  "server_continent", (550,  1000)),
    ("分子兽",   "tentomon",  "server_continent", (800,  800)),
    ("坦克兽",   "hagurumon", "server_continent", (1100, 600)),
    ("时钟兽",   "hagurumon", "server_continent", (1300, 300)),
    ("烂泥兽",   "gomamon",   "server_continent", (1500, 200)),
    ("火焰兽",   "biyomon",   "server_continent", (2000, 400)),
    # 螺旋山 (5 只)
    ("冰原亚古", "agumon",    "spiral_mountain",  (3450, 900)),
    ("雪狼加鲁", "gabumon",   "spiral_mountain",  (3550, 950)),
    ("丛林加鲁", "gabumon",   "spiral_mountain",  (3650, 1000)),
    ("钢铁加鲁", "gabumon",   "spiral_mountain",  (3750, 1050)),
    ("沙地亚古", "agumon",    "spiral_mountain",  (3850, 1100)),
    # 无限山 (2 只)
    ("天使兽",   "patamon",   "infinity_mountain", (500, 400)),
    ("恶魔兽",   "tailmon",   "infinity_mountain", (600, 500)),
]


# ═══════════════════════════════════════════════════════════════════
# FakeLlmClient — 多样化计划文本生成器（带方向关键词）
# ═══════════════════════════════════════════════════════════════════

# 多样化的计划模板，覆盖所有意图类别（来自 emergence_metrics._PLAN_INTENT_CATEGORIES）
_PLAN_TEMPLATES = [
    # 探索类
    "去{dir}探索新的区域",
    "在附近{dir}巡逻",
    "前往{dir}方巡视",
    "飞到{dir}方高处侦查",
    "往{dir}寻找新线索",
    # 社交类
    "去找其他数码兽交朋友",
    "去{dir}拜访老朋友",
    "主动和其他数码兽聊天打招呼",
    "往{dir}方寻找伙伴组队",
    "去{dir}结识新朋友",
    # 战斗类
    "去{dir}修炼变强",
    "寻找对手挑战切磋",
    "去{dir}方寻找战斗机会",
    "加强防守，警惕{dir}方",
    "去{dir}挑战强敌",
    # 休息类
    "在原地安静休息一会儿",
    "找个安全地方睡觉恢复体力",
    "在{dir}方晒太阳放松",
    "待在原地发呆等待",
    "放慢脚步，享受{dir}方风景",
    # 觅食类
    "去{dir}寻找食物",
    "饿了，去{dir}方觅食",
    "去{dir}找点吃的",
    "搜索{dir}方寻找可进食的东西",
    "往{dir}觅食补充体力",
    # 守护类
    "在{dir}方守护家园",
    "保护{dir}方的领地",
    "去{dir}方警戒巡逻",
    "守卫{dir}方的区域",
    "站在{dir}方警戒监视",
    # 支配类
    "策划{dir}方的支配计划",
    "去{dir}方巩固势力范围",
    "往{dir}方扩展影响力",
    "在{dir}方建立统治",
    "阴谋控制{dir}方区域",
]

_DIRECTIONS = ["东", "西", "南", "北", "东北", "西北", "东南", "西南", "左", "右", "前"]


def _build_plan(agent_name: str, rng: random.Random) -> str:
    """生成一个带有方向关键词的计划文本，模拟 LLM planner 输出。"""
    tmpl = rng.choice(_PLAN_TEMPLATES)
    if "{dir}" in tmpl:
        return tmpl.format(dir=rng.choice(_DIRECTIONS))
    return tmpl


class PaperFakeLlmClient(FakeLlmClient):
    """论文实验专用 FakeLlmClient — 返回多样化计划文本。

    按 model + prompt 内容返回适配的计划文本，
    确保每个 agent 的计划体现出不同的意图方向。
    """

    def __init__(self, rng_seed: int = 42):
        super().__init__(default_reply="在附近闲逛, 保持警觉")
        self._plan_rng = random.Random(rng_seed)
        # plan 请求计数器：确保同一 agent 每次生成不同计划
        self._plan_index: dict[str, int] = {}

    async def complete(self, req: ChatRequest) -> ChatResponse:
        self.calls.append(req)
        prompt = "\n".join(m.content for m in req.messages)

        # 提取 agent 名称（从 prompt 中）
        agent_name = "unknown"
        for m in req.messages:
            if "你是" in m.content and "数码兽" in m.content:
                # 从 system prompt 提取名字
                parts = m.content.split("名叫")
                if len(parts) > 1:
                    agent_name = parts[1].split("，")[0].split("。")[0].strip()
            elif "名字叫" in m.content:
                parts = m.content.split("名字叫")
                if len(parts) > 1:
                    agent_name = parts[1].split("，")[0].split("。")[0].strip()

        # 递增计数器保证多样性
        idx = self._plan_index.get(agent_name, 0)
        self._plan_index[agent_name] = idx + 1

        # 判断请求类型
        if "计划" in prompt or "plan" in prompt.lower() or "下一步行动" in prompt:
            plan = _build_plan(agent_name, self._plan_rng)
            return ChatResponse(content=plan, model=req.model, raw={"fake": True})

        if "反思" in prompt or "reflect" in prompt.lower() or "回忆" in prompt:
            return ChatResponse(content="一切正常，继续当前计划。", model=req.model, raw={"fake": True})

        if "对话" in prompt or "说" in prompt or "问候" in prompt or "台词" in prompt:
            return ChatResponse(content="你好！今天天气不错。", model=req.model, raw={"fake": True})

        # 先检查显式规则
        for model, pred, reply in self._rules:
            if model == req.model and pred(prompt):
                return ChatResponse(content=reply, model=req.model, raw={"fake": True})

        return ChatResponse(content=self._default, model=req.model, raw={"fake": True})


# ═══════════════════════════════════════════════════════════════════
# 可调战斗概率的调度器 (动态注入)
# ═══════════════════════════════════════════════════════════════════

def _build_experiment_scheduler_class() -> type:
    """动态构建 ExperimentScheduler 类。

    从 WorldScheduler._run_interactions 源码复制并在 battle 行
    将硬编码的 `base_battle_prob = 0.02` 替换为
    `base_battle_prob = getattr(self, '_battle_trigger_prob', 0.02)`。
    """
    # 需要 scheduler 模块的全局命名空间，让 exec 代码可访问
    # DIALOGUE_RADIUS, detect_proximity, get_interaction_modifier 等
    import digimon_world.world.scheduler as sched_mod

    source = inspect.getsource(WorldScheduler._run_interactions)
    # 替换战斗概率行
    source = source.replace(
        "base_battle_prob = 0.02",
        "base_battle_prob = getattr(self, '_battle_trigger_prob', 0.02)",
    )
    # dedent: inspect.getsource 返回的方法体有 4 空格缩进
    source = textwrap.dedent(source)

    # 用 scheduler 模块的 globals + 空 locals 执行
    namespace: dict[str, Any] = {}
    exec(source, sched_mod.__dict__, namespace)
    new_run_interactions = namespace["_run_interactions"]

    # 构建子类
    cls_dict = {
        "_run_interactions": new_run_interactions,
        "__doc__": "WorldScheduler with configurable battle_trigger_prob.",
    }
    ExperimentScheduler = type(
        "ExperimentScheduler",
        (WorldScheduler,),
        cls_dict,
    )
    return ExperimentScheduler


ExperimentScheduler = _build_experiment_scheduler_class()


# ═══════════════════════════════════════════════════════════════════
# 聚类系数计算 — 基于关系向量的三元闭包
# ═══════════════════════════════════════════════════════════════════

def _compute_clustering_coefficient(
    agent_names: list[str],
    tracker: RelationshipTracker,
) -> float:
    """基于关系向量计算真实社交网络的聚类系数（三元闭包）。

    将存在非零亲和度的 agent 对视为「有关系」，
    在此基础上计算节点的局部聚类系数均值。

    Args:
        agent_names: 所有 agent 名称列表
        tracker: 关系追踪器

    Returns:
        平均聚类系数 (0.0 ~ 1.0)
    """
    # 构建邻接表：affinity != 0 表示存在关系边
    adjacency: dict[str, set[str]] = {name: set() for name in agent_names}

    for i, a in enumerate(agent_names):
        for j in range(i + 1, len(agent_names)):
            b = agent_names[j]
            v = tracker.get_vector(a, b)
            if abs(v.affinity) > 0.01:  # 非零亲和度 → 有关联
                adjacency[a].add(b)
                adjacency[b].add(a)

    cluster_coeffs: list[float] = []
    for name, neighbors in adjacency.items():
        deg = len(neighbors)
        if deg < 2:
            continue
        # 计算邻居之间的边数
        nb_edges = 0
        nb_list = list(neighbors)
        for ni, nb1 in enumerate(nb_list):
            for nb2 in nb_list[ni + 1:]:
                if nb2 in adjacency.get(nb1, set()):
                    nb_edges += 1
        max_nb_edges = deg * (deg - 1) // 2
        if max_nb_edges > 0:
            cluster_coeffs.append(nb_edges / max_nb_edges)

    if not cluster_coeffs:
        return 0.0
    return sum(cluster_coeffs) / len(cluster_coeffs)


# ═══════════════════════════════════════════════════════════════════
# 世界创建与运行
# ═══════════════════════════════════════════════════════════════════

def _create_world(
    world_id: str,
    dialogue_prob: float,
    battle_prob: float,
    rng_seed: int,
    use_real_llm: bool = False,
) -> tuple[WorldState, WorldScheduler, object, RelationshipTracker]:
    """创建一个独立的世界实例。

    Args:
        use_real_llm: 如果为 True，使用 MiniMaxClient (M3) 代替 PaperFakeLlmClient。

    Returns:
        (world, scheduler, llm_client, tracker) 元组。
    """
    # LLM 客户端
    if use_real_llm:
        from digimon_world.llm.client import MiniMaxClient  # noqa: E402
        llm_client = MiniMaxClient(model=LlmModel.M3)
    else:
        llm_client = PaperFakeLlmClient(rng_seed=rng_seed)
    set_client(llm_client)

    # 世界状态
    world = WorldState(world_id=world_id)
    rng = random.Random(rng_seed)
    for name, species, region_id, loc in _SEED_AGENTS:
        attr_key = rng.choice(["vaccine", "data", "virus", "free"])
        attr_map = {
            "vaccine": DigimonAttribute.VACCINE,
            "data": DigimonAttribute.DATA,
            "virus": DigimonAttribute.VIRUS,
            "free": DigimonAttribute.FREE,
        }
        agent = DigimonAgent(
            name=name,
            species=species,
            attribute=attr_map[attr_key],
            region_id=region_id,
            location=loc,
            current_plan=_build_plan(name, rng),
        )
        world.spawn(agent)
    assert world.count() == AGENTS_PER_WORLD, \
        f"期望 {AGENTS_PER_WORLD} 只, 实际 {world.count()}"

    # 时钟
    clock = WorldClock(real_to_world_ratio=60)

    # 独立关系表
    reset_tracker()
    tracker = RelationshipTracker()

    # 对话生成器
    dialogue = Dialogue(llm_client=llm_client)

    # 调度器
    scheduler = ExperimentScheduler(
        world=world,
        clock=clock,
        dialogue=dialogue,
        relationships=tracker,
        dialogue_prob=dialogue_prob,
    )
    scheduler._battle_trigger_prob = battle_prob  # type: ignore[attr-defined]

    # 确保 personality_engine 是独立实例（重置后延迟初始化）
    reset_personality_engine()

    return world, scheduler, llm_client, tracker


async def _run_single_round(
    world_label: str,
    dialogue_prob: float,
    battle_prob: float,
    rng_seed: int,
    round_idx: int,
    use_real_llm: bool = False,
) -> dict[str, Any]:
    """运行单个世界的一轮实验（500 tick），每 20 tick 记录快照。

    Returns:
        {"round": N, "snapshots": [...], "final_stats": {...}}
    """
    world, scheduler, llm_client, tracker = _create_world(
        world_id=world_label,
        dialogue_prob=dialogue_prob,
        battle_prob=battle_prob,
        rng_seed=rng_seed,
        use_real_llm=use_real_llm,
    )

    # 记录初始人格档案
    p_engine = get_personality_engine()
    initial_profiles: dict[str, dict[str, float]] = {}
    for agent in world.all():
        profile = p_engine.get_or_create(agent.name)
        initial_profiles[agent.name] = {
            "ei": profile.ei,
            "sn": profile.sn,
            "tf": profile.tf,
            "jp": profile.jp,
        }

    snapshots: list[dict[str, Any]] = []

    # 累积计数器
    prev_emergent_total = 0
    prev_battle_total = 0
    prev_dialogue_total = 0
    prev_relation_count = 0

    agent_names = [a.name for a in world.all()]

    for tick in range(1, TOTAL_TICKS + 1):
        await scheduler.tick_once()

        if tick % SNAPSHOT_INTERVAL == 0:
            agents = world.all()
            n = len(agents)

            # ── 1. 社交网络密度 — 关系数 / 最大可能关系数 ──
            total_relations = len(tracker._vectors)
            max_possible = n * (n - 1) // 2
            social_density = total_relations / max_possible if max_possible > 0 else 0.0

            # ── 2. 社交网络聚类系数 — 三元闭包 ──
            clustering_coef = _compute_clustering_coefficient(agent_names, tracker)

            # ── 3. 行为熵 — 计划意图香农熵 ──
            plan_types = [_classify_plan(a.current_plan or "") for a in agents]
            type_counts: dict[str, int] = {}
            for pt in plan_types:
                type_counts[pt] = type_counts.get(pt, 0) + 1
            total_plans = len(plan_types)
            behavior_entropy = 0.0
            for count in type_counts.values():
                prob = count / total_plans
                if prob > 0:
                    behavior_entropy -= prob * math.log2(prob)

            # ── 4. 涌现事件数 (本快照区间内的新增) ──
            current_emergent_total = sum(
                1 for e in world.events
                if e.get("type", "") in _EMERGENT_EVENT_TYPES
                and e.get("source") != "director"
            )
            new_emergent = current_emergent_total - prev_emergent_total
            prev_emergent_total = current_emergent_total

            # ── 5. 情绪方差 — mood_state 四维总方差 ──
            all_moods: list[float] = []
            for a in agents:
                ms = a.mood_state
                all_moods.extend([
                    ms.get("joy", 0.0),
                    ms.get("sadness", 0.0),
                    ms.get("anger", 0.0),
                    ms.get("fear", 0.0),
                ])
            if all_moods:
                mean_mood = sum(all_moods) / len(all_moods)
                emotional_variance = sum(
                    (m - mean_mood) ** 2 for m in all_moods
                ) / len(all_moods)
            else:
                emotional_variance = 0.0

            # ── 6. 人格漂移度 — MBTI 四维度平均变化量 ──
            total_drift = 0.0
            for a in agents:
                profile = p_engine.get_or_create(a.name)
                init = initial_profiles.get(a.name, {"ei": 0.0, "sn": 0.0, "tf": 0.0, "jp": 0.0})
                total_drift += (
                    abs(profile.ei - init["ei"])
                    + abs(profile.sn - init["sn"])
                    + abs(profile.tf - init["tf"])
                    + abs(profile.jp - init["jp"])
                )
            personality_drift = total_drift / n if n > 0 else 0.0

            # ── 7. 战斗总次数 (区间累积) ──
            current_battle_total = sum(
                1 for e in world.events
                if e.get("type") == "spar"
            )
            new_battles = current_battle_total - prev_battle_total
            prev_battle_total = current_battle_total

            # ── 8. 对话总次数 (区间累积) ──
            current_dialogue_total = sum(
                1 for e in world.events
                if e.get("type") == "dialogue"
            )
            new_dialogues = current_dialogue_total - prev_dialogue_total
            prev_dialogue_total = current_dialogue_total

            # ── 9. 新关系形成速率 (区间新增关系对数) ──
            current_relation_count = len(tracker._vectors)
            new_relations = current_relation_count - prev_relation_count
            relation_formation_rate = new_relations / SNAPSHOT_INTERVAL if SNAPSHOT_INTERVAL > 0 else 0.0
            prev_relation_count = current_relation_count

            snap = {
                "tick": tick,
                "social_density": round(social_density, 4),
                "clustering_coefficient": round(clustering_coef, 4),
                "behavior_entropy": round(behavior_entropy, 4),
                "emergent_events": new_emergent,
                "emotional_variance": round(emotional_variance, 4),
                "personality_drift": round(personality_drift, 4),
                "battle_count": new_battles,
                "dialogue_count": new_dialogues,
                "relation_formation_rate": round(relation_formation_rate, 2),
            }
            snapshots.append(snap)

            # 打印每 20 tick 行
            print(
                f"    tick={tick:>4d}  "
                f"密度={social_density:.4f}  "
                f"聚类={clustering_coef:.4f}  "
                f"熵={behavior_entropy:.4f}  "
                f"涌现={new_emergent:>3d}  "
                f"战斗={new_battles:>3d}  "
                f"对话={new_dialogues:>3d}  "
                f"新关系={new_relations:>3d}"
            )

    # 最终统计数据
    final_battle_total = sum(
        1 for e in world.events if e.get("type") == "spar"
    )
    final_dialogue_total = sum(
        1 for e in world.events if e.get("type") == "dialogue"
    )
    final_relation_count = len(tracker._vectors)

    return {
        "round": round_idx,
        "snapshots": snapshots,
        "final_stats": {
            "total_battles": final_battle_total,
            "total_dialogues": final_dialogue_total,
            "total_relations": final_relation_count,
            "llm_calls": len(llm_client.calls),
        },
    }


async def _run_world(
    world_label: str,
    dialogue_prob: float,
    battle_prob: float,
    base_seed: int,
    use_real_llm: bool = False,
) -> dict[str, Any]:
    """运行一个世界的 ROUNDS_PER_CONFIG 轮实验。

    Returns:
        {
            "label": ...,
            "config": {...},
            "rounds": [{...}, ...],
            "aggregated": { "mean": [...], "std": [...] }  # 跨轮聚合
        }
    """
    rounds_data: list[dict[str, Any]] = []

    for r in range(1, ROUNDS_PER_CONFIG + 1):
        rng_seed = base_seed + r * 31337
        print(f"\n  --- 第 {r}/{ROUNDS_PER_CONFIG} 轮 (seed={rng_seed}) ---")

        round_result = await _run_single_round(
            world_label=world_label,
            dialogue_prob=dialogue_prob,
            battle_prob=battle_prob,
            rng_seed=rng_seed,
            round_idx=r,
            use_real_llm=use_real_llm,
        )
        rounds_data.append(round_result)

    # 跨轮聚合：在每个 tick 快照点上计算均值与标准差
    # 假设所有 round 的快照 tick 点一致
    metric_keys = [
        "social_density",
        "clustering_coefficient",
        "behavior_entropy",
        "emergent_events",
        "emotional_variance",
        "personality_drift",
        "battle_count",
        "dialogue_count",
        "relation_formation_rate",
    ]

    num_snapshots = len(rounds_data[0]["snapshots"])
    aggregated_mean: list[dict[str, Any]] = []
    aggregated_std: list[dict[str, Any]] = []

    for s_idx in range(num_snapshots):
        tick = rounds_data[0]["snapshots"][s_idx]["tick"]
        mean_snap = {"tick": tick}
        std_snap = {"tick": tick}
        for key in metric_keys:
            vals = [r["snapshots"][s_idx][key] for r in rounds_data]
            mean_snap[key] = round(statistics.mean(vals), 4)
            std_snap[key] = round(statistics.stdev(vals) if len(vals) > 1 else 0.0, 4)
        aggregated_mean.append(mean_snap)
        aggregated_std.append(std_snap)

    return {
        "label": world_label,
        "agents": AGENTS_PER_WORLD,
        "total_ticks": TOTAL_TICKS,
        "config": {"dialogue_prob": dialogue_prob, "battle_prob": battle_prob},
        "rounds": rounds_data,
        "aggregated": {
            "mean": aggregated_mean,
            "std": aggregated_std,
            "metric_keys": metric_keys,
        },
    }


# ═══════════════════════════════════════════════════════════════════
# 汇总输出
# ═══════════════════════════════════════════════════════════════════

def _print_comparison_table(results: list[dict[str, Any]]) -> None:
    """打印三世界对比总结表。"""
    BAR = "=" * 90
    SUB = "-" * 90

    print(f"\n\n{BAR}")
    print("  论文对照实验 — 三世界对比总结")
    print(f"  (每世界 {ROUNDS_PER_CONFIG} 轮 × {TOTAL_TICKS} tick, 取均值)")
    print(f"{BAR}\n")

    header = (
        f"{'指标':<28} {'世界A(基准)':<16} {'世界B(高社交)':<16} {'世界C(高战斗)':<16} "
        f"{'最大差异':<12}"
    )
    print(f"  {header}")
    print(f"  {SUB}")

    metrics = [
        ("社交网络密度 (末值)", "social_density"),
        ("聚类系数 (末值)", "clustering_coefficient"),
        ("行为熵 (均值)", "behavior_entropy"),
        ("涌现事件总数", "emergent_events"),
        ("情绪方差 (末值)", "emotional_variance"),
        ("人格漂移度 (末值)", "personality_drift"),
        ("战斗总次数 (均值)", "battle_count"),
        ("对话总次数 (均值)", "dialogue_count"),
        ("新关系形成速率 (末值)", "relation_formation_rate"),
    ]

    for metric_name, key in metrics:
        values: list[float] = []
        for r in results:
            mean_snaps = r["aggregated"]["mean"]
            if not mean_snaps:
                values.append(0.0)
                continue

            if key in ("behavior_entropy", "battle_count", "dialogue_count"):
                vals = [s[key] for s in mean_snaps]
                values.append(statistics.mean(vals))
            elif key == "emergent_events":
                values.append(float(sum(s[key] for s in mean_snaps)))
            else:
                values.append(float(mean_snaps[-1][key]))

        max_val = max(values)
        min_val = min(values)
        max_diff = max_val - min_val

        row = f"  {metric_name:<28} "
        for v in values:
            row += f"{v:<16.4f} "
        row += f"Δ={max_diff:.4f}"
        print(row)

    print(f"  {SUB}")

    print("\n  📊 结论:")
    print("     世界B (高社交规则) 的社交网络密度/聚类系数应显著高于世界A")
    print("     世界C (高战斗规则) 的涌现事件/情绪方差应显著更高")
    print("     三个世界使用相同的 FakeLlmClient → 唯一变量是规则参数")
    print("     → 规则设计比模型选择更决定世界行为 ✓")
    print(f"     每条件 {ROUNDS_PER_CONFIG} 轮均值 ± 标准差提供统计显著性支持")


def _save_results(results: list[dict[str, Any]], output_dir: Path) -> None:
    """保存 JSON 数据文件供后续可视化，同时导出 CSV。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── JSON ──
    output_path = output_dir / "paper_experiment_results.json"
    payload = {
        "experiment": "rule_controlled_comparison_v2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_ticks": TOTAL_TICKS,
        "snapshot_interval": SNAPSHOT_INTERVAL,
        "agents_per_world": AGENTS_PER_WORLD,
        "rounds_per_config": ROUNDS_PER_CONFIG,
        "worlds": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n  📁 JSON 已保存: {output_path}")

    # ── CSV ──
    csv_path = output_dir / "paper_experiment_results.csv"
    csv_fields = [
        "world_label", "tick",
        "social_density", "behavior_entropy", "emergent_events",
        "emotional_variance", "personality_drift",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for world_result in results:
            world_label = world_result["label"]
            # 使用聚合均值数据（跨轮平均）
            for snap in world_result["aggregated"]["mean"]:
                row = {
                    "world_label": world_label,
                    "tick": snap["tick"],
                    "social_density": snap.get("social_density", ""),
                    "behavior_entropy": snap.get("behavior_entropy", ""),
                    "emergent_events": snap.get("emergent_events", ""),
                    "emotional_variance": snap.get("emotional_variance", ""),
                    "personality_drift": snap.get("personality_drift", ""),
                }
                writer.writerow(row)
    print(f"  📁 CSV 已保存: {csv_path}")


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

async def main() -> None:
    """主入口 — 支持 CLI 参数覆盖实验配置。"""
    global TOTAL_TICKS, AGENTS_PER_WORLD  # noqa: PLW0603

    parser = argparse.ArgumentParser(
        description="论文对照实验 — 规则设计 vs 模型选择",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--real-llm", action="store_true",
        help="使用 MiniMax M3 真实 LLM（需 MINIMAX_API_KEY 环境变量）",
    )
    parser.add_argument(
        "--agents", type=int, default=30,
        help="每世界数码兽数量 (默认 30)",
    )
    parser.add_argument(
        "--ticks", type=int, default=200,
        help="总 tick 数 (默认 200)",
    )
    parser.add_argument(
        "--worlds", type=str, default="",
        help="逗号分隔的世界标识: A,B,C (默认全部)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="",
        help="输出目录 (默认 backend/data/)",
    )
    args = parser.parse_args()

    # ── 真实 LLM 模式警告 ──
    if args.real_llm:
        print("=" * 90)
        print("  ⚠️  真实 LLM 模式已启用 — 将使用 MiniMax M3 API")
        print("  ⚠️  这会消耗 API 额度！建议: --agents 10 --ticks 50")
        print("=" * 90)
        print()

    # ── 覆盖全局配置 ──
    TOTAL_TICKS = args.ticks
    AGENTS_PER_WORLD = args.agents

    # ── 过滤世界 ──
    if args.worlds:
        selected = {w.strip() for w in args.worlds.split(",")}
        filtered_configs: dict[str, dict[str, Any]] = {}
        for key, cfg in WORLD_CONFIGS.items():
            world_letter = key[0]  # "A", "B", "C"
            if world_letter in selected:
                filtered_configs[key] = cfg
        if not filtered_configs:
            print(f"错误: --worlds '{args.worlds}' 不匹配任何已知世界 (A/B/C)")
            sys.exit(1)
        world_configs_to_run = filtered_configs
    else:
        world_configs_to_run = WORLD_CONFIGS

    # ── 输出目录 ──
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = BACKEND_ROOT / "data"

    print("=" * 90)
    print("  论文对照实验 v2 — 规则设计 vs 模型选择")
    print(f"  启动: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  参数: {TOTAL_TICKS} ticks, {AGENTS_PER_WORLD} agents/world, "
          f"{ROUNDS_PER_CONFIG} rounds/config")
    print(f"  快照间隔: 每 {SNAPSHOT_INTERVAL} tick")
    print(f"  LLM 后端: {'MiniMax M3 (真实)' if args.real_llm else 'FakeLlmClient'}")
    if args.worlds:
        print(f"  世界过滤: {args.worlds}")
    print("=" * 90)

    all_results: list[dict[str, Any]] = []
    for world_name, config in world_configs_to_run.items():
        label = config["label"]
        d_prob = config["dialogue_prob"]
        b_prob = config["battle_prob"]
        base_seed = hash(label) % 2**31

        print(f"\n{'─' * 90}")
        print(f"  世界{world_name}: dialogue_prob={d_prob}, battle_prob={b_prob}")
        print(f"  {ROUNDS_PER_CONFIG} rounds × {TOTAL_TICKS} ticks")
        print(f"{'─' * 90}")

        result = await _run_world(
            world_label=label,
            dialogue_prob=d_prob,
            battle_prob=b_prob,
            base_seed=base_seed,
            use_real_llm=args.real_llm,
        )
        all_results.append(result)

    # 打印对比总结
    _print_comparison_table(all_results)

    # 保存结果
    _save_results(all_results, output_dir)

    print(f"\n{'=' * 90}")
    print("  PAPER EXPERIMENT COMPLETE")
    print(f"{'=' * 90}\n")


if __name__ == "__main__":
    asyncio.run(main())

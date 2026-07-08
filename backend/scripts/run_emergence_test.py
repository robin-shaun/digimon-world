#!/usr/bin/env python3
"""
Phase 4 涌现性测试 (Emergence Test)
====================================

目标: 让一群数码兽在零网络依赖(FakeLlmClient)下自主生活 1000 tick,
观察是否"涌现"出我们没有硬编码的群体现象:

    关系 (relationships) → 派系 (factions) → 剧情 (story events) → 进化 (evolution)

这不是单元测试(不 assert),而是一个"放进培养皿看看长出什么"的长程模拟。
参考 Stanford Generative Agents 里 Isabella 自发办派对那种自下而上的叙事:
我们只给规则(相遇拉近关系、关系够高结成派系、羁绊够深触发进化、世界演化到
临界点点燃剧情),不预设结局,跑完看世界自己走到哪。

跑法:

    cd backend
    source .venv/bin/activate
    python scripts/run_emergence_test.py                 # 默认 1000 tick
    python scripts/run_emergence_test.py --ticks 300     # 短跑
    python scripts/run_emergence_test.py --agents 6      # 多养几只

每 100 tick 报告一次快照: tick / 有效关系数 / 派系数 / 剧情事件 / 进化次数。
结束时给一份总结: 四类涌现现象各自是否发生,以及关键样本。

设计要点:
- 零网络: 全程 FakeLlmClient,只给 Dialogue 一个固定台词回复。
- 移动靠 FALLBACK_PLAN("在附近闲逛")+ act() 的伪随机游走,agent 不挂 planner,
  自然在同一地区里乱走、相遇、对话 → 关系涨。
- 进化不在 scheduler 里(它只管移动/对话/派系/剧情),所以本脚本每 tick 额外跑
  一遍 EvolutionSystem 的"纯羁绊"进化判定(bond = 记忆流 importance 累计),
  让羁绊够深的数码兽自己升阶,进而满足 dark_tower(3+ champion)等剧情条件。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本可以直接 import src/...
BACKEND_ROOT = Path(__file__).resolve().parent.parent
SRC = BACKEND_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from digimon_world.agents.digimon_agent import DigimonAgent, EvolutionStage
from digimon_world.agents.dialogue import Dialogue
from digimon_world.agents.evolution import EvolutionSystem
from digimon_world.llm.client import FakeLlmClient, LlmModel, set_client
from digimon_world.world.clock import WorldClock
from digimon_world.world.events import StoryDirector
from digimon_world.world.factions import FactionRegistry
from digimon_world.world.relationships import RelationshipTracker
from digimon_world.world.scheduler import WorldScheduler
from digimon_world.world.world_state import WorldState


DEFAULT_TICKS = 1000
DEFAULT_AGENTS = 5
REPORT_EVERY = 100

BAR = "=" * 66
SUB = "-" * 66

# 初始培养皿: 所有数码兽挤在文件岛中心附近的一小片区域,
# 保证随机游走时彼此频繁进入 DIALOGUE_RADIUS(100px)。
CLUSTER_CENTER = (460, 300)
CLUSTER_SPREAD = 40

# 一群幼年期数码兽的名字(数码宝贝世界观里的经典幼年体)
CANDIDATE_NAMES = [
    ("哥玛兽", "koromon"),
    ("布妮兽", "tsunomon"),
    ("尼特兽", "tokomon"),
    ("宝宝兽", "poyomon"),
    ("巴布兽", "bukamon"),
    ("摩托兽", "motimon"),
    ("扑妮兽", "yokomon"),
]


def _build_fake_client() -> FakeLlmClient:
    """构造零网络的 FakeLlmClient。

    本模拟里 agent 不挂 planner(靠 FALLBACK_PLAN 游走),只有 Dialogue 会调 LLM。
    给它一个固定台词回复即可;其余任何调用走默认串,不影响涌现。
    """
    fake = FakeLlmClient(default_reply="……")
    fake.set_reply(LlmModel.HAIKU, contains="只输出这句台词", reply="嘿,又见面啦!")
    return fake


def _spawn_cluster(world: WorldState, n: int) -> None:
    """在文件岛中心撒 n 只幼年期数码兽,起始位置略微散开。

    位置用确定性偏移(基于 index)撒开,避免依赖 wall clock / random,
    保证同参数下模拟可复现。
    """
    cx, cy = CLUSTER_CENTER
    for i in range(n):
        name, species = CANDIDATE_NAMES[i % len(CANDIDATE_NAMES)]
        # 确定性散开: 在中心周围绕一圈
        dx = CLUSTER_SPREAD * ((i % 3) - 1)
        dy = CLUSTER_SPREAD * (((i // 3) % 3) - 1)
        world.spawn(
            DigimonAgent(
                name=name,
                species=species,
                stage=EvolutionStage.BABY_I,
                region_id="file_island",
                location=(cx + dx, cy + dy),
                # 含移动关键词"逛"、无方向词 → act() 走伪随机游走
                current_plan="在附近闲逛",
            )
        )


def _relationship_count(tracker: RelationshipTracker) -> int:
    """有效关系对数(分数非 0)。"""
    return sum(1 for p in tracker.all_pairs() if p["score"] != 0)


def _run_evolution_pass(world: WorldState, evo: EvolutionSystem) -> list[dict]:
    """对每只数码兽跑一次"纯羁绊"进化判定,返回本轮发生的进化事件。

    scheduler 只负责移动/对话/派系/剧情,不碰进化。这里补上进化这一涌现层:
    bond = 记忆流 importance 累计(相遇/进化等高 importance 记忆会推高羁绊),
    羁绊够深就自己升一阶。一次只升一阶(check_and_evolve 内部逻辑)。
    """
    evolved: list[dict] = []
    for agent in world.all():
        result = evo.check_and_evolve(agent, battle_victories=agent.battle_victories)
        if result.evolved:
            payload = {
                "type": "evolution",
                "agent": agent.name,
                "from": result.old_stage.value,
                "to": result.new_stage.value,
                "reason": result.reason.value,
            }
            world.events.append(payload)
            evolved.append(payload)
    return evolved


async def run(ticks: int, n_agents: int) -> int:
    set_client(_build_fake_client())

    # 独立世界 / 时钟 / 关系表 / 派系 / 剧情 / 进化(不碰进程级单例,干净可复现)
    world = WorldState()
    _spawn_cluster(world, n_agents)
    clock = WorldClock(real_to_world_ratio=60)
    tracker = RelationshipTracker()
    registry = FactionRegistry()
    director = StoryDirector()
    evo = EvolutionSystem()

    from digimon_world.llm.client import get_client

    scheduler = WorldScheduler(
        world=world,
        clock=clock,
        dialogue=Dialogue(llm_client=get_client()),
        relationships=tracker,
        factions=registry,
        story_director=director,
    )

    print(BAR)
    print(f" Phase 4 涌现性测试  (ticks={ticks}, agents={n_agents})")
    print(BAR)
    print(f" 培养皿: 文件岛中心,{n_agents} 只幼年期数码兽")
    print(f" 成员:   {', '.join(a.name for a in world.all())}")
    print(SUB)
    print(f" {'tick':>5} | {'关系':>4} | {'派系':>4} | {'剧情':>4} | {'进化':>4} | 世界事件")
    print(SUB)

    total_evolutions = 0
    evolution_log: list[dict] = []

    for i in range(1, ticks + 1):
        await scheduler.tick_once(real_seconds=1.0)
        new_evos = _run_evolution_pass(world, evo)
        total_evolutions += len(new_evos)
        evolution_log.extend(new_evos)

        if i % REPORT_EVERY == 0 or i == 1:
            story_events = [e for e in world.events if e.get("type") == "story_event"]
            print(
                f" {i:>5} | {_relationship_count(tracker):>4} | "
                f"{len(registry.all_factions()):>4} | {len(story_events):>4} | "
                f"{total_evolutions:>4} | {len(world.events):>6}"
            )

    # ---- 总结 ----
    pairs = [p for p in tracker.all_pairs() if p["score"] != 0]
    factions = registry.all_factions()
    story_events = [e for e in world.events if e.get("type") == "story_event"]

    print(SUB)
    print(" 涌现总结:")
    print(SUB)

    def _verdict(label: str, happened: bool, detail: str) -> None:
        mark = "✅ 涌现" if happened else "⬜ 未涌现"
        print(f"  {mark}  {label:<10}  {detail}")

    _verdict(
        "关系",
        bool(pairs),
        f"{len(pairs)} 对有效关系,最高 {max((p['score'] for p in pairs), default=0):.0f},"
        f" 最低 {min((p['score'] for p in pairs), default=0):.0f}",
    )
    _verdict(
        "派系",
        bool(factions),
        f"{len(factions)} 个派系 " + ", ".join(
            f"[{f.faction_id}: {'/'.join(sorted(f.members))}]" for f in factions[:3]
        ),
    )
    _verdict(
        "剧情",
        bool(story_events),
        f"{len(story_events)} 起剧情事件: "
        + ", ".join(e.get("event_id", "?") for e in story_events),
    )
    _verdict(
        "进化",
        total_evolutions > 0,
        f"{total_evolutions} 次进化, 最终阶段: "
        + ", ".join(f"{a.name}={a.stage.value}" for a in world.all()),
    )

    # ---- 样本细节 ----
    print(SUB)
    print(" 关系 TOP 5:")
    for p in sorted(pairs, key=lambda x: x["score"], reverse=True)[:5]:
        print(f"    {p['a']} ↔ {p['b']}: {p['score']:.0f}")

    if story_events:
        print(" 剧情事件:")
        for e in story_events:
            print(f"    · [{e.get('event_id')}] {e.get('description')}")

    if evolution_log:
        print(" 进化记录(前 8):")
        for e in evolution_log[:8]:
            print(f"    · {e['agent']}: {e['from']} → {e['to']} ({e['reason']})")

    print(SUB)
    emerged = sum(
        1 for x in (pairs, factions, story_events, evolution_log) if x
    )
    print(f" 四类涌现现象: {emerged}/4 发生")
    print(BAR)

    # 关系一定会涌现(游走必相遇),视为脚本自检: 关系为 0 说明模拟坏了。
    return 0 if pairs else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4 涌现性测试")
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS, help=f"跑多少 tick(默认 {DEFAULT_TICKS})")
    parser.add_argument("--agents", type=int, default=DEFAULT_AGENTS, help=f"数码兽数量(默认 {DEFAULT_AGENTS})")
    args = parser.parse_args()
    return asyncio.run(run(ticks=args.ticks, n_agents=args.agents))


if __name__ == "__main__":
    sys.exit(main())

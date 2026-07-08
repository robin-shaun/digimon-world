"""
DigimonAgent.act() / step() 行为循环测试。

act() 是 Phase 2 主循环的最后一步:
    Observe → Memory → Reflect → Plan → Act

不调 LLM,纯关键词解析:
- 移动: 含 "走/去/飞/..." + 方向词
- 观察: 含 "观察/巡视/看/..."
- 休息: 含 "休息/睡觉/等待/..."
- 兜底: 伪随机小步

所有 agent 都默认有 planner/reflector,planner/reflector 的 LLM 失败时静默返回 fallback,
所以 step() 不需要 mock 也能跑(只是会 fallback)。
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import (
    DigimonAgent,
    DigimonStats,
    EvolutionStage,
)
from digimon_world.world.world_state import DEFAULT_REGIONS, Region


@pytest.fixture
def agumon() -> DigimonAgent:
    """一只新鲜的亚古兽,位置 (200, 400)。"""
    return DigimonAgent(
        name="亚古兽",
        species="agumon",
        stage=EvolutionStage.ROOKIE,
        region_id="file_island",
        location=(200, 400),
        stats=DigimonStats(),
    )


# ═══════════════════════════════════════════════════════════
#  act() - 移动意图
# ═══════════════════════════════════════════════════════════

def test_act_move_right(agumon: DigimonAgent) -> None:
    agumon.current_plan = "向右边走去"
    old = agumon.location
    event = agumon.act()
    assert event["type"] == "moved"
    assert event["agent"] == "亚古兽"
    assert tuple(event["from"]) == old
    # 右移,x 应该增加
    assert event["to"][0] > old[0]
    assert event["to"][1] == old[1]
    # agent.location 同步更新
    assert agumon.location == tuple(event["to"])


def test_act_move_up(agumon: DigimonAgent) -> None:
    agumon.current_plan = "向北走"
    old = agumon.location
    event = agumon.act()
    assert event["type"] == "moved"
    # 北/上 → y 减小
    assert event["to"][1] < old[1]
    assert event["to"][0] == old[0]


def test_act_move_without_direction_defaults_to_one_of_four(agumon: DigimonAgent) -> None:
    agumon.current_plan = "去沙滩走走"
    old = agumon.location
    event = agumon.act()
    assert event["type"] == "moved"
    # 没识别出方向 → 4 方向之一(2faf0ec fix 之后不再是固定向右)
    dx = event["to"][0] - old[0]
    dy = event["to"][1] - old[1]
    # 必须有移动 (dx, dy 至少一个非零)
    assert (dx, dy) != (0, 0), "fallback 必须产生方向"
    # 必须落在一个 4 方向里 (考虑 step 大小是 12)
    valid_dx = {-12, 0, 12}  # 左/不横移/右
    valid_dy = {-12, 0, 12}
    assert dx in valid_dx, f"dx={dx} 不在 4 方向里"
    assert dy in valid_dy, f"dy={dy} 不在 4 方向里"


def test_act_move_combined_directions(agumon: DigimonAgent) -> None:
    agumon.current_plan = "向右下方的商店走去"
    old = agumon.location
    event = agumon.act()
    assert event["type"] == "moved"
    # 右 + 下 → x↑ y↑
    assert event["to"][0] > old[0]
    assert event["to"][1] > old[1]


def test_act_move_uses_default_step(agumon: DigimonAgent) -> None:
    agumon.current_plan = "向东走"
    event = agumon.act()
    assert event["to"][0] - event["from"][0] == DigimonAgent.DEFAULT_STEP


# ═══════════════════════════════════════════════════════════
#  act() - 观察意图
# ═══════════════════════════════════════════════════════════

def test_act_observe_keeps_location(agumon: DigimonAgent) -> None:
    agumon.current_plan = "仔细观察四周"
    old = agumon.location
    event = agumon.act()
    assert event["type"] == "observed"
    assert event["location"] == list(old)
    assert agumon.location == old


def test_act_patrol_triggers_observe(agumon: DigimonAgent) -> None:
    agumon.current_plan = "在沙滩上巡视"
    old = agumon.location
    event = agumon.act()
    # "巡视" 不在移动触发词里,但在观察触发词里
    assert event["type"] == "observed"
    assert agumon.location == old


# ═══════════════════════════════════════════════════════════
#  act() - 休息意图
# ═══════════════════════════════════════════════════════════

def test_act_rest_keeps_location(agumon: DigimonAgent) -> None:
    agumon.current_plan = "在树下休息一会儿"
    old = agumon.location
    event = agumon.act()
    assert event["type"] == "rested"
    assert event["location"] == list(old)
    assert agumon.location == old


def test_act_sleep_triggers_rest(agumon: DigimonAgent) -> None:
    agumon.current_plan = "该睡觉了"
    old = agumon.location
    event = agumon.act()
    assert event["type"] == "rested"
    assert agumon.location == old


# ═══════════════════════════════════════════════════════════
#  act() - 兜底
# ═══════════════════════════════════════════════════════════

def test_act_fallback_when_no_plan(agumon: DigimonAgent) -> None:
    agumon.current_plan = None
    old = agumon.location
    event = agumon.act()
    # 无计划 → 兜底走一步
    assert event["type"] == "moved"
    assert event.get("fallback") is True
    # 步长是默认的一半
    dx = event["to"][0] - event["from"][0]
    dy = event["to"][1] - event["from"][1]
    assert abs(dx) + abs(dy) == DigimonAgent.DEFAULT_STEP // 2


def test_act_fallback_when_unrecognized_plan(agumon: DigimonAgent) -> None:
    agumon.current_plan = "唱歌"  # 不在三类触发词里
    event = agumon.act()
    assert event["type"] == "moved"
    assert event.get("fallback") is True


def test_act_fallback_deterministic_by_memory_id(agumon: DigimonAgent) -> None:
    """兜底方向由 memory.next_id 决定 → 可复现。"""
    agumon.current_plan = "不明意图"
    agumon.memory.next_id = 0  # 0 % 4 == 0 → (-1, 0)... wait, idx=0 → (0, -1)
    event0 = agumon.act()

    agumon2 = DigimonAgent(
        name="加布兽", species="gabumon", location=(200, 400)
    )
    agumon2.current_plan = "不明意图"
    agumon2.memory.next_id = 0
    event2 = agumon2.act()
    # 同样 next_id = 0 → 同样方向
    assert event0["to"][0] - event0["from"][0] == event2["to"][0] - event2["from"][0]
    assert event0["to"][1] - event0["from"][1] == event2["to"][1] - event2["from"][1]


# ═══════════════════════════════════════════════════════════
#  act() - 边界
# ═══════════════════════════════════════════════════════════

def test_act_move_clamps_to_non_negative(agumon: DigimonAgent) -> None:
    agumon.location = (5, 5)
    agumon.current_plan = "向左上方走"
    event = agumon.act()
    # 坐标不能变负
    assert event["to"][0] >= 0
    assert event["to"][1] >= 0


def test_act_clamps_to_region_bounds(agumon: DigimonAgent) -> None:
    """agent 已在地区右下边界,再往右下走,应停在边界不越界。"""
    # file_island bounds = (0, 0, 960, 600)
    agumon.region_id = "file_island"
    agumon.location = (960, 600)
    agumon.current_plan = "向右下方继续走"
    event = agumon.act(DEFAULT_REGIONS)
    assert event["type"] == "moved"
    # 夹紧在 max_x / max_y,不越界
    assert event["to"][0] == 960
    assert event["to"][1] == 600
    assert agumon.location == (960, 600)


def test_act_clamps_to_region_bounds_smaller_region(agumon: DigimonAgent) -> None:
    """自定义小地区: 边界应来自该 region,而非硬编码 960/600。"""
    regions = {
        "tiny": Region(region_id="tiny", name="小地区", description="", bounds=(0, 0, 100, 100)),
    }
    agumon.region_id = "tiny"
    agumon.location = (100, 100)
    agumon.current_plan = "向右下走"
    event = agumon.act(regions)
    assert event["to"][0] == 100
    assert event["to"][1] == 100


def test_act_unknown_region_logs_warning(agumon: DigimonAgent, caplog) -> None:
    """region_id 不在 regions 中 → 跳过移动,原地不动,记 warning。"""
    agumon.region_id = "atlantis"  # 不存在
    agumon.location = (200, 400)
    agumon.current_plan = "向右走"
    with caplog.at_level("WARNING"):
        event = agumon.act(DEFAULT_REGIONS)
    # 位置不变
    assert event["to"] == [200, 400]
    assert event["from"] == [200, 400]
    assert agumon.location == (200, 400)
    assert event.get("skipped") == "unknown_region"
    # 记了 warning
    assert any("atlantis" in r.message or "atlantis" in str(r.args) for r in caplog.records)


def test_act_unknown_region_skips_fallback_move(agumon: DigimonAgent) -> None:
    """兜底分支同样受 region 检查保护,不会走出未知世界。"""
    agumon.region_id = "atlantis"
    agumon.location = (200, 400)
    agumon.current_plan = "唱歌"  # 触发兜底
    event = agumon.act(DEFAULT_REGIONS)
    assert event["to"] == [200, 400]
    assert event.get("skipped") == "unknown_region"
    assert event.get("fallback") is True
    assert agumon.location == (200, 400)


def test_act_without_regions_preserves_legacy_behavior(agumon: DigimonAgent) -> None:
    """不传 regions(旧调用方 / 单测)→ 行为不变: 仅非负夹紧,正常移动。"""
    agumon.location = (200, 400)
    agumon.current_plan = "向右走"
    event = agumon.act()
    assert event["type"] == "moved"
    assert event["to"][0] > 200
    assert "skipped" not in event


def test_get_bounds_returns_region_bounds(agumon: DigimonAgent) -> None:
    agumon.region_id = "file_island"
    assert agumon.get_bounds(DEFAULT_REGIONS) == (0, 0, 960, 600)


def test_get_bounds_none_when_unknown(agumon: DigimonAgent) -> None:
    agumon.region_id = "atlantis"
    assert agumon.get_bounds(DEFAULT_REGIONS) is None
    assert agumon.get_bounds(None) is None


def test_act_event_has_iso_timestamp(agumon: DigimonAgent) -> None:
    agumon.current_plan = "向右走"
    event = agumon.act()
    assert "at" in event
    # ISO 格式长度至少 19 字符
    assert len(event["at"]) >= 19


def test_act_event_includes_plan_for_tracing(agumon: DigimonAgent) -> None:
    agumon.current_plan = "向右走"
    event = agumon.act()
    assert event["plan"] == "向右走"


# ═══════════════════════════════════════════════════════════
#  step() - 完整主循环一步
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_step_full_loop_records_memory(agumon: DigimonAgent) -> None:
    """step() 跑一次后,记忆流里应该多一条 act() 产生的事件。"""
    agumon.current_plan = "向右走走看风景"  # → 移动
    initial_count = len(agumon.memory.entries)
    event = await agumon.step()
    # 事件是 moved
    assert event["type"] == "moved"
    # 记忆多了一条
    assert len(agumon.memory.entries) == initial_count + 1
    # 重要性由 _heuristic_importance 给出,"moved" → 3
    assert agumon.memory.entries[-1].importance == 3


@pytest.mark.asyncio
async def test_step_no_planner_uses_fallback(agumon: DigimonAgent) -> None:
    """没有 planner → fallback 计划 + 兜底事件。"""
    # 默认 agent.planner 是 None
    assert agumon.planner is None
    event = await agumon.step()
    # fallback 计划是 "在附近闲逛, 保持警觉" → "闲逛" 是移动触发词
    assert event["type"] == "moved"


@pytest.mark.asyncio
async def test_step_no_reflector_silently_skips(agumon: DigimonAgent) -> None:
    """没有 reflector → reflect_if_needed 静默返回,不抛异常。"""
    assert agumon.reflector is None
    # 不应抛
    event = await agumon.step()
    assert event is not None


@pytest.mark.asyncio
async def test_step_does_not_raise_with_any_plan(agumon: DigimonAgent) -> None:
    """各种怪计划文本都不应让 step() 抛异常。"""
    for plan in ["", None, "唱歌跳舞", "去天空飞", "睡觉休息", "随机行为 xyz"]:
        agumon.current_plan = plan
        event = await agumon.step()
        assert event is not None
        assert "type" in event
        assert "agent" in event
        assert event["agent"] == "亚古兽"

@pytest.mark.asyncio
async def test_act_fallback_4_directions_diverse(agumon: DigimonAgent) -> None:
    """无方向关键词时, fallback 应在 4 方向中分布(连续多次 act() 不应只走 1 个方向)。

    实际: 上次 2faf0ec fix 用 memory.next_id%4,但 next_id 跨多次 act 可能
    产生重复方向,导致数码兽在 x=960 边界卡死。本测试在多次 act 后
    验证至少命中过 2+ 个不同方向(用 time.time 偏移打散)。
    """
    # 把 plan 设成"无方向关键词" 触发 fallback
    agumon.current_plan = "在附近闲逛, 保持警觉"
    seen_dirs = set()
    # 试 50 次, 必出现 2+ 不同方向
    for _ in range(50):
        # 重新初始化 location 让每次 act 都能产生不同 from
        agumon.location = (100, 100)
        event = agumon.act()
        if event.get("type") == "moved":
            from_xy = tuple(event["from"])
            to_xy = tuple(event["to"])
            dx = to_xy[0] - from_xy[0]
            dy = to_xy[1] - from_xy[1]
            if (dx, dy) != (0, 0):
                # 归一化到 4 方向
                if dx != 0: dx = 1 if dx > 0 else -1
                if dy != 0: dy = 1 if dy > 0 else -1
                seen_dirs.add((dx, dy))
    # 至少看到 2 个不同方向
    assert len(seen_dirs) >= 2, f"只看到一个方向 {seen_dirs}, fallback 退化"

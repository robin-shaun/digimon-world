"""
社交关系系统测试
================

覆盖:
- 初始关系为 0(中立)
- update 正/负 + 对称 + 夹紧
- get_faction 返回最友好 / 最敌对
- battle 自动调整关系(-10 敌对, 输方 +5 敬畏)
- dialogue 自动调整关系(+3 友好)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world.api import app as fastapi_app
from digimon_world.world import get_world, reset_world
from digimon_world.world.relationships import (
    DIALOGUE_DELTA,
    MAX_SCORE,
    MIN_SCORE,
    RelationshipTracker,
    reset_tracker,
)

# ---- 1. 初始化关系为 0 ----


def test_initial_relationship_is_zero() -> None:
    """从未互动过的两只数码兽,关系值为 0(中立)。"""
    rt = RelationshipTracker()
    assert rt.get_relationship("亚古兽", "加布兽") == 0.0
    # 自我关系恒为 0
    assert rt.get_relationship("亚古兽", "亚古兽") == 0.0


# ---- 2. update 正负 ----


def test_update_positive_and_negative() -> None:
    """update 正负增量累加,双向对称,并夹紧在 [MIN, MAX]。"""
    rt = RelationshipTracker()

    rt.update("A", "B", +30)
    assert rt.get_relationship("A", "B") == 30.0
    # 对称: (B, A) 命中同一条
    assert rt.get_relationship("B", "A") == 30.0

    rt.update("A", "B", -50)
    assert rt.get_relationship("A", "B") == -20.0

    # 上界夹紧
    rt.update("A", "B", +999)
    assert rt.get_relationship("A", "B") == MAX_SCORE
    # 下界夹紧
    rt.update("A", "B", -9999)
    assert rt.get_relationship("A", "B") == MIN_SCORE

    # 自我 update 是 no-op
    assert rt.update("A", "A", +50) == 0.0
    assert rt.get_relationship("A", "A") == 0.0


# ---- 3. get_faction ----


def test_get_faction_returns_ally_and_rival() -> None:
    """get_faction 返回最友好的 ally 和最敌对的 rival。"""
    rt = RelationshipTracker()
    rt.update("亚古兽", "加布兽", +40)   # 好朋友
    rt.update("亚古兽", "比丘兽", +10)   # 一般朋友
    rt.update("亚古兽", "暴龙兽", -60)   # 死敌

    faction = rt.get_faction("亚古兽")
    assert faction["ally"] == "加布兽"
    assert faction["rival"] == "暴龙兽"

    # 只有正关系时 rival 为 None
    rt2 = RelationshipTracker()
    rt2.update("X", "Y", +5)
    f2 = rt2.get_faction("X")
    assert f2["ally"] == "Y"
    assert f2["rival"] is None

    # 完全没关系 → 两者都 None
    assert rt2.get_faction("孤独兽") == {"ally": None, "rival": None}


# ---- 4. battle 自动调整 ----


def test_battle_auto_adjusts_relationship() -> None:
    """record_battle: affinity 下降, rivalry/respect/fear 分别上升。"""
    rt = RelationshipTracker()
    rt.record_battle(winner="亚古兽", loser="加布兽")
    # get_relationship() 返回纯亲和度 (BATTLE_DELTA = -10)
    assert rt.get_relationship("亚古兽", "加布兽") == -10.0

    # 平局 / None 不改变关系
    rt.record_battle(winner=None, loser="加布兽")
    assert rt.get_relationship("亚古兽", "加布兽") == -10.0


def test_battle_api_updates_relationship() -> None:
    """POST /api/battle/start 后 GET /api/relationships 出现这一对且为负。"""
    reset_world()
    reset_tracker()
    get_world()  # 初始化亚古兽 / 加布兽 / 比丘兽
    client = TestClient(fastapi_app)

    r = client.post(
        "/api/battle/start",
        json={"attacker": "亚古兽", "defender": "加布兽"},
    )
    assert r.status_code == 200, r.text

    rel = client.get("/api/relationships")
    assert rel.status_code == 200
    pairs = rel.json()["pairs"]
    assert len(pairs) == 1
    pair = pairs[0]
    assert {pair["a"], pair["b"]} == {"亚古兽", "加布兽"}
    # 打过一架 → 关系为负
    assert pair["score"] < 0
    reset_world()
    reset_tracker()


# ---- 5. dialogue 自动调整 ----


@pytest.mark.asyncio
async def test_dialogue_auto_adjusts_relationship() -> None:
    """Phase 6 显著性阈值: routine proximity 只加基础亲近,不触发 LLM 对话。

    首次 tick: 相遇 → PROXIMITY_DELTA + 节日 RELATIONSHIP_BOOST。
    LLM 对话需 significance >= 6,普通相遇仅 5,被拦截。
    """
    from digimon_world.agents.dialogue import Dialogue
    from digimon_world.agents.digimon_agent import DigimonAgent
    from digimon_world.llm.client import FakeLlmClient, LlmModel
    from digimon_world.world.clock import WorldClock
    from digimon_world.world.festivals import RELATIONSHIP_BOOST, FestivalSystem
    from digimon_world.world.scheduler import WorldScheduler
    from digimon_world.world.world_state import WorldState

    world = WorldState()
    world.spawn(DigimonAgent(name="甲兽", species="a", region_id="file_island", location=(100, 100)))
    world.spawn(DigimonAgent(name="乙兽", species="b", region_id="file_island", location=(120, 100)))

    fake = FakeLlmClient()
    fake.set_reply(LlmModel.MINIMAX_M3, reply="你好呀!")
    dialogue = Dialogue(llm_client=fake)

    tracker = RelationshipTracker()
    clock = WorldClock()
    festivals = FestivalSystem()
    sched = WorldScheduler(
        world=world, clock=clock, dialogue=dialogue,
        relationships=tracker, festivals=festivals,
        dialogue_prob=1.0,
    )

    assert tracker.get_relationship("甲兽", "乙兽") == 0.0
    await sched.tick_once()
    # Phase 6: proximity 显著性 5 ≥ 阈值 4 → 触发 LLM 对话
    # → record_dialogue_with_personality(基础 + 欲望加成 + MBTI 加成) + 节日加成
    # 基础: DIALOGUE_DELTA=3.0, 节日: RELATIONSHIP_BOOST=5.0
    # 欲望为空 → 0, MBTI 随机 → 区间 [0, MBTI_BONUS_CAP=4.0]
    # 因此结果区间 [8.0, 12.0]
    score = tracker.get_relationship("甲兽", "乙兽")
    assert score >= DIALOGUE_DELTA + RELATIONSHIP_BOOST, f"Expected >= {DIALOGUE_DELTA+RELATIONSHIP_BOOST}, got {score}"
    assert score <= DIALOGUE_DELTA + RELATIONSHIP_BOOST + 4.0, f"Expected <= {DIALOGUE_DELTA+RELATIONSHIP_BOOST+4.0}, got {score}"


# ---- 6. 隐性欲望(latent desire)测试 ----


def test_desire_affinity_exact_match() -> None:
    """完全相同的欲望 → 兼容度 1.0。"""
    assert RelationshipTracker.desire_affinity("想变强", "想变强") == 1.0


def test_desire_affinity_same_category() -> None:
    """同一类别(不同措辞)的欲望 → 兼容度 0.6。"""
    # "变强" 和 "想变强" 都在 strength 类别
    result = RelationshipTracker.desire_affinity("变强", "想变强")
    assert result == 0.6


def test_desire_affinity_empty() -> None:
    """空欲望不影响 → 兼容度 0.0。"""
    assert RelationshipTracker.desire_affinity("", "想变强") == 0.0
    assert RelationshipTracker.desire_affinity("想变强", "") == 0.0
    assert RelationshipTracker.desire_affinity("", "") == 0.0


def test_desire_affinity_different_category() -> None:
    """不同类别欲望 → 兼容度 0.0。"""
    assert RelationshipTracker.desire_affinity("想变强", "想交朋友") == 0.0


def test_record_dialogue_with_matching_desires() -> None:
    """欲望相同 → 对话关系增量包含 bonus。"""
    rt = RelationshipTracker()
    base = DIALOGUE_DELTA
    # 欲望完全匹配: affinity=1.0, bonus=min(4.0*1.0, 6.0)=4.0
    expected = base + 4.0
    got = rt.record_dialogue_with_desire("亚古兽", "想变强", "暴龙兽", "想变强")
    assert got == expected
    assert rt.get_relationship("亚古兽", "暴龙兽") == expected


def test_record_dialogue_with_empty_desires() -> None:
    """欲望为空 → 无加成,与旧 record_dialogue 行为一致。"""
    rt = RelationshipTracker()
    got = rt.record_dialogue_with_desire("亚古兽", "", "加布兽", "")
    assert got == DIALOGUE_DELTA


def test_record_dialogue_with_same_category_desires() -> None:
    """欲望同类别 → 部分加成。"""
    rt = RelationshipTracker()
    # affinity=0.6, bonus=min(4.0*0.6, 6.0)=2.4
    expected = DIALOGUE_DELTA + 2.4
    got = rt.record_dialogue_with_desire("亚古兽", "变强", "暴龙兽", "想变强")
    assert got == expected


# ---- 7. MBTI 人格兼容加成 (Phase 17 Task 4) ----


def test_mbti_compatibility_bonus_empty() -> None:
    """空 MBTI 类型 → bonus 为 0。"""
    assert RelationshipTracker.mbti_compatibility_bonus("", "") == 0.0
    assert RelationshipTracker.mbti_compatibility_bonus("INTJ", "") == 0.0
    assert RelationshipTracker.mbti_compatibility_bonus("", "ENFP") == 0.0


def test_mbti_compatibility_bonus_max() -> None:
    """最佳配对 INTJ + ENFP → 兼容度 1.0 → bonus = MBTI_BONUS_FACTOR。"""
    from digimon_world.world.relationships import MBTI_BONUS_CAP, MBTI_BONUS_FACTOR
    expected = min(MBTI_BONUS_FACTOR * 1.0, MBTI_BONUS_CAP)
    assert RelationshipTracker.mbti_compatibility_bonus("INTJ", "ENFP") == expected


def test_mbti_compatibility_bonus_moderate() -> None:
    """中等兼容 INTJ + INTP (0.8) → bonus = MBTI_BONUS_FACTOR * 0.8。"""
    from digimon_world.world.relationships import MBTI_BONUS_CAP, MBTI_BONUS_FACTOR
    expected = min(MBTI_BONUS_FACTOR * 0.8, MBTI_BONUS_CAP)
    assert RelationshipTracker.mbti_compatibility_bonus("INTJ", "INTP") == expected


def test_mbti_compatibility_bonus_low() -> None:
    """低兼容 INTJ + ESFJ (0.2) → bonus = MBTI_BONUS_FACTOR * 0.2。"""
    from digimon_world.world.relationships import MBTI_BONUS_CAP, MBTI_BONUS_FACTOR
    expected = min(MBTI_BONUS_FACTOR * 0.2, MBTI_BONUS_CAP)
    assert RelationshipTracker.mbti_compatibility_bonus("INTJ", "ESFJ") == expected


def test_record_dialogue_with_personality_full_bonus() -> None:
    """欲望完全匹配 + MBTI 最佳配对 → 最大加成。"""
    from digimon_world.world.relationships import DESIRE_BONUS_FACTOR, MBTI_BONUS_CAP, MBTI_BONUS_FACTOR
    rt = RelationshipTracker()
    # desire: 1.0 → DESIRE_BONUS_FACTOR*1.0=4.0, capped at DESIRE_BONUS_CAP=6.0 → 4.0
    # mbti: INTJ+ENFP=1.0 → MBTI_BONUS_FACTOR*1.0=3.0, capped at MBTI_BONUS_CAP=4.0 → 3.0
    # total: 3.0 + 4.0 + 3.0 = 10.0
    expected = DIALOGUE_DELTA + DESIRE_BONUS_FACTOR + min(MBTI_BONUS_FACTOR * 1.0, MBTI_BONUS_CAP)
    got = rt.record_dialogue_with_personality(
        "亚古兽", "想变强", "暴龙兽", "想变强",
        mbti_a="INTJ", mbti_b="ENFP",
    )
    assert got == expected
    assert rt.get_relationship("亚古兽", "暴龙兽") == expected


def test_record_dialogue_with_personality_no_mbti() -> None:
    """MBTI 为空 → 行为与 record_dialogue_with_desire 一致。"""
    # 使用独立 tracker 避免互相影响
    rt1 = RelationshipTracker()
    got = rt1.record_dialogue_with_personality(
        "亚古兽", "想变强", "暴龙兽", "想变强",
    )
    rt2 = RelationshipTracker()
    expected = rt2.record_dialogue_with_desire("亚古兽", "想变强", "暴龙兽", "想变强")
    assert got == expected


def test_record_proximity_with_personality() -> None:
    """相遇含欲望+MBTI 加成（打折）。"""
    from digimon_world.world.relationships import (
        DESIRE_BONUS_FACTOR,
        MBTI_BONUS_CAP,
        MBTI_BONUS_FACTOR,
        PROXIMITY_DELTA,
    )
    rt = RelationshipTracker()
    # desire: 1.0 → 4.0*0.5=2.0
    # mbti: 1.0 → 3.0*0.5=1.5
    # total: 1.0 + 2.0 + 1.5 = 4.5
    desire_bonus = min(DESIRE_BONUS_FACTOR * 1.0 * 0.5, 6.0 * 0.5)
    mbti_bonus = min(MBTI_BONUS_FACTOR * 1.0 * 0.5, MBTI_BONUS_CAP * 0.5)
    expected = PROXIMITY_DELTA + desire_bonus + mbti_bonus
    got = rt.record_proximity_with_personality(
        "亚古兽", "想变强", "暴龙兽", "想变强",
        mbti_a="INTJ", mbti_b="ENFP",
    )
    assert got == expected

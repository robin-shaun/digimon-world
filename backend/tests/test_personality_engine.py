"""人格引擎测试 — 基于荣格心理学 MBTI 的动态人格系统。"""
import pytest

from digimon_world.world.personality_engine import (
    MbtiDimension,
    PersonalityEvolutionEngine,
    PersonalityProfile,
)


class TestPersonalityProfile:
    """测试人格档案。"""

    def test_default_initialization(self):
        """默认初始化为中性人格 (全 0)。"""
        p = PersonalityProfile()
        assert p.ei == 0.0
        assert p.sn == 0.0
        assert p.tf == 0.0
        assert p.jp == 0.0
        assert p.type_code == "ESTJ"  # 0 = positive = E/S/T/J
        assert p.ei_strength == 0.0
        assert p.sn_strength == 0.0
        assert p.tf_strength == 0.0
        assert p.jp_strength == 0.0

    def test_clear_type_detection(self):
        """清晰类型 vs 模糊类型检测。"""
        clear = PersonalityProfile(ei=0.8, sn=-0.7, tf=0.6, jp=-0.9)
        assert clear.type_code == "ENTP"
        assert clear.is_clear_type() is True

        fuzzy = PersonalityProfile(ei=0.2, sn=-0.1, tf=0.0, jp=0.1)
        assert fuzzy.is_clear_type() is False

    def test_type_code_with_strong_dimensions(self):
        """强维度正确映射到 MBTI 类型。"""
        p = PersonalityProfile(ei=0.9, sn=-0.8, tf=-0.7, jp=0.6)
        assert p.type_code == "ENFJ"

    def test_to_dict_serialization(self):
        """to_dict 包含所有关键字段。"""
        p = PersonalityProfile(ei=0.5, sn=-0.3, tf=0.7, jp=-0.1)
        d = p.to_dict()
        assert d["type_code"] == "ENTP"
        assert "ei" in d
        assert "sn" in d
        assert "tf" in d
        assert "jp" in d
        assert "strengths" in d
        assert "history" in d
        assert "evolution_count" in d

    def test_dominant_dimension(self):
        """dominant_dimension 返回最强维度。"""
        p = PersonalityProfile(ei=0.2, sn=-0.9, tf=0.3, jp=0.1)
        assert p.dominant_dimension() == "sn"

    def test_history_tracking(self):
        """演化历史记录正确。"""
        p = PersonalityProfile()
        assert len(p.history) == 0
        p.history.append({"event": "test", "result_type": "ESTJ", "time": "now"})
        assert len(p.history) == 1


class TestMbtiDimension:
    """测试维度枚举。"""

    def test_letter_positive(self):
        """正值返回第一极字母。"""
        assert MbtiDimension.EI.letter(0.5) == "E"
        assert MbtiDimension.SN.letter(0.0) == "S"  # 0 = positive
        assert MbtiDimension.TF.letter(0.1) == "T"
        assert MbtiDimension.JP.letter(0.9) == "J"

    def test_letter_negative(self):
        """负值返回第二极字母。"""
        assert MbtiDimension.EI.letter(-0.5) == "I"
        assert MbtiDimension.SN.letter(-0.1) == "N"
        assert MbtiDimension.TF.letter(-0.7) == "F"
        assert MbtiDimension.JP.letter(-0.3) == "P"

    def test_positive_label(self):
        """positive_label 返回中文描述。"""
        assert "外倾" in MbtiDimension.EI.positive_label()
        assert "感觉" in MbtiDimension.SN.positive_label()
        assert "思考" in MbtiDimension.TF.positive_label()
        assert "判断" in MbtiDimension.JP.positive_label()

    def test_negative_label(self):
        """negative_label 返回中文描述。"""
        assert "内倾" in MbtiDimension.EI.negative_label()
        assert "直觉" in MbtiDimension.SN.negative_label()
        assert "情感" in MbtiDimension.TF.negative_label()
        assert "感知" in MbtiDimension.JP.negative_label()


class TestEvolutionEngine:
    """测试演化引擎核心逻辑。"""

    @pytest.fixture
    def engine(self):
        return PersonalityEvolutionEngine(evolution_rate=1.0, regression_strength=0.0)

    def test_get_or_create_returns_same_profile(self, engine):
        """同名 agent 返回同一档案。"""
        p1 = engine.get_or_create("Agumon")
        p2 = engine.get_or_create("Agumon")
        assert p1 is p2

    def test_get_or_create_different_agents(self, engine):
        """不同 agent 返回不同档案。"""
        p1 = engine.get_or_create("Agumon")
        p2 = engine.get_or_create("Gabumon")
        assert p1 is not p2

    def test_initial_profile_is_valid(self, engine):
        """初始档案维度在合法范围内。"""
        p = engine.get_or_create("Agumon")
        assert -1.0 <= p.ei <= 1.0
        assert -1.0 <= p.sn <= 1.0
        assert -1.0 <= p.tf <= 1.0
        assert -1.0 <= p.jp <= 1.0
        assert len(p.type_code) == 4

    def test_apply_event_changes_dimensions(self, engine):
        """事件应用后维度值变化。"""
        p = engine.get_or_create("Agumon")
        # 手动设已知值，关回归
        p.ei = 0.0
        p.sn = 0.0
        p.tf = 0.0
        p.jp = 0.0
        p._recompute()

        updated = engine.apply_event("Agumon", "battle_win")
        assert updated.ei > 0.0  # 战斗胜利 → +E
        assert updated.tf > 0.0  # 战斗胜利 → +T

    def test_apply_event_social_friendly(self, engine):
        """社交友好事件推动 +E, +F。"""
        p = engine.get_or_create("Gabumon")
        p.ei = 0.0
        p.sn = 0.0
        p.tf = 0.0
        p.jp = 0.0
        p._recompute()

        updated = engine.apply_event("Gabumon", "social_friendly")
        assert updated.ei > 0.0  # +E
        assert updated.tf < 0.0  # -T = +F 方向

    def test_apply_event_alone_time(self, engine):
        """独处时间推动 -E。"""
        p = engine.get_or_create("Tentomon")
        p.ei = 0.0
        p._recompute()

        updated = engine.apply_event("Tentomon", "alone_time")
        assert updated.ei < 0.0  # 独处 → 更内向

    def test_apply_event_multiplier(self, engine):
        """multiplier 放大事件影响。"""
        p = engine.get_or_create("Agumon")
        p.ei = 0.0
        p._recompute()

        normal = engine.apply_event("Agumon", "battle_win", multiplier=1.0)
        p2 = engine.get_or_create("Gabumon")
        p2.ei = 0.0
        p2._recompute()
        boosted = engine.apply_event("Gabumon", "battle_win", multiplier=3.0)

        # 3倍 multiplier 应该比 1倍 变化大
        assert abs(boosted.ei) > abs(normal.ei) or abs(boosted.tf) > abs(normal.tf)

    def test_regression_toward_zero(self):
        """回归均值让极端值向 0 漂移。"""
        engine = PersonalityEvolutionEngine(evolution_rate=1.0, regression_strength=0.1)
        p = engine.get_or_create("Agumon")
        p.ei = 0.95  # 极端外向
        p._recompute()

        # 施加一个不影响 EI 的事件
        updated = engine.apply_event("Agumon", "explore_discovery")
        # 回归应让 EI 下降
        assert updated.ei < 0.95

    def test_clamp_prevents_exceeding_bounds(self, engine):
        """维度值不会超过 [-1.0, 1.0] 边界。"""
        p = engine.get_or_create("Agumon")
        p.ei = 0.99
        p._recompute()

        # 连续施加极端事件
        for _ in range(20):
            engine.apply_event("Agumon", "battle_win", multiplier=5.0)

        final = engine.get("Agumon")
        assert -1.0 <= final.ei <= 1.0

    def test_evolution_history_recorded(self, engine):
        """每次演化记录到历史。"""
        engine.get_or_create("Agumon")
        engine.apply_event("Agumon", "battle_win", description="击败了黑暗齿轮")
        engine.apply_event("Agumon", "social_friendly", description="和加布兽交友")

        p = engine.get("Agumon")
        assert p.evolution_count == 2
        assert len(p.history) == 2
        assert p.history[0]["event"] == "battle_win"
        assert p.history[1]["event"] == "social_friendly"
        assert "battle_win" in p.history[0]["desc"] or p.history[0]["desc"] == "击败了黑暗齿轮"

    def test_history_capped_at_100(self, engine):
        """历史记录最多保留 100 条。"""
        engine.get_or_create("Agumon")
        for i in range(150):  # noqa: B007
            engine.apply_event("Agumon", "battle_win")

        p = engine.get("Agumon")
        assert len(p.history) <= 100
        assert p.evolution_count == 150

    def test_unknown_event_type_no_crash(self, engine):
        """未知事件类型不会崩溃。"""
        engine.get_or_create("Agumon")
        p_before = engine.get("Agumon")
        result = engine.apply_event("Agumon", "nonexistent_event")
        assert result is p_before  # 返回原档案

    def test_list_all(self, engine):
        """list_all 返回所有 agent。"""
        engine.get_or_create("Agumon")
        engine.get_or_create("Gabumon")
        all_agents = engine.list_all()
        assert len(all_agents) == 2
        names = [name for name, _ in all_agents]
        assert "Agumon" in names
        assert "Gabumon" in names

    def test_reset_clears_all(self, engine):
        """reset 清除所有档案。"""
        engine.get_or_create("Agumon")
        engine.reset()
        assert len(engine.list_all()) == 0

    def test_set_manual_profile(self, engine):
        """set 可手动设置档案。"""
        custom = PersonalityProfile(ei=0.8, sn=-0.6, tf=0.4, jp=-0.2)
        engine.set("CustomMon", custom)
        retrieved = engine.get("CustomMon")
        assert retrieved.type_code == "ENTP"
        assert retrieved.ei == 0.8

    def test_get_nonexistent(self, engine):
        """不存在的 agent 返回 None。"""
        assert engine.get("NoSuchMon") is None


class TestCompatibility:
    """测试人格兼容矩阵。"""

    @pytest.fixture
    def engine(self):
        return PersonalityEvolutionEngine()

    def test_compatibility_intj_enfp_golden_pair(self, engine):
        """INTJ-ENFP 是黄金配对，兼容度应为 1.0。"""
        compat = engine.compatibility("INTJ", "ENFP")
        assert compat == 1.0

    def test_compatibility_same_type_moderate(self, engine):
        """同类型兼容度应为中等 (0.7)。"""
        compat = engine.compatibility("INTP", "INTP")
        assert compat == 0.7

    def test_compatibility_unknown_fallback(self, engine):
        """不在矩阵中的配对使用默认值。"""
        compat = engine.compatibility("XXXX", "YYYY")
        assert compat == 0.5  # 默认值

    def test_compatibility_symmetric(self, engine):
        """兼容度应对称。"""
        # 检查矩阵中明确值的对称性
        assert engine.compatibility("ENFP", "INTJ") == 1.0
        assert engine.compatibility("INTJ", "ENFP") == 1.0

    def test_agent_compatibility_with_profiles(self, engine):
        """agent_compatibility 基于类型计算。"""
        engine.set("MonA", PersonalityProfile(ei=0.8, sn=-0.7, tf=0.6, jp=-0.9))  # ENTP
        engine.set("MonB", PersonalityProfile(ei=-0.9, sn=-0.8, tf=0.7, jp=0.6))  # INTJ
        compat = engine.agent_compatibility("MonA", "MonB")
        assert compat > 0.7  # ENTP-INTJ 高兼容

    def test_agent_compatibility_missing_profile(self, engine):
        """缺档案时返回默认兼容度。"""
        compat = engine.agent_compatibility("Ghost", "Phantom")
        assert compat == 0.5


class TestGlobalSingleton:
    """测试全局单例。"""

    def test_get_personality_engine_singleton(self):
        """get 返回同一个实例。"""
        from digimon_world.world.personality_engine import (
            get_personality_engine,
            reset_personality_engine,
        )
        reset_personality_engine()
        e1 = get_personality_engine()
        e2 = get_personality_engine()
        assert e1 is e2

    def test_reset_personality_engine(self):
        """reset 创建新实例。"""
        from digimon_world.world.personality_engine import (
            get_personality_engine,
            reset_personality_engine,
        )
        reset_personality_engine()
        e1 = get_personality_engine()
        reset_personality_engine()
        e2 = get_personality_engine()
        assert e1 is not e2


class TestEventImpacts:
    """测试所有预设事件类型的影响方向。"""

    @pytest.mark.parametrize("event_type,check_dim,expect_sign", [
        ("battle_win", "ei", "positive"),
        ("battle_win", "tf", "positive"),
        ("battle_loss", "ei", "negative"),
        ("social_friendly", "ei", "positive"),
        ("social_friendly", "tf", "negative"),  # → F
        ("alone_time", "ei", "negative"),
        ("evolution", "ei", "positive"),
        ("save_other", "tf", "negative"),  # → F
        ("save_other", "ei", "positive"),
    ])
    def test_event_impact_sign(self, event_type, check_dim, expect_sign):
        """验证事件对各维度的影响方向正确。"""
        impacts = PersonalityEvolutionEngine.EVENT_IMPACTS[event_type]
        delta = impacts[check_dim]
        if expect_sign == "positive":
            assert delta >= 0, f"{event_type} should push {check_dim} positive, got {delta}"
        else:
            assert delta <= 0, f"{event_type} should push {check_dim} negative, got {delta}"

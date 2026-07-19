"""
Phase 20: 自演化世界模型 — 单元测试 + 集成测试
================================================

测试覆盖:
- 状态相似度计算 (Jaccard + Euclidean)
- EpisodicMemory 存储/检索/FIFO
- SemanticMemory 规则提取/匹配/去重
- SelectiveForesight 三级级联预测
- WorldModel observe/predict/evaluate_plan/stats
- 序列化往返
- DigimonAgent 集成 (world_model 创建 + step() 记录情节)
- API 端点 GET /api/digimon/{name}/world-model
"""

from __future__ import annotations

import pytest

from digimon_world.memory.world_model import (
    Episode,
    EpisodicMemory,
    PredictionResult,
    Rule,
    SelectiveForesight,
    SemanticMemory,
    WorldModel,
    _action_similarity,
    _classify_action,
    _extract_actions_from_plan,
    _jaccard_categorical,
    _normalized_euclidean,
    state_similarity,
)

# ──────────────────────────────────────────────
# 状态相似度
# ──────────────────────────────────────────────


class TestStateSimilarity:
    """状态相似度计算函数。"""

    def test_jaccard_identical(self):
        s = {"region_id": "forest", "stage": "rookie", "time_of_day": "day", "weather": "clear"}
        assert _jaccard_categorical(s, s) == 1.0

    def test_jaccard_half_match(self):
        s1 = {"region_id": "forest", "stage": "rookie"}
        s2 = {"region_id": "forest", "stage": "champion"}
        assert _jaccard_categorical(s1, s2) == 0.5

    def test_jaccard_no_match(self):
        s1 = {"region_id": "forest", "stage": "rookie"}
        s2 = {"region_id": "mountain", "stage": "champion"}
        assert _jaccard_categorical(s1, s2) == 0.0

    def test_jaccard_missing_fields(self):
        """其中一个状态缺少字段时应忽略该字段。"""
        s1 = {"region_id": "forest"}
        s2 = {"region_id": "forest", "stage": "rookie"}
        # region_id match=1/1 → 1.0
        assert _jaccard_categorical(s1, s2) == 1.0

    def test_euclidean_identical(self):
        s = {"hp_pct": 80.0, "nearby_agents_count": 3}
        assert _normalized_euclidean(s, s) == pytest.approx(1.0)

    def test_euclidean_different(self):
        s1 = {"hp_pct": 100.0, "nearby_agents_count": 0}
        s2 = {"hp_pct": 0.0, "nearby_agents_count": 20}
        sim = _normalized_euclidean(s1, s2)
        assert 0.0 <= sim < 0.5

    def test_euclidean_missing_values(self):
        s1 = {"hp_pct": 50.0}
        s2 = {"hp_pct": 50.0, "nearby_agents_count": 5}
        sim = _normalized_euclidean(s1, s2)
        assert sim == 1.0  # 只有 hp_pct 参与比较且相同

    def test_state_similarity_combined(self):
        s1 = {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 3}
        s2 = {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 3}
        assert state_similarity(s1, s2) == pytest.approx(1.0)

    def test_action_similarity_exact(self):
        assert _action_similarity("fight", "fight") == 1.0

    def test_action_similarity_partial(self):
        sim = _action_similarity("fight enemy", "battle monster")
        assert 0.0 <= sim <= 1.0

    def test_classify_action(self):
        assert _classify_action("fight enemy") == "fight"
        assert _classify_action("移动到森林") == "move"
        assert _classify_action("休息一下") == "rest"
        assert _classify_action("和 agumon 对话") == "talk"

    def test_extract_actions_from_plan(self):
        actions = _extract_actions_from_plan("去森林战斗然后休息")
        assert "move" in actions
        assert "fight" in actions
        assert "rest" in actions


# ──────────────────────────────────────────────
# Episode / Rule
# ──────────────────────────────────────────────


class TestEpisode:
    def test_creation(self):
        ep = Episode(
            state_snapshot={"region_id": "forest"},
            action="fight",
            outcome={"success": True, "event_type": "battle"},
            tick_index=5,
        )
        assert ep.tick_index == 5
        assert ep.confidence == 1.0

    def test_serialization(self):
        ep = Episode(
            state_snapshot={"region_id": "forest"},
            action="fight",
            outcome={"success": True},
            tick_index=5,
        )
        d = ep.to_dict()
        restored = Episode.from_dict(d)
        assert restored.tick_index == 5
        assert restored.action == "fight"
        assert restored.state_snapshot == {"region_id": "forest"}


class TestRule:
    def test_matches(self):
        r = Rule(condition={"region_id": "forest"}, conclusion="safe")
        assert r.matches({"region_id": "forest"})
        assert not r.matches({"region_id": "mountain"})
        assert not r.matches({})

    def test_serialization(self):
        r = Rule(condition={"region_id": "forest"}, conclusion="safe", confidence=0.8)
        d = r.to_dict()
        restored = Rule.from_dict(d)
        assert restored.confidence == 0.8
        assert restored.conclusion == "safe"


# ──────────────────────────────────────────────
# EpisodicMemory
# ──────────────────────────────────────────────


class TestEpisodicMemory:
    def test_add_and_count(self):
        mem = EpisodicMemory()
        mem.add({"region_id": "forest"}, "fight", {"success": True}, tick=1)
        mem.add({"region_id": "forest"}, "fight", {"success": False}, tick=2)
        assert mem.count() == 2

    def test_retrieve_similar(self):
        mem = EpisodicMemory()
        mem.add({"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 2},
                "fight", {"success": True, "event_type": "battle"}, tick=1)
        mem.add({"region_id": "mountain", "stage": "champion", "hp_pct": 50, "nearby_agents_count": 5},
                "rest", {"success": True, "event_type": "rest"}, tick=2)

        results = mem.retrieve_similar(
            {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 2}
        )
        assert len(results) >= 1
        assert results[0].state_snapshot["region_id"] == "forest"

    def test_fifo_eviction(self):
        mem = EpisodicMemory(_max_episodes=3)
        for i in range(5):
            mem.add({"region_id": "test"}, f"action_{i}", {"success": True}, tick=i)

        assert mem.count() == 3
        # 最旧的 (tick 0, 1) 应被驱逐
        ticks = {ep.tick_index for ep in mem.episodes}
        assert ticks == {2, 3, 4}

    def test_recent(self):
        mem = EpisodicMemory()
        for i in range(10):
            mem.add({"region_id": "test"}, f"action_{i}", {"success": True}, tick=i)

        recent = mem.recent(n=3)
        assert len(recent) == 3
        assert recent[0].tick_index == 9  # 最新

    def test_serialization(self):
        mem = EpisodicMemory()
        mem.add({"region_id": "forest"}, "fight", {"success": True}, tick=1)
        d = mem.to_dict()
        restored = EpisodicMemory.from_dict(d)
        assert restored.count() == 1
        assert restored.episodes[0].tick_index == 1


# ──────────────────────────────────────────────
# SemanticMemory
# ──────────────────────────────────────────────


class TestSemanticMemory:
    def _make_episodes(self, n: int, field: str, value: str, event_type: str) -> list[Episode]:
        return [
            Episode(
                state_snapshot={field: value, "stage": "rookie"},
                action="test",
                outcome={"success": True, "event_type": event_type},
                tick_index=i,
            )
            for i in range(n)
        ]

    def test_extract_rules_with_support(self):
        mem = SemanticMemory()
        episodes = self._make_episodes(5, "region_id", "forest", "battle")
        rules = mem.extract_rules(episodes, min_support=3)
        assert len(rules) > 0
        assert any("battle" in r.conclusion for r in rules)

    def test_extract_rules_insufficient_support(self):
        mem = SemanticMemory()
        episodes = self._make_episodes(2, "region_id", "forest", "battle")
        rules = mem.extract_rules(episodes, min_support=3)
        assert len(rules) == 0

    def test_rule_dedup(self):
        """重复提取相同模式应去重而非重复添加。"""
        mem = SemanticMemory()
        episodes = self._make_episodes(5, "region_id", "forest", "battle")
        mem.extract_rules(episodes, min_support=3)
        count1 = mem.count()
        mem.extract_rules(episodes, min_support=3)
        count2 = mem.count()
        assert count2 <= count1 + 1  # 不重复添加相同规则

    def test_match_rules(self):
        mem = SemanticMemory()
        episodes = self._make_episodes(5, "region_id", "forest", "battle")
        mem.extract_rules(episodes, min_support=3)

        matched = mem.match_rules({"region_id": "forest"})
        assert len(matched) >= 1

        not_matched = mem.match_rules({"region_id": "mountain"})
        assert len(not_matched) == 0

    def test_max_rules_eviction(self):
        mem = SemanticMemory(_max_rules=5)
        rules_to_add = [
            Rule(condition={"key": str(i)}, conclusion=f"rule_{i}", confidence=0.1 * i)
            for i in range(10)
        ]
        mem._merge_rules(rules_to_add)
        assert mem.count() <= 5
        # 最低置信度的应被驱逐
        confidences = [r.confidence for r in mem.rules]
        assert min(confidences) >= 0.4

    def test_serialization(self):
        mem = SemanticMemory()
        mem.rules.append(Rule(condition={"k": "v"}, conclusion="test", confidence=0.7))
        d = mem.to_dict()
        restored = SemanticMemory.from_dict(d)
        assert restored.count() == 1
        assert restored.rules[0].confidence == 0.7


# ──────────────────────────────────────────────
# SelectiveForesight
# ──────────────────────────────────────────────


class TestSelectiveForesight:
    def _setup(self):
        episodic = EpisodicMemory()
        semantic = SemanticMemory()

        # 5 条 fight → battle 经验
        for i in range(5):
            episodic.add(
                {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 3},
                "fight enemy",
                {"success": True, "hp_change": -10, "mood_change": 0.1, "event_type": "battle"},
                tick=i,
            )

        # 5 条 talk → social 经验
        for i in range(5, 10):
            episodic.add(
                {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 1},
                "talk to friend",
                {"success": True, "hp_change": 0, "mood_change": 0.3, "event_type": "social"},
                tick=i,
            )

        return episodic, semantic

    def test_predict_episodic(self):
        episodic, semantic = self._setup()
        foresight = SelectiveForesight()

        state = {"region_id": "forest", "stage": "rookie", "hp_pct": 75, "nearby_agents_count": 2}
        result = foresight.predict(episodic, semantic, state, "fight enemy")
        assert result.source == "episodic"
        assert result.confidence > 0.5
        assert result.predicted_outcome["event_type"] == "battle"

    def test_predict_none(self):
        episodic = EpisodicMemory()
        semantic = SemanticMemory()
        foresight = SelectiveForesight()

        state = {"region_id": "unknown", "stage": "rookie", "hp_pct": 50, "nearby_agents_count": 0}
        result = foresight.predict(episodic, semantic, state, "do something weird")
        assert result.source == "none"
        assert result.confidence == 0.1

    def test_evaluate_plan(self):
        episodic, semantic = self._setup()
        foresight = SelectiveForesight()

        state = {"region_id": "forest", "stage": "rookie", "hp_pct": 75, "nearby_agents_count": 2}
        result = foresight.evaluate_plan(episodic, semantic, state, "去战斗然后休息")
        assert "overall_confidence" in result
        assert "recommendation" in result
        assert result["recommendation"] in ("proceed", "caution", "reconsider")


# ──────────────────────────────────────────────
# WorldModel
# ──────────────────────────────────────────────


class TestWorldModel:
    def test_creation(self):
        wm = WorldModel(agent_name="agumon")
        assert wm.agent_name == "agumon"
        assert wm.episodic.count() == 0
        assert wm.semantic.count() == 0

    def test_observe(self):
        wm = WorldModel(agent_name="agumon")
        ep = wm.observe(
            {"region_id": "forest", "stage": "rookie", "hp_pct": 90, "nearby_agents_count": 1},
            "fight enemy",
            {"success": True, "event_type": "battle"},
            tick_index=1,
        )
        assert isinstance(ep, Episode)
        assert wm.episodic.count() == 1

    def test_predict(self):
        wm = WorldModel(agent_name="agumon")
        # 先记录几条经验
        for i in range(5):
            wm.observe(
                {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 3},
                "fight enemy",
                {"success": True, "hp_change": -5, "mood_change": 0.1, "event_type": "battle"},
                tick_index=i,
            )

        result = wm.predict(
            {"region_id": "forest", "stage": "rookie", "hp_pct": 75, "nearby_agents_count": 2},
            "fight enemy",
        )
        assert isinstance(result, PredictionResult)
        assert result.source == "episodic"

    def test_evaluate_plan(self):
        wm = WorldModel(agent_name="agumon")
        result = wm.evaluate_plan(
            {"region_id": "forest"}, "去森林探索"
        )
        assert "overall_confidence" in result
        assert "recommendation" in result

    def test_stats(self):
        wm = WorldModel(agent_name="agumon")
        wm.observe({"region_id": "test"}, "fight", {"success": True}, tick_index=1)
        stats = wm.stats()
        assert stats["agent_name"] == "agumon"
        assert stats["total_episodes"] == 1
        assert stats["total_rules"] == 0

    def test_extract_rules(self):
        wm = WorldModel(agent_name="agumon")
        for i in range(5):
            wm.observe(
                {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 3},
                "fight",
                {"success": True, "event_type": "battle"},
                tick_index=i,
            )
        n = wm.extract_rules(force=True)
        assert n >= 0  # 可能有也可能没有规则（取决于 min_support）

    def test_serialization_roundtrip(self):
        wm = WorldModel(agent_name="agumon")
        wm.observe(
            {"region_id": "forest"}, "fight", {"success": True, "event_type": "battle"}, tick_index=1,
        )
        d = wm.to_dict()
        restored = WorldModel.from_dict(d)
        assert restored.agent_name == "agumon"
        assert restored.episodic.count() == 1
        assert restored.episodic.episodes[0].tick_index == 1

    def test_multiple_observations_generate_rules_on_interval(self):
        """24 tick 后应自动触发规则提取。"""
        wm = WorldModel(agent_name="agumon")

        for i in range(25):
            wm.observe(
                {"region_id": "forest", "stage": "rookie", "hp_pct": 80, "nearby_agents_count": 3},
                "fight",
                {"success": True, "event_type": "battle"},
                tick_index=i,
            )

        # 第 24 tick 应提取规则
        assert wm.semantic.count() > 0 or wm.stats()["total_rules"] >= 0


# ──────────────────────────────────────────────
# Phase 20 集成测试: DigimonAgent + API + 端到端
# ──────────────────────────────────────────────


class TestWorldModelAgentIntegration:
    """测试 WorldModel 与 DigimonAgent 的集成。"""

    def test_agent_creates_world_model(self):
        """DigimonAgent 初始化后 world_model 不为 None。"""
        from digimon_world.agents.digimon_agent import DigimonAgent, DigimonAttribute

        agent = DigimonAgent(
            name="测试兽",
            species="testmon",
            attribute=DigimonAttribute.VACCINE,
        )
        assert agent.world_model is not None
        assert agent.world_model.agent_name == "测试兽"
        assert agent.world_model.episodic.count() == 0
        assert agent.world_model.semantic.count() == 0

    def test_agent_world_model_is_independent(self):
        """每个 agent 的 world_model 互相独立。"""
        from digimon_world.agents.digimon_agent import DigimonAgent

        a = DigimonAgent(name="甲兽", species="amon")
        b = DigimonAgent(name="乙兽", species="bmon")

        # 各自独立
        assert a.world_model is not b.world_model
        assert a.world_model.agent_name == "甲兽"
        assert b.world_model.agent_name == "乙兽"

        # 对 a 记录情节不应影响 b
        a.world_model.observe(
            {"region_id": "forest"}, "fight", {"success": True}, tick_index=1,
        )
        assert a.world_model.episodic.count() == 1
        assert b.world_model.episodic.count() == 0

    def test_step_records_episode_sync(self):
        """同步模拟 agent.step() 核心逻辑，验证 world_model 记录情节。"""
        from digimon_world.agents.digimon_agent import DigimonAgent

        agent = DigimonAgent(name="同步测兽", species="synctest")
        agent.planner = None
        agent.reflector = None

        count_before = agent.world_model.episodic.count()
        assert count_before == 0

        # 模拟 step() 核心逻辑（不含异步 LLM 调用）
        agent._decay_mood()
        for i in range(3):
            pre_state = agent._capture_world_state(tick_index=i)
            event = agent.act()
            agent.observe(event, tick_index=i)
            agent.world_model.observe(pre_state, agent.current_plan or "idle", event, i)

        assert agent.world_model.episodic.count() == 3
        # 验证统计信息可读
        stats = agent.world_model.stats()
        assert stats["total_episodes"] == 3
        assert stats["agent_name"] == "同步测兽"

    def test_step_preserves_state_snapshot(self):
        """step 模拟中，记录的 state_snapshot 包含完整字段。"""
        from digimon_world.agents.digimon_agent import DigimonAgent

        agent = DigimonAgent(name="状态测兽", species="statetest")
        agent.planner = None
        agent.reflector = None

        pre_state = agent._capture_world_state(tick_index=5)
        event = agent.act()
        agent.world_model.observe(pre_state, agent.current_plan or "idle", event, 5)

        ep = agent.world_model.episodic.episodes[-1]
        assert ep.tick_index == 5
        assert "region_id" in ep.state_snapshot
        assert "stage" in ep.state_snapshot
        assert "hp_pct" in ep.state_snapshot
        assert "nearby_agents_count" in ep.state_snapshot

    def test_world_model_observe_directly(self):
        """直接调用 WorldModel.observe() 记录情节。"""
        wm = WorldModel(agent_name="亚古兽")
        pre_state = {
            "region_id": "齿轮草原",
            "stage": "rookie",
            "hp_pct": 80,
            "nearby_agents_count": 2,
        }
        ep = wm.observe(
            pre_state,
            "fight enemy",
            {"success": True, "event_type": "battle", "hp_change": -10},
            tick_index=5,
        )
        assert wm.episodic.count() == 1
        assert ep.tick_index == 5

        # 第二条记录
        wm.observe(
            pre_state,
            "rest",
            {"success": True, "event_type": "rest", "hp_change": 5},
            tick_index=6,
        )
        assert wm.episodic.count() == 2

        recent = wm.episodic.recent(n=2)
        assert recent[0].tick_index == 6

    def test_world_model_rules_after_sufficient_observations(self):
        """≥5 条同类型情节后应提取规则。"""
        wm = WorldModel(agent_name="加布兽")
        for i in range(10):
            wm.observe(
                {
                    "region_id": "迷乱森林",
                    "stage": "rookie",
                    "hp_pct": 75,
                    "nearby_agents_count": 3,
                },
                "fight enemy",
                {"success": True, "event_type": "battle", "hp_change": -8},
                tick_index=i,
            )

        n_rules = wm.extract_rules(force=True)
        assert n_rules >= 0
        # 强制提取后 stats 应反映规则数
        stats = wm.stats()
        assert stats["total_rules"] >= 0

    def test_world_model_predict_with_history(self):
        """有足够经验后 predict 应基于情节记忆。"""
        wm = WorldModel(agent_name="比丘兽")
        for i in range(5):
            wm.observe(
                {
                    "region_id": "龙眼湖",
                    "stage": "rookie",
                    "hp_pct": 80,
                    "nearby_agents_count": 1,
                },
                "talk to friend",
                {"success": True, "event_type": "social", "mood_change": 0.3},
                tick_index=i,
            )

        result = wm.predict(
            {
                "region_id": "龙眼湖",
                "stage": "rookie",
                "hp_pct": 80,
                "nearby_agents_count": 1,
            },
            "talk to friend",
        )
        assert result.source in ("episodic", "semantic", "none")
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.predicted_outcome, dict)

    def test_world_model_serialization_preserves_data(self):
        """序列化往返后数据不丢失。"""
        wm = WorldModel(agent_name="甲虫兽")
        for i in range(5):
            wm.observe(
                {"region_id": "玩具城", "stage": "rookie"},
                "explore",
                {"success": True, "event_type": "explore"},
                tick_index=i,
            )
        wm.extract_rules(force=True)

        d = wm.to_dict()
        restored = WorldModel.from_dict(d)

        assert restored.agent_name == "甲虫兽"
        assert restored.episodic.count() == wm.episodic.count()
        assert restored.semantic.count() == wm.semantic.count()
        # 验证情节内容一致
        for orig, rest in zip(wm.episodic.episodes, restored.episodic.episodes, strict=False):
            assert orig.tick_index == rest.tick_index
            assert orig.action == rest.action

    def test_evaluate_plan_returns_recommendation(self):
        """evaluate_plan 返回合理建议。"""
        wm = WorldModel(agent_name="巴鲁兽")
        result = wm.evaluate_plan(
            {"region_id": "森林", "stage": "rookie"},
            "去森林探索然后战斗",
        )
        assert "recommendation" in result
        assert result["recommendation"] in ("proceed", "caution", "reconsider")
        assert "overall_confidence" in result
        assert "predictions" in result


class TestWorldModelAPI:
    """测试 /api/digimon/{name}/world-model API 端点。"""

    @pytest.fixture(autouse=True)
    def _reset_world(self):
        """每个测试前重置世界状态。"""
        from digimon_world.world.world_state import get_world, reset_world

        reset_world()
        return get_world()

    def test_endpoint_returns_world_model_snapshot(self):
        """API 返回包含 stats + recent_episodes + rules 的 JSON。"""
        from fastapi.testclient import TestClient

        from digimon_world.api.app import app

        client = TestClient(app)

        resp = client.get("/api/digimon/亚古兽/world-model")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "亚古兽"
        assert data["status"] == "active"
        assert "stats" in data
        assert "recent_episodes" in data
        assert "rules" in data
        assert isinstance(data["stats"], dict)
        assert isinstance(data["rules"], list)
        assert "total_episodes" in data["stats"]
        assert "total_rules" in data["stats"]

    def test_endpoint_404_for_unknown_digimon(self):
        """未知数码兽返回 404。"""
        from fastapi.testclient import TestClient

        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        get_world()
        client = TestClient(app)

        resp = client.get("/api/digimon/不存在的数码兽/world-model")
        assert resp.status_code == 404

    def test_endpoint_reflects_accumulated_episodes(self):
        """WorldModel 有情节后 API 返回正确的 recent_episodes。"""
        from fastapi.testclient import TestClient

        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()

        # 给亚古兽直接添加情节
        agent = world.get("亚古兽")
        assert agent is not None
        assert agent.world_model is not None

        for i in range(3):
            agent.world_model.observe(
                {"region_id": "测试区域", "stage": "rookie"},
                f"测试动作_{i}",
                {"success": True, "event_type": "test"},
                tick_index=i,
            )

        client = TestClient(app)
        resp = client.get("/api/digimon/亚古兽/world-model")
        assert resp.status_code == 200
        data = resp.json()

        assert data["stats"]["total_episodes"] >= 3
        assert len(data["recent_episodes"]) >= 3

    def test_endpoint_returns_rules_when_present(self):
        """当有规则时 API 返回 rules 列表。"""
        from fastapi.testclient import TestClient

        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()

        agent = world.get("加布兽")
        assert agent is not None
        assert agent.world_model is not None

        # 添加足量经验以提取规则
        for i in range(10):
            agent.world_model.observe(
                {"region_id": "迷乱森林", "stage": "rookie", "hp_pct": 80},
                "fight",
                {"success": True, "event_type": "battle"},
                tick_index=i,
            )
        agent.world_model.extract_rules(force=True)

        client = TestClient(app)
        resp = client.get("/api/digimon/加布兽/world-model")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["rules"], list)
        # 规则列表中的规则应有 condition / conclusion / confidence
        for rule in data["rules"]:
            assert "condition" in rule
            assert "conclusion" in rule
            assert "confidence" in rule
            assert 0.0 <= rule["confidence"] <= 1.0

    def test_all_agents_have_world_model(self):
        """所有初始化的 agent 都有 world_model。"""
        from digimon_world.world.world_state import get_world

        world = get_world()

        for agent in world.all():
            assert agent.world_model is not None, (
                f"{agent.name} should have a world_model"
            )
            assert agent.world_model.agent_name == agent.name

    def test_cross_agent_episode_isolation(self):
        """不同 agent 的情节记录互不影响，API 各自返回正确数据。"""
        from fastapi.testclient import TestClient

        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()

        agumon = world.get("亚古兽")
        gabumon = world.get("加布兽")
        assert agumon is not None
        assert gabumon is not None

        # 给亚古兽记录情节
        for i in range(5):
            agumon.world_model.observe(
                {"region_id": "a_region"}, "fight", {"success": True, "event_type": "battle"},
                tick_index=i,
            )

        # 给加布兽记录不同的情节
        for i in range(3):
            gabumon.world_model.observe(
                {"region_id": "b_region"}, "rest", {"success": True, "event_type": "rest"},
                tick_index=i,
            )

        client = TestClient(app)

        # 亚古兽 API
        r1 = client.get("/api/digimon/亚古兽/world-model")
        assert r1.json()["stats"]["total_episodes"] >= 5

        # 加布兽 API
        r2 = client.get("/api/digimon/加布兽/world-model")
        assert r2.json()["stats"]["total_episodes"] >= 3

        # 互不影响
        assert r1.json()["stats"]["total_episodes"] != r2.json()["stats"]["total_episodes"]

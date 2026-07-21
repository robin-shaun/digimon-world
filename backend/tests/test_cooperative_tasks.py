"""
协作任务系统测试 — Phase 31
===========================

覆盖 CooperativeTask / CooperativeTaskRegistry / TaskGenerationEngine / API 端点。

测试范围:
- CooperativeTask 数据类 (创建/序列化/计算)
- CooperativeTaskRegistry (CRUD + 查询 + 贡献度 + 完成检查)
- TaskGenerationEngine (随机生成 / 扫描 / 候选选择)
- API 端点 (列表/详情/生成/贡献)
- 全局单例
- 边界情况
"""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from digimon_world.api import app
from digimon_world.world import reset_world
from digimon_world.world.cooperative_tasks import (
    DEFAULT_COMPLETION_THRESHOLD,
    TASK_TYPES,
    CooperativeTask,
    CooperativeTaskRegistry,
    TaskGenerationEngine,
    get_cooperative_registry,
    reset_cooperative_registry,
)

# ──────────────────────────────────────────────
# 夹具
# ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset() -> None:
    """每个测试前后重置全局状态。"""
    reset_cooperative_registry()
    reset_world()
    random.seed(42)
    yield
    reset_cooperative_registry()
    reset_world()


@pytest.fixture
def registry() -> CooperativeTaskRegistry:
    """创建独立的注册表实例。"""
    return CooperativeTaskRegistry()


@pytest.fixture
def client() -> TestClient:
    """FastAPI 测试客户端。"""
    return TestClient(app)


# ──────────────────────────────────────────────
# CooperativeTask 数据类测试 (≥3 个)
# ──────────────────────────────────────────────


class TestCooperativeTask:
    """CooperativeTask 数据类测试。"""

    def test_create_task(self) -> None:
        """创建基本协作任务。"""
        task = CooperativeTask(
            task_id="coop_explore_0001",
            task_type="explore",
            title="探索秘境",
            description="探索未知区域",
            required_participants=3,
            region_id="file_island",
            position={"x": 100, "y": 200},
        )
        assert task.task_id == "coop_explore_0001"
        assert task.task_type == "explore"
        assert task.title == "探索秘境"
        assert task.description == "探索未知区域"
        assert task.required_participants == 3
        assert task.current_participants == []
        assert task.sub_goals == {}
        assert task.shared_reward == 0.3
        assert task.individual_contributions == {}
        assert task.status == "pending"
        assert task.tick_created == 0
        assert task.tick_completed is None
        assert task.region_id == "file_island"
        assert task.position == {"x": 100, "y": 200}
        assert task.completion_threshold == DEFAULT_COMPLETION_THRESHOLD

    def test_total_contribution(self) -> None:
        """计算总贡献度。"""
        task = CooperativeTask(
            task_id="coop_test_0001",
            task_type="build",
            title="test",
            description="test",
            required_participants=2,
            individual_contributions={"agumon": 0.3, "gabumon": 0.5},
        )
        assert task.total_contribution() == 0.8

    def test_total_contribution_empty(self) -> None:
        """空贡献度。"""
        task = CooperativeTask(
            task_id="coop_test_0002",
            task_type="build",
            title="test",
            description="test",
            required_participants=2,
        )
        assert task.total_contribution() == 0.0

    def test_is_fully_staffed(self) -> None:
        """检查人数是否达标。"""
        task = CooperativeTask(
            task_id="coop_test_0003",
            task_type="hunt",
            title="test",
            description="test",
            required_participants=2,
            current_participants=["agumon", "gabumon"],
        )
        assert task.is_fully_staffed() is True

    def test_is_not_fully_staffed(self) -> None:
        """人数不足。"""
        task = CooperativeTask(
            task_id="coop_test_0004",
            task_type="hunt",
            title="test",
            description="test",
            required_participants=3,
            current_participants=["agumon"],
        )
        assert task.is_fully_staffed() is False

    def test_to_dict(self) -> None:
        """序列化测试。"""
        task = CooperativeTask(
            task_id="coop_defend_0001",
            task_type="defend",
            title="保卫边境",
            description="击退入侵者",
            required_participants=2,
            current_participants=["agumon"],
            individual_contributions={"agumon": 0.2},
            region_id="server_continent",
            position={"x": 500, "y": 300},
        )
        d = task.to_dict()
        assert d["task_id"] == "coop_defend_0001"
        assert d["task_type"] == "defend"
        assert d["current_participants"] == ["agumon"]
        assert d["individual_contributions"] == {"agumon": 0.2}
        assert d["total_contribution"] == 0.2
        assert d["participant_count"] == 1

    def test_task_types_valid(self) -> None:
        """所有任务类型都可创建。"""
        for task_type in TASK_TYPES:
            task = CooperativeTask(
                task_id=f"coop_{task_type}_test",
                task_type=task_type,
                title="test",
                description="test",
                required_participants=2,
            )
            assert task.task_type == task_type


# ──────────────────────────────────────────────
# 加入和贡献度测试 (≥3 个)
# ──────────────────────────────────────────────


class TestJoinAndContribute:
    """加入任务和贡献度测试。"""

    def test_join_task(self, registry: CooperativeTaskRegistry) -> None:
        """加入任务成功。"""
        task = registry.create_task("explore", "探索", "描述", 3, "file_island")
        assert registry.join_task(task.task_id, "agumon") is True
        assert "agumon" in task.current_participants
        assert task.individual_contributions["agumon"] == 0.0

    def test_join_nonexistent_task(self, registry: CooperativeTaskRegistry) -> None:
        """加入不存在的任务。"""
        assert registry.join_task("nonexistent", "agumon") is False

    def test_join_duplicate_agent(self, registry: CooperativeTaskRegistry) -> None:
        """重复加入同一任务。"""
        task = registry.create_task("hunt", "狩猎", "描述", 2, "spiral_mountain")
        assert registry.join_task(task.task_id, "agumon") is True
        assert registry.join_task(task.task_id, "agumon") is False

    def test_auto_activate_on_full(self, registry: CooperativeTaskRegistry) -> None:
        """人数达标后自动激活。"""
        task = registry.create_task("defend", "防御", "描述", 2, "server_continent")
        assert task.status == "pending"
        registry.join_task(task.task_id, "agumon")
        assert task.status == "pending"
        registry.join_task(task.task_id, "gabumon")
        assert task.status == "active"

    def test_contribute(self, registry: CooperativeTaskRegistry) -> None:
        """提交贡献。"""
        task = registry.create_task("build", "建造", "描述", 2, "village_of_beginnings")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")  # 激活
        assert registry.contribute(task.task_id, "agumon", 0.5) is True
        assert task.individual_contributions["agumon"] == 0.5

    def test_contribute_non_participant(self, registry: CooperativeTaskRegistry) -> None:
        """非参与者贡献失败。"""
        task = registry.create_task("explore", "探索", "描述", 2, "infinity_mountain")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        assert registry.contribute(task.task_id, "stranger", 0.5) is False

    def test_contribute_negative_amount(self, registry: CooperativeTaskRegistry) -> None:
        """负数贡献失败。"""
        task = registry.create_task("hunt", "狩猎", "描述", 2, "endless_ocean")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        assert registry.contribute(task.task_id, "agumon", -0.1) is False


# ──────────────────────────────────────────────
# 完成检查测试 (≥3 个)
# ──────────────────────────────────────────────


class TestCompletionCheck:
    """任务完成检查测试。"""

    def test_completion_not_reached(self, registry: CooperativeTaskRegistry) -> None:
        """未达到阈值。"""
        task = registry.create_task("explore", "探索", "描述", 2, "file_island")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        registry.contribute(task.task_id, "agumon", 0.2)
        result = registry.check_completion(task.task_id)
        assert result["completed"] is False
        assert result["total_contribution"] == 0.2

    def test_completion_reached(self, registry: CooperativeTaskRegistry) -> None:
        """达到阈值完成。"""
        task = registry.create_task("build", "建造", "描述", 2, "village_of_beginnings")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        registry.contribute(task.task_id, "agumon", 0.6)
        registry.contribute(task.task_id, "gabumon", 0.5)
        result = registry.check_completion(task.task_id)
        assert result["completed"] is True
        assert task.status == "completed"
        assert "rewards" in result
        assert "agumon" in result["rewards"]
        assert "gabumon" in result["rewards"]

    def test_completion_rewards_sum(self, registry: CooperativeTaskRegistry) -> None:
        """奖励总和应合理。"""
        task = registry.create_task("defend", "防御", "描述", 2, "server_continent")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        registry.contribute(task.task_id, "agumon", 0.5)
        registry.contribute(task.task_id, "gabumon", 0.5)
        result = registry.check_completion(task.task_id)
        assert result["completed"] is True
        rewards = result["rewards"]
        total_reward = sum(rewards.values())
        # 每人保底 0.7 + 共享 0.15 = 0.85; 总计 1.7
        assert total_reward > 1.0

    def test_reward_equal_contributions(self, registry: CooperativeTaskRegistry) -> None:
        """等量贡献应获得相近奖励。"""
        task = registry.create_task("hunt", "狩猎", "描述", 2, "spiral_mountain")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        registry.contribute(task.task_id, "agumon", 0.5)
        registry.contribute(task.task_id, "gabumon", 0.5)
        result = registry.check_completion(task.task_id)
        assert result["completed"] is True
        # 等量贡献 → 奖励相等
        assert abs(result["rewards"]["agumon"] - result["rewards"]["gabumon"]) < 0.01

    def test_completion_nonexistent_task(self, registry: CooperativeTaskRegistry) -> None:
        """检查不存在的任务。"""
        result = registry.check_completion("nonexistent")
        assert result["completed"] is False
        assert "不存在" in result["message"]


# ──────────────────────────────────────────────
# 子目标分配测试
# ──────────────────────────────────────────────


class TestSubGoals:
    """子目标分配测试。"""

    def test_assign_sub_goals(self, registry: CooperativeTaskRegistry) -> None:
        """分配子目标。"""
        task = registry.create_task("explore", "探索", "描述", 3, "file_island")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        registry.join_task(task.task_id, "piyomon")
        goals = registry.assign_sub_goals(task.task_id)
        assert len(goals) == 3
        assert "agumon" in goals
        assert "gabumon" in goals
        assert "piyomon" in goals
        for g in goals.values():
            assert len(g) > 0

    def test_assign_sub_goals_different_types(self, registry: CooperativeTaskRegistry) -> None:
        """不同任务类型有不同子目标。"""
        explore_task = registry.create_task("explore", "探索", "描述", 2, "file_island")
        defend_task = registry.create_task("defend", "防御", "描述", 2, "server_continent")
        registry.join_task(explore_task.task_id, "agumon")
        registry.join_task(explore_task.task_id, "gabumon")
        registry.join_task(defend_task.task_id, "piyomon")
        registry.join_task(defend_task.task_id, "tentomon")
        explore_goals = set(registry.assign_sub_goals(explore_task.task_id).values())
        defend_goals = set(registry.assign_sub_goals(defend_task.task_id).values())
        assert explore_goals != defend_goals


# ──────────────────────────────────────────────
# 注册表查询测试 (≥2 个)
# ──────────────────────────────────────────────


class TestRegistryList:
    """注册表查询测试。"""

    def test_get_active_tasks(self, registry: CooperativeTaskRegistry) -> None:
        """获取活跃任务。"""
        t1 = registry.create_task("explore", "探索A", "desc", 2, "file_island")
        t2 = registry.create_task("defend", "防御B", "desc", 2, "server_continent")
        t3 = registry.create_task("build", "建造C", "desc", 2, "village_of_beginnings")
        # t3 设为完成
        registry.join_task(t3.task_id, "agumon")
        registry.join_task(t3.task_id, "gabumon")
        registry.contribute(t3.task_id, "agumon", 1.0)
        registry.check_completion(t3.task_id)
        active = registry.get_active_tasks()
        assert len(active) == 2
        task_ids = {t.task_id for t in active}
        assert t1.task_id in task_ids
        assert t2.task_id in task_ids

    def test_get_tasks_by_region(self, registry: CooperativeTaskRegistry) -> None:
        """按区域查询。"""
        registry.create_task("explore", "探索A", "desc", 2, "file_island")
        registry.create_task("explore", "探索B", "desc", 2, "file_island")
        registry.create_task("defend", "防御C", "desc", 2, "server_continent")
        file_tasks = registry.get_tasks_by_region("file_island")
        assert len(file_tasks) == 2
        server_tasks = registry.get_tasks_by_region("server_continent")
        assert len(server_tasks) == 1

    def test_get_agent_tasks(self, registry: CooperativeTaskRegistry) -> None:
        """按参与者查询。"""
        t1 = registry.create_task("hunt", "狩猎A", "desc", 2, "spiral_mountain")
        t2 = registry.create_task("hunt", "狩猎B", "desc", 2, "endless_ocean")
        registry.join_task(t1.task_id, "agumon")
        registry.join_task(t2.task_id, "agumon")
        agent_tasks = registry.get_agent_tasks("agumon")
        assert len(agent_tasks) == 2

    def test_create_task_invalid_type(self, registry: CooperativeTaskRegistry) -> None:
        """无效任务类型。"""
        with pytest.raises(ValueError):
            registry.create_task("invalid", "标题", "描述", 2, "file_island")

    def test_create_task_insufficient_participants(self, registry: CooperativeTaskRegistry) -> None:
        """participants 不足 2。"""
        with pytest.raises(ValueError):
            registry.create_task("explore", "标题", "描述", 1, "file_island")


# ──────────────────────────────────────────────
# 任务生成引擎测试 (≥3 个)
# ──────────────────────────────────────────────


class TestGenerationEngine:
    """TaskGenerationEngine 测试。"""

    def test_generate_with_few_agents(self) -> None:
        """数码兽不足时返回 None。"""
        from digimon_world.world.world_state import get_world

        engine = TaskGenerationEngine()
        world = get_world()
        agents = world.all()[:1]  # 只取 1 只
        result = engine.generate_random_task(world, agents, 100)
        assert result is None

    def test_generate_random_task(self) -> None:
        """基本随机生成。"""
        from digimon_world.world.world_state import get_world

        engine = TaskGenerationEngine()
        world = get_world()
        agents = world.all()
        # 确保有至少 2 只
        if len(agents) < 2:
            pytest.skip("数码兽数量不足")
        result = engine.generate_random_task(world, agents, 100)
        # 可能成功也可能失败（取决于 proximity）
        if result is not None:
            assert result.task_type in TASK_TYPES
            assert result.required_participants >= 2
            assert len(result.current_participants) >= 2
            assert result.status == "active"
            assert result.tick_created == 100
            assert result.region_id != ""
            assert len(result.sub_goals) > 0

    def test_scan_for_opportunities(self) -> None:
        """扫描机会。"""
        from digimon_world.world.world_state import get_world

        engine = TaskGenerationEngine()
        world = get_world()
        agents = world.all()
        if len(agents) < 2:
            pytest.skip("数码兽数量不足")
        tasks = engine.scan_for_opportunities(world, agents, 200)
        # 可能返回 0-3 个任务
        assert len(tasks) <= 3
        for task in tasks:
            assert task.task_type in TASK_TYPES
            assert len(task.current_participants) >= 2

    def test_select_candidates(self) -> None:
        """候选选择测试。"""
        engine = TaskGenerationEngine()

        class MockAgent:
            def __init__(self, name: str, x: int, y: int) -> None:
                self.name = name
                self.location = (x, y)

        agents = [
            MockAgent("near1", 100, 100),
            MockAgent("near2", 120, 110),
            MockAgent("far1", 900, 900),
            MockAgent("far2", 950, 950),
        ]
        candidates = engine._select_candidates(agents, 100, 100, max_distance=200)
        assert "near1" in candidates
        assert "near2" in candidates
        assert "far1" not in candidates
        assert "far2" not in candidates

    def test_generate_has_sub_goals(self) -> None:
        """生成的任务应有子目标。"""
        from digimon_world.world.world_state import get_world

        engine = TaskGenerationEngine()
        world = get_world()
        agents = world.all()
        if len(agents) < 2:
            pytest.skip("数码兽数量不足")
        result = engine.generate_random_task(world, agents, 300)
        if result is not None:
            assert len(result.sub_goals) == len(result.current_participants)
            for p in result.current_participants:
                assert p in result.sub_goals


# ──────────────────────────────────────────────
# 全局单例测试
# ──────────────────────────────────────────────


class TestGlobalSingleton:
    """全局单例测试。"""

    def test_get_returns_same_instance(self) -> None:
        r1 = get_cooperative_registry()
        r2 = get_cooperative_registry()
        assert r1 is r2

    def test_reset_creates_new_instance(self) -> None:
        r1 = get_cooperative_registry()
        reset_cooperative_registry()
        r2 = get_cooperative_registry()
        assert r1 is not r2

    def test_reset_clears_data(self) -> None:
        r = get_cooperative_registry()
        r.create_task("explore", "探索", "描述", 2, "file_island")
        assert r.task_count() == 1
        reset_cooperative_registry()
        r2 = get_cooperative_registry()
        assert r2.task_count() == 0


# ──────────────────────────────────────────────
# API 端点测试 (≥5 个)
# ──────────────────────────────────────────────


class TestApiEndpoints:
    """FastAPI 端点测试。"""

    def test_list_empty_tasks(self, client: TestClient) -> None:
        """空任务列表。"""
        r = client.get("/api/cooperative-tasks")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["tasks"] == []

    def test_create_task_via_registry_and_list(self, client: TestClient) -> None:
        """通过注册表创建再查询API。"""
        registry = get_cooperative_registry()
        registry.create_task("explore", "探索秘境", "描述", 2, "file_island", {"x": 100, "y": 200})
        r = client.get("/api/cooperative-tasks")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1

    def test_get_single_task(self, client: TestClient) -> None:
        """获取单个任务。"""
        registry = get_cooperative_registry()
        task = registry.create_task("defend", "保卫边境", "击退敌人", 2, "server_continent")
        r = client.get(f"/api/cooperative-tasks/{task.task_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["task_id"] == task.task_id
        assert data["task_type"] == "defend"
        assert data["title"] == "保卫边境"

    def test_get_nonexistent_task(self, client: TestClient) -> None:
        """获取不存在的任务。"""
        r = client.get("/api/cooperative-tasks/nonexistent_12345")
        assert r.status_code == 404

    def test_generate_endpoint(self, client: TestClient) -> None:
        """任务生成端点。"""
        r = client.post("/api/cooperative-tasks/generate", json={"tick_count": 0, "max_tasks": 2})
        assert r.status_code == 200
        data = r.json()
        assert "generated" in data
        assert "tasks" in data

    def test_contribute_endpoint(self, client: TestClient) -> None:
        """贡献端点。"""
        registry = get_cooperative_registry()
        task = registry.create_task("build", "建造设施", "共同建造", 2, "village_of_beginnings")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        r = client.post(
            f"/api/cooperative-tasks/{task.task_id}/contribute",
            json={"agent_name": "agumon", "amount": 0.5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["agent_name"] == "agumon"
        assert data["contributed"] == 0.5
        assert data["status"] == "active"

    def test_contribute_nonexistent_task(self, client: TestClient) -> None:
        """向不存在的任务贡献。"""
        r = client.post(
            "/api/cooperative-tasks/nonexistent/contribute",
            json={"agent_name": "agumon", "amount": 0.5},
        )
        assert r.status_code == 404

    def test_get_all_tasks_endpoint(self, client: TestClient) -> None:
        """获取所有任务端点。"""
        registry = get_cooperative_registry()
        registry.create_task("explore", "探索A", "desc", 2, "file_island")
        registry.create_task("hunt", "狩猎B", "desc", 2, "spiral_mountain")
        r = client.get("/api/cooperative-tasks/all")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2


# ──────────────────────────────────────────────
# 边界情况测试
# ──────────────────────────────────────────────


class TestEdgeCases:
    """边界情况测试。"""

    def test_max_participants(self, registry: CooperativeTaskRegistry) -> None:
        """达到最大参与者数。"""
        task = registry.create_task("hunt", "狩猎", "描述", 2, "spiral_mountain")
        # 添加 10 个参与者（最大值）
        for i in range(10):
            name = f"digimon_{i}"
            assert registry.join_task(task.task_id, name) is True
        # 第 11 个应失败
        assert registry.join_task(task.task_id, "extra") is False

    def test_contribute_inactive_task(self, registry: CooperativeTaskRegistry) -> None:
        """向未激活任务贡献。"""
        task = registry.create_task("explore", "探索", "描述", 3, "file_island")
        registry.join_task(task.task_id, "agumon")  # 仅 1 人，未激活
        assert registry.contribute(task.task_id, "agumon", 0.5) is False

    def test_join_completed_task(self, registry: CooperativeTaskRegistry) -> None:
        """无法加入已完成任务。"""
        task = registry.create_task("build", "建造", "描述", 2, "village_of_beginnings")
        registry.join_task(task.task_id, "agumon")
        registry.join_task(task.task_id, "gabumon")
        registry.contribute(task.task_id, "agumon", 1.0)
        registry.check_completion(task.task_id)
        assert task.status == "completed"
        assert registry.join_task(task.task_id, "piyomon") is False

    def test_create_task_default_position(self) -> None:
        """默认坐标。"""
        task = CooperativeTask(
            task_id="coop_test_default",
            task_type="explore",
            title="test",
            description="test",
            required_participants=2,
        )
        assert task.position == {"x": 0, "y": 0}

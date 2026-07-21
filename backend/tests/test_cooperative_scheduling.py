"""Phase 31 Task 4: Scheduler 协作调度集成测试"""
from digimon_world.world.cooperative_tasks import (
    CooperativeTask,
    TaskGenerationEngine,
    get_cooperative_registry,
    reset_cooperative_registry,
)
from digimon_world.world.scheduler import _get_coop_energy_factor


class FakeAgent:
    def __init__(self, name, energy=100):
        self.name = name
        self.energy = energy


class FakeTask:
    def __init__(self, participants, contributions=None):
        self.current_participants = participants
        self.individual_contributions = contributions or dict.fromkeys(participants, 0.0)


class TestCooperativeScheduling:
    def test_energy_factor_full_energy(self):
        agents = [FakeAgent("a", 100), FakeAgent("b", 100)]
        task = FakeTask(["a", "b"])
        assert _get_coop_energy_factor(agents, task) == 1.0

    def test_energy_factor_low_energy(self):
        agents = [FakeAgent("a", 30), FakeAgent("b", 30)]
        task = FakeTask(["a", "b"])
        assert _get_coop_energy_factor(agents, task) == 0.3

    def test_energy_factor_mixed_energy(self):
        agents = [FakeAgent("a", 100), FakeAgent("b", 50)]
        task = FakeTask(["a", "b"])
        factor = _get_coop_energy_factor(agents, task)
        assert 0.3 < factor < 1.0

    def test_energy_factor_missing_agent(self):
        agents = [FakeAgent("a", 100)]
        task = FakeTask(["a", "c"])  # c doesn't exist
        factor = _get_coop_energy_factor(agents, task)
        assert factor == 1.0  # Only known agent is at full energy

    def test_registry_add_task(self):
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="test_1", task_type="explore", title="Test",
            description="Desc", required_participants=2,
            current_participants=["a", "b"], sub_goals={},
            individual_contributions={"a": 0.0, "b": 0.0},
            status="active", tick_created=0, region_id="test",
        )
        reg.add_task(task)
        assert task in reg.get_active_tasks()
        assert reg.get_task("test_1") is task

    def test_registry_contribute(self):
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="test_2", task_type="defend", title="Defend",
            description="Desc", required_participants=2,
            current_participants=["a", "b"], sub_goals={},
            individual_contributions={"a": 0.0, "b": 0.0},
            status="active", tick_created=0, region_id="test",
            completion_threshold=1.0,
        )
        reg.add_task(task)
        reg.contribute("test_2", "a", 0.6)
        reg.contribute("test_2", "b", 0.5)
        assert task.individual_contributions["a"] == 0.6
        assert task.individual_contributions["b"] == 0.5
        assert reg.check_completion("test_2")["completed"]

    def test_registry_get_active_tasks(self):
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        t1 = CooperativeTask(
            task_id="t1", task_type="explore", title="E", description="D",
            required_participants=1, current_participants=["a"], sub_goals={},
            individual_contributions={"a": 0.0}, status="active", tick_created=0, region_id="r",
        )
        t2 = CooperativeTask(
            task_id="t2", task_type="build", title="B", description="D",
            required_participants=1, current_participants=["b"], sub_goals={},
            individual_contributions={"b": 0.0}, status="completed", tick_created=0, region_id="r",
        )
        reg.add_task(t1)
        reg.add_task(t2)
        active = reg.get_active_tasks()
        assert t1 in active
        assert t2 not in active

    def test_registry_get_agent_tasks(self):
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="t3", task_type="hunt", title="H", description="D",
            required_participants=3, current_participants=["a", "b", "c"],
            sub_goals={}, individual_contributions={"a": 0.0, "b": 0.0, "c": 0.0},
            status="active", tick_created=0, region_id="r",
        )
        reg.add_task(task)
        tasks_for_a = reg.get_agent_tasks("a")
        assert len(tasks_for_a) == 1
        assert tasks_for_a[0].task_id == "t3"

    def test_generation_engine_scan_no_agents(self):
        engine = TaskGenerationEngine()
        tasks = engine.scan_for_opportunities(None, [], 0)
        assert tasks == []

    def test_singleton_reset(self):
        reset_cooperative_registry()
        reg1 = get_cooperative_registry()
        reg1.add_task(CooperativeTask(
            task_id="s1", task_type="explore", title="S1", description="D",
            required_participants=1, current_participants=["a"], sub_goals={},
            individual_contributions={"a": 0.0}, status="active", tick_created=0, region_id="r",
        ))
        assert reg1.task_count() == 1
        reset_cooperative_registry()
        reg2 = get_cooperative_registry()
        assert reg2.task_count() == 0

    def test_completion_detection(self):
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="comp_test", task_type="defend", title="Defend",
            description="Desc", required_participants=2,
            current_participants=["a", "b"], sub_goals={},
            individual_contributions={"a": 0.0, "b": 0.0},
            status="active", tick_created=0, region_id="r",
            completion_threshold=1.0,
        )
        reg.add_task(task)
        # 未达阈值
        reg.contribute("comp_test", "a", 0.3)
        assert reg.check_completion("comp_test")["completed"] is False
        # 达阈值
        reg.contribute("comp_test", "b", 0.8)
        assert reg.check_completion("comp_test")["completed"] is True

    def test_generation_engine_creates_task_with_participants(self):
        """验证引擎生成的 task 有合理的参与者。"""
        import random
        rng = random.Random(42)
        engine = TaskGenerationEngine(rng=rng)

        class FakeRegion:
            def __init__(self, rid, name):
                self.id = rid
                self.name = name
                self.bounds = (0, 0, 1000, 1000)

        class FakeWorld:
            def __init__(self):
                self.regions = {"test_region": FakeRegion("test_region", "测试区")}

        agents = []
        for i in range(10):
            a = FakeAgent(f"agent_{i}", energy=80 + i * 2)
            a.location = (i * 90, i * 80)
            agents.append(a)

        task = engine.generate_random_task(FakeWorld(), agents, 100)
        assert task is not None
        assert len(task.current_participants) >= 2
        assert task.status == "active"

    def test_energy_factor_bounds(self):
        """能量因子必须在 0.3-1.0 范围内。"""
        assert _get_coop_energy_factor([FakeAgent("a", 0)], FakeTask(["a"])) == 0.3
        assert _get_coop_energy_factor([FakeAgent("a", 200)], FakeTask(["a"])) == 1.0

    def test_registry_task_count(self):
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        for i in range(5):
            reg.add_task(CooperativeTask(
                task_id=f"c_{i}", task_type="explore", title=f"T{i}", description="D",
                required_participants=1, current_participants=["a"], sub_goals={},
                individual_contributions={"a": 0.0}, status="active", tick_created=0, region_id="r",
            ))
        assert reg.task_count() == 5

    def test_contribute_nonexistent_task(self):
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        # contribute to nonexistent task should not crash
        reg.contribute("nonexistent", "a", 0.5)
        assert reg.task_count() == 0

    # ── Phase 31 Task 4 新增: 调度器集成测试 ──────

    def test_add_task_assigns_sub_goals(self):
        """add_task 传入空 sub_goals 时自动分配子目标。"""
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="sg_test", task_type="explore", title="探索测试",
            description="测试子目标分配", required_participants=2,
            current_participants=["a", "b"], sub_goals={},
            individual_contributions={"a": 0.0, "b": 0.0},
            status="active", tick_created=0, region_id="test",
        )
        reg.add_task(task)
        # add_task 应自动分配子目标
        assert len(task.sub_goals) == 2
        assert "a" in task.sub_goals
        assert "b" in task.sub_goals
        assert task.sub_goals["a"] != task.sub_goals["b"]  # 不同参与者不同子目标

    def test_add_task_preserves_existing_sub_goals(self):
        """add_task 不应覆盖引擎已分配的子目标。"""
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="sg_preserve", task_type="defend", title="防御测试",
            description="测试保留子目标", required_participants=2,
            current_participants=["x", "y"],
            sub_goals={"x": "自定义目标A", "y": "自定义目标B"},
            individual_contributions={"x": 0.0, "y": 0.0},
            status="active", tick_created=0, region_id="test",
        )
        reg.add_task(task)
        # 已有子目标时不应覆盖
        assert task.sub_goals["x"] == "自定义目标A"
        assert task.sub_goals["y"] == "自定义目标B"

    def test_create_task_then_join_assigns_sub_goals(self):
        """create_task + join_task 后应有子目标。"""
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = reg.create_task(
            task_type="hunt", title="狩猎测试", description="联合狩猎",
            required_participants=2, region_id="forest",
        )
        # create_task 时无参与者，sub_goals 应为空
        assert task.sub_goals == {}

        reg.join_task(task.task_id, "hunter_a")
        reg.join_task(task.task_id, "hunter_b")

        # join 后应有子目标
        assert len(task.sub_goals) == 2
        assert "hunter_a" in task.sub_goals
        assert "hunter_b" in task.sub_goals

    def test_full_lifecycle_sub_goals_present(self):
        """全生命周期: 创建→加入→贡献→完成，子目标全程存在。"""
        reset_cooperative_registry()
        reg = get_cooperative_registry()

        # 用引擎生成（模拟调度器扫描流程）
        import random
        rng = random.Random(99)
        engine = TaskGenerationEngine(rng=rng)

        class FakeRegion:
            def __init__(self, rid, name):
                self.id = rid
                self.name = name
                self.bounds = (0, 0, 1000, 1000)

        class FakeWorld:
            def __init__(self):
                self.regions = {"forest": FakeRegion("forest", "森林区")}

        agents = []
        for i in range(5):
            a = FakeAgent(f"digi_{i}", energy=100)
            a.location = (i * 50, i * 50)
            agents.append(a)

        task = engine.generate_random_task(FakeWorld(), agents, 100)
        assert task is not None
        assert len(task.sub_goals) >= 2  # 引擎已分配子目标

        # 添加到注册表
        reg.add_task(task)

        # 子目标被正确注册
        retrieved = reg.get_task(task.task_id)
        assert retrieved is not None
        assert len(retrieved.sub_goals) >= 2

        # 贡献度追踪（按阈值分配以确保完成）
        for p in task.current_participants:
            share = task.completion_threshold / len(task.current_participants)
            reg.contribute(task.task_id, p, share)

        # 完成检查
        result = reg.check_completion(task.task_id)
        assert result["completed"]

    def test_assign_sub_goals_public_api(self):
        """公开 API assign_sub_goals 正确分配子目标。"""
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="public_sg", task_type="build", title="建造测试",
            description="公开 API 测试", required_participants=3,
            current_participants=["builder_a", "builder_b", "builder_c"],
            sub_goals={},
            individual_contributions={"builder_a": 0.0, "builder_b": 0.0, "builder_c": 0.0},
            status="active", tick_created=0, region_id="test",
        )
        reg.add_task(task)
        # 由于 add_task 空 sub_goals 也会触发分配，再次调用也应正确
        result = reg.assign_sub_goals(task.task_id)
        assert len(result) == 3
        # 每个参与者都有不同的子目标（至少第一个与第二个不同）
        assert result["builder_a"] != result["builder_b"]

    def test_energy_factor_all_agents(self):
        """能量因子使用所有参与者计算。"""
        agents = [
            FakeAgent("a", 100),
            FakeAgent("b", 80),
            FakeAgent("c", 60),
            FakeAgent("d", 40),
        ]
        task = FakeTask(["a", "b", "c", "d"])
        factor = _get_coop_energy_factor(agents, task)
        # avg = (100+80+60+40)/400 = 0.7
        assert abs(factor - 0.7) < 0.01

    def test_add_task_indexes_agent_correctly(self):
        """add_task 正确索引 agent → task 映射。"""
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="idx_test", task_type="explore", title="索引测试",
            description="测试索引", required_participants=2,
            current_participants=["agent_x", "agent_y"],
            sub_goals={},
            individual_contributions={"agent_x": 0.0, "agent_y": 0.0},
            status="active", tick_created=0, region_id="zone_a",
        )
        reg.add_task(task)
        # 按 agent 查询
        x_tasks = reg.get_agent_tasks("agent_x")
        y_tasks = reg.get_agent_tasks("agent_y")
        assert len(x_tasks) == 1
        assert len(y_tasks) == 1
        assert x_tasks[0].task_id == "idx_test"
        # 按 region 查询
        zone_tasks = reg.get_tasks_by_region("zone_a")
        assert len(zone_tasks) == 1
        assert zone_tasks[0].task_id == "idx_test"

    def test_failed_task_not_in_active(self):
        """超时失败的任务不出现在活跃列表中。"""
        reset_cooperative_registry()
        reg = get_cooperative_registry()
        task = CooperativeTask(
            task_id="timeout_test", task_type="hunt", title="超时任务",
            description="测试超时", required_participants=2,
            current_participants=["a", "b"],
            sub_goals={},
            individual_contributions={"a": 0.0, "b": 0.0},
            status="active", tick_created=0, region_id="test",
            completion_threshold=2.0,
        )
        reg.add_task(task)
        assert task in reg.get_active_tasks()

        # 标记为失败
        task.status = "failed"
        assert task not in reg.get_active_tasks()

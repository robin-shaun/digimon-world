"""测试黑色齿轮系统 (Phase 8: 数码宝贝原作复刻 — 🟡 P1)。"""
import random

import pytest

from digimon_world.world.dark_gears import (
    GEAR_DAMAGE_PER_BATTLE,
    GEAR_DEFAULT_HP,
    INFECTION_ATTACK_BONUS,
    INFECTION_DEFENSE_PENALTY,
    MAX_ACTIVE_GEARS,
    DarkGear,
    DarkGearSystem,
    get_dark_gear_system,
    reset_dark_gear_system,
)


class TestDarkGear:
    """DarkGear 数据类的单元测试。"""

    def test_create_gear(self):
        gear = DarkGear(
            gear_id="dark_gear_001",
            sub_region_id="confusion_forest",
            placed_at_tick=500,
        )
        assert gear.gear_id == "dark_gear_001"
        assert gear.sub_region_id == "confusion_forest"
        assert gear.placed_at_tick == 500
        assert gear.hp == GEAR_DEFAULT_HP
        assert not gear.destroyed

    def test_take_damage_partial(self):
        gear = DarkGear("g01", "gear_savannah", 100)
        destroyed = gear.take_damage(10)
        assert not destroyed
        assert gear.hp == GEAR_DEFAULT_HP - 10
        assert not gear.destroyed

    def test_take_damage_lethal(self):
        gear = DarkGear("g01", "gear_savannah", 100)
        destroyed = gear.take_damage(GEAR_DEFAULT_HP)
        assert destroyed
        assert gear.hp == 0
        assert gear.destroyed

    def test_take_damage_overkill(self):
        """过量伤害也应该标记为摧毁。"""
        gear = DarkGear("g01", "gear_savannah", 100)
        destroyed = gear.take_damage(999)
        assert destroyed
        assert gear.hp == 0

    def test_to_dict(self):
        gear = DarkGear("dark_gear_002", "beach_of_departure", 200)
        d = gear.to_dict()
        assert d["gear_id"] == "dark_gear_002"
        assert d["sub_region_id"] == "beach_of_departure"
        assert d["placed_at_tick"] == 200
        assert d["hp"] == GEAR_DEFAULT_HP
        assert d["destroyed"] is False


class TestDarkGearSystem:
    """DarkGearSystem 集成测试。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.system = reset_dark_gear_system()

    def test_initial_state(self):
        assert len(self.system.active_gears) == 0
        assert self.system.total_gears_placed == 0
        assert self.system.threat_level == "PEACEFUL"

    def test_no_placement_on_non_interval(self):
        """在非 placement 间隔 tick 上不应投放齿轮。"""
        gear = self.system.process(tick_count=1)
        assert gear is None
        gear = self.system.process(tick_count=42)
        assert gear is None

    def test_can_force_placement(self):
        """force_place_gear 应绕过概率检查直接投放。"""
        self.system.force_place_gear(sub_region_id="gear_savannah")
        assert len(self.system.active_gears) == 1
        assert self.system.active_gears[0].gear_id == "dark_gear_001"
        assert not self.system.active_gears[0].destroyed
        assert self.system.total_gears_placed == 1

    def test_placement_cooldown(self):
        """process() 在冷却期内不应投放（即使 tick 在 interval 上）。"""
        # 手动投放一个齿轮在 tick=200
        self.system.force_place_gear(sub_region_id="confusion_forest", tick=200)
        # tick=400 在 interval 上但冷却期内 (400-200=200 < 300)
        gear = self.system.process(tick_count=400)
        assert gear is None
        # tick=600 已过冷却期 (600-200=400 >= 300)
        # 但需要 rng 配合 — 验证 at least 逻辑允许投放
        # (随机性由 test_can_force_placement 等覆盖)

    def test_max_active_gears(self):
        """活动齿轮达到上限后 process() 应拒绝投放。"""
        # 手动投放至上限
        for i in range(MAX_ACTIVE_GEARS):
            self.system.force_place_gear(
                sub_region_id=f"sub_{i}", tick=1000 + i * 500
            )
        assert len(self.system.active_gears) == MAX_ACTIVE_GEARS

        # process 在 interval tick + 冷却过后仍应拒绝（已达上限）
        gear = self.system.process(tick_count=3000)
        assert gear is None
        assert len(self.system.active_gears) == MAX_ACTIVE_GEARS

    def test_cleanup_destroyed_gears(self):
        """process() 应该清理已被摧毁的齿轮。"""
        gear = self.system.force_place_gear(sub_region_id="confusion_forest", tick=0)
        gear.take_damage(GEAR_DEFAULT_HP)
        assert gear.destroyed

        # process 清理
        self.system.process(tick_count=1)
        assert len(self.system.active_gears) == 0

    def test_is_sub_region_infected(self):
        self.system.force_place_gear(sub_region_id="confusion_forest")
        assert self.system.is_sub_region_infected("confusion_forest") is True
        assert self.system.is_sub_region_infected("beach_of_departure") is False

    def test_is_agent_infected(self):
        self.system.force_place_gear(sub_region_id="confusion_forest")
        assert self.system.is_agent_infected("confusion_forest") is True
        assert self.system.is_agent_infected("toy_town") is False
        assert self.system.is_agent_infected(None) is False

    def test_get_infection_stats(self):
        self.system.force_place_gear(sub_region_id="confusion_forest")
        attack, defense, infected = self.system.get_infection_stats(
            100, 100, "confusion_forest"
        )
        assert infected is True
        assert attack == int(100 * INFECTION_ATTACK_BONUS)
        assert defense == int(100 * INFECTION_DEFENSE_PENALTY)

        # 未感染区域不变
        attack2, defense2, infected2 = self.system.get_infection_stats(
            100, 100, "beach_of_departure"
        )
        assert infected2 is False
        assert attack2 == 100
        assert defense2 == 100

    def test_try_destroy_gear_partial(self):
        gear = self.system.force_place_gear(sub_region_id="gear_savannah")
        destroyed, msg = self.system.try_destroy_gear("gear_savannah")
        assert not destroyed
        assert "剩余 HP" in msg
        assert not gear.destroyed
        assert gear.hp == GEAR_DEFAULT_HP - GEAR_DAMAGE_PER_BATTLE

    def test_try_destroy_gear_lethal(self):
        gear = self.system.force_place_gear(sub_region_id="gear_savannah")
        # 3次打击 ≥ GEAR_DEFAULT_HP (50) with GEAR_DAMAGE_PER_BATTLE (20)
        for _ in range(5):
            destroyed, _ = self.system.try_destroy_gear("gear_savannah")
            if destroyed:
                break
        assert gear.destroyed

    def test_try_destroy_gear_empty(self):
        destroyed, msg = self.system.try_destroy_gear("toy_town")
        assert not destroyed
        assert "没有" in msg

    def test_threat_levels(self):
        assert self.system.threat_level == "PEACEFUL"

        # 添加齿轮验证威胁等级
        gear1 = DarkGear("g01", "sub1", 100)
        self.system._gears.append(gear1)
        assert self.system.threat_level == "CAUTIOUS"

        gear2 = DarkGear("g02", "sub2", 100)
        self.system._gears.append(gear2)
        assert self.system.threat_level == "THREATENED"

        gear3 = DarkGear("g03", "sub3", 100)
        self.system._gears.append(gear3)
        assert self.system.threat_level == "THREATENED"

        gear4 = DarkGear("g04", "sub4", 100)
        self.system._gears.append(gear4)
        assert self.system.threat_level == "CRISIS"

    def test_to_dict(self):
        gear = DarkGear("g01", "confusion_forest", 100)
        self.system._gears.append(gear)

        d = self.system.to_dict()
        assert len(d["active_gears"]) == 1
        assert d["active_gears"][0]["gear_id"] == "g01"
        assert d["threat_level"] == "CAUTIOUS"
        assert "confusion_forest" in d["infected_sub_regions"]

    def test_total_gears_placed_counter(self):
        self.system.force_place_gear(sub_region_id="confusion_forest")
        assert self.system.total_gears_placed == 1

    def test_reset(self):
        self.system._gears.append(DarkGear("g01", "sub1", 100))
        self.system._gear_counter = 5
        self.system.reset()
        assert len(self.system.active_gears) == 0
        assert self.system.total_gears_placed == 0

    def test_global_singleton(self):
        system_a = get_dark_gear_system()
        system_b = get_dark_gear_system()
        assert system_a is system_b

        reset_system = reset_dark_gear_system()
        assert isinstance(reset_system, DarkGearSystem)

    def test_multiple_gears_different_sub_regions(self):
        """多个齿轮在不同子区域，每个子区域独立感染。"""
        gear1 = DarkGear("g01", "confusion_forest", 100)
        gear2 = DarkGear("g02", "gear_savannah", 200)
        self.system._gears.extend([gear1, gear2])

        assert self.system.is_sub_region_infected("confusion_forest")
        assert self.system.is_sub_region_infected("gear_savannah")
        assert not self.system.is_sub_region_infected("toy_town")

    def test_pick_target_prefers_occupied(self):
        """_pick_target_sub_region 应该优先选择有 agent 的子区域。"""
        # 构建简单的 world mock
        world_mock = type("World", (), {
            "agents": [
                {"sub_region": {"id": "beach_of_departure"}},
            ]
        })()
        system = DarkGearSystem(rng=random.Random(0))
        target = system._pick_target_sub_region(world_mock)
        assert target == "beach_of_departure"

    def test_pick_target_fallback_random(self):
        """没有 world 或 agent 时回退到随机选择。"""
        system = DarkGearSystem(rng=random.Random(0))
        target = system._pick_target_sub_region(None)
        # 应该是 14 个文件岛子区域之一
        valid = {
            "freezing_area", "miharashi_mountain", "ancient_dino_region",
            "shogungekomon_castle", "confusion_forest", "gear_savannah",
            "infinity_mountain_peak", "dark_cave", "dragon_eye_lake",
            "ogremon_fortress", "factory_area", "beach_of_departure",
            "vending_machine_area", "toy_town",
        }
        assert target in valid

    def test_try_destroy_gear_with_multiplier(self):
        """进化阶段倍率: MEGA(3x) 应造成 60 点伤害 (20*3), 一击摧毁齿轮。"""
        gear = self.system.force_place_gear(sub_region_id="dark_cave")
        destroyed, msg = self.system.try_destroy_gear(
            "dark_cave", damage_multiplier=3.0
        )
        assert destroyed
        assert "被战斗余波摧毁" in msg
        assert gear.destroyed
        assert len(self.system.active_gears) == 0  # 清理后应为0

    def test_try_destroy_gear_with_multiplier_partial(self):
        """FRESH(0.5x) 应只造成 10 点伤害, 不够摧毁。"""
        gear = self.system.force_place_gear(sub_region_id="confusion_forest")
        destroyed, msg = self.system.try_destroy_gear(
            "confusion_forest", damage_multiplier=0.5
        )
        assert not destroyed
        assert "剩余 HP" in msg
        assert gear.hp == GEAR_DEFAULT_HP - int(GEAR_DAMAGE_PER_BATTLE * 0.5)

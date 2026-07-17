"""测试文件岛 14 子区域拓扑 (Phase 8: 数码宝贝原作复刻)。"""
import pytest
from digimon_world.world.world_state import (
    FILE_ISLAND,
    get_world,
    reset_world,
)


class TestFileIslandSubRegions:
    """文件岛应该有 14 个完全覆盖 960x600 地图的子区域。
    注意 Phase 17 后文件岛平移到右下角 (2900, 2300) 起点。"""

    def test_sub_region_count(self):
        """确认文件岛有恰好 14 个子区域。"""
        assert len(FILE_ISLAND.sub_regions) == 14

    def test_all_sub_regions_have_unique_ids(self):
        """子区域 ID 必须唯一。"""
        ids = [sr.sub_region_id for sr in FILE_ISLAND.sub_regions]
        assert len(ids) == len(set(ids)), f"Duplicate sub_region_id found: {ids}"

    def test_all_sub_regions_have_names(self):
        """每个子区域必须有中文名和英文名。"""
        for sr in FILE_ISLAND.sub_regions:
            assert sr.name, f"{sr.sub_region_id} has empty name"
            assert sr.name_en, f"{sr.sub_region_id} has empty name_en"
            assert sr.description, f"{sr.sub_region_id} has empty description"

    @pytest.mark.parametrize("x,y,expected", [
        (3060, 2820, "beach_of_departure"),
        (3260, 2490, "confusion_forest"),
        (3500, 2480, "gear_savannah"),
        (3740, 2490, "infinity_mountain_peak"),
        (3010, 2570, "dark_cave"),
        (3260, 2620, "dragon_eye_lake"),
        (3500, 2640, "ogremon_fortress"),
        (3730, 2620, "factory_area"),
        (3360, 2830, "vending_machine_area"),
        (3700, 2820, "toy_town"),
        (3020, 2350, "freezing_area"),
        (3380, 2360, "miharashi_mountain"),
        (3740, 2355, "ancient_dino_region"),
        (3000, 2470, "shogungekomon_castle"),
    ])
    def test_coordinate_lookup(self, x, y, expected):
        """每类子区域的代表性坐标应该命中。"""
        sr = FILE_ISLAND.find_sub_region(x, y)
        assert sr is not None, f"({x}, {y}) not in any sub-region"
        assert sr.sub_region_id == expected, (
            f"({x}, {y}) → {sr.sub_region_id}, expected {expected}"
        )

    def test_full_map_coverage(self):
        """文件岛 960x600 地图中的每个像素都应该命中某个子区域 (Phase 17 平移到 2900,2300)。"""
        # 采样检查: 每 60 像素一个采样点
        misses = []
        for x in range(2900, 3861, 60):
            for y in range(2300, 2901, 60):
                sr = FILE_ISLAND.find_sub_region(x, y)
                if sr is None:
                    misses.append((x, y))
        assert len(misses) == 0, f"{len(misses)} pixels not covered: {misses[:10]}..."

    def test_sub_regions_serialized_in_world_to_dict(self):
        """WorldState.to_dict() 应包含子区域数据。"""
        reset_world()
        world = get_world()
        data = world.to_dict()

        file_island_data = next(
            (r for r in data["regions"] if r["id"] == "file_island"), None
        )
        assert file_island_data is not None
        assert "sub_regions" in file_island_data
        assert len(file_island_data["sub_regions"]) == 14

        # 每个子区域有完整字段
        for sr in file_island_data["sub_regions"]:
            for key in ("id", "name", "name_en", "bounds", "pois"):
                assert key in sr, f"sub_region missing key: {key}"

    def test_agent_sub_region_attribution(self):
        """Agent 序列化时应附带当前 sub_region。"""
        reset_world()
        world = get_world()
        data = world.to_dict()

        for agent_data in data["agents"]:
            assert "sub_region" in agent_data, (
                f"Agent {agent_data['name']} missing sub_region in to_dict()"
            )
            sr = agent_data["sub_region"]
            if sr is not None:
                assert "id" in sr
                assert "name" in sr
                assert "name_en" in sr

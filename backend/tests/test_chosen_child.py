"""
Phase 12: 被选召的孩子 (ChosenChildAgent) 测试
==============================================

测试 ChosenChildAgent 本体 + FastAPI 端点。
"""

import pytest
from fastapi.testclient import TestClient

from digimon_world.agents.chosen_child import ChosenChildAgent, Crest
from digimon_world.api.app import app, _chosen_children


@pytest.fixture(autouse=True)
def _clear_chosen_children() -> None:
    """每个测试前后清空内存存储,避免测试间互相污染。"""
    _chosen_children.clear()
    yield
    _chosen_children.clear()


# ---- ChosenChildAgent 单元测试 ----


class TestChosenChildAgent:
    """ChosenChildAgent 本体测试。"""

    def test_create_default(self) -> None:
        """默认创建: 名字、徽章、位置、搭档为空。"""
        child = ChosenChildAgent(name="肖昆")
        assert child.name == "肖昆"
        assert child.crest == Crest.COURAGE
        assert child.crest.value == "courage"
        assert child.partner_name is None
        assert child.region_id == "file_island"
        assert child.location == (500, 400)

    def test_create_with_crest(self) -> None:
        """指定徽章创建。"""
        child = ChosenChildAgent(name="太一", crest=Crest.COURAGE)
        assert child.crest == Crest.COURAGE

        child2 = ChosenChildAgent(name="大和", crest=Crest.FRIENDSHIP)
        assert child2.crest == Crest.FRIENDSHIP

    def test_all_crests_have_labels(self) -> None:
        """所有徽章都有中文标签。"""
        all_crests = list(Crest)
        assert len(all_crests) == 8  # 勇气/友情/爱心/知识/希望/光明/诚实/善良
        for c in all_crests:
            label = Crest.label(c)
            assert label, f"Crest {c} has no label"
            assert isinstance(label, str)

    def test_move_basic(self) -> None:
        """基础移动: dx, dy 更新坐标。"""
        child = ChosenChildAgent(name="肖昆", location=(500, 400))
        new_pos = child.move(10, -20)
        assert new_pos == (510, 380)
        assert child.location == (510, 380)

    def test_move_clamp(self) -> None:
        """移动边界夹紧: 不出 [0, 1000] 范围。"""
        child = ChosenChildAgent(name="肖昆", location=(5, 5))
        new_pos = child.move(-20, -30)
        assert new_pos == (0, 0)  # clamped

        child2 = ChosenChildAgent(name="肖昆2", location=(990, 995))
        new_pos2 = child2.move(30, 10)
        assert new_pos2 == (1000, 1000)  # clamped

    def test_move_updates_last_active(self) -> None:
        """移动会刷新 last_active。"""
        child = ChosenChildAgent(name="肖昆")
        old_active = child.last_active
        child.move(10, 10)
        assert child.last_active > old_active

    def test_set_partner(self) -> None:
        """绑定搭档数码兽。"""
        child = ChosenChildAgent(name="肖昆")
        assert child.partner_name is None
        child.set_partner("亚古兽")
        assert child.partner_name == "亚古兽"

    def test_touch(self) -> None:
        """touch() 刷新 last_active。"""
        child = ChosenChildAgent(name="肖昆")
        old_active = child.last_active
        child.touch()
        assert child.last_active >= old_active

    def test_to_dict(self) -> None:
        """序列化包含所有关键字段。"""
        child = ChosenChildAgent(
            name="肖昆",
            partner_name="亚古兽",
            crest=Crest.COURAGE,
        )
        d = child.to_dict()
        assert d["name"] == "肖昆"
        assert d["partner_name"] == "亚古兽"
        assert d["crest"] == "courage"
        assert d["crest_label"] == "勇气"
        assert d["region_id"] == "file_island"
        assert d["position"] == {"x": 500, "y": 400}
        assert "created_at" in d
        assert "last_active" in d

    def test_from_dict_roundtrip(self) -> None:
        """dict 往返: to_dict → from_dict 保持数据一致。"""
        child = ChosenChildAgent(
            name="肖昆",
            partner_name="亚古兽",
            crest=Crest.FRIENDSHIP,
            location=(300, 200),
        )
        d = child.to_dict()
        restored = ChosenChildAgent.from_dict(d)
        assert restored.name == child.name
        assert restored.partner_name == child.partner_name
        assert restored.crest == child.crest
        assert restored.location == child.location


# ---- API 端点测试 ----


class TestChosenChildrenAPI:
    """FastAPI /api/chosen-children 端点测试。"""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_create_chosen_child(self, client: TestClient) -> None:
        """POST /api/chosen-children 创建一个孩子。"""
        resp = client.post("/api/chosen-children", json={
            "name": "肖昆",
            "crest": "courage",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "肖昆"
        assert data["crest"] == "courage"
        assert data["crest_label"] == "勇气"

    def test_create_duplicate_409(self, client: TestClient) -> None:
        """重复名字返回 409。"""
        client.post("/api/chosen-children", json={"name": "肖昆"})
        resp = client.post("/api/chosen-children", json={"name": "肖昆"})
        assert resp.status_code == 409

    def test_create_invalid_crest_400(self, client: TestClient) -> None:
        """无效徽章返回 400。"""
        resp = client.post("/api/chosen-children", json={
            "name": "肖昆",
            "crest": "unknown_crest",
        })
        assert resp.status_code == 400

    def test_list_empty(self, client: TestClient) -> None:
        """空列表。"""
        resp = client.get("/api/chosen-children")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["children"] == []

    def test_list_with_children(self, client: TestClient) -> None:
        """创建 3 个后列出。"""
        for name in ["肖昆", "太一", "大和"]:
            client.post("/api/chosen-children", json={"name": name})
        resp = client.get("/api/chosen-children")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        names = [c["name"] for c in data["children"]]
        assert "肖昆" in names
        assert "太一" in names
        assert "大和" in names

    def test_get_single(self, client: TestClient) -> None:
        """GET /api/chosen-children/{name}。"""
        client.post("/api/chosen-children", json={"name": "肖昆"})
        resp = client.get("/api/chosen-children/肖昆")
        assert resp.status_code == 200
        assert resp.json()["name"] == "肖昆"

    def test_get_not_found(self, client: TestClient) -> None:
        """不存在的孩子返回 404。"""
        resp = client.get("/api/chosen-children/nobody")
        assert resp.status_code == 404

    def test_move(self, client: TestClient) -> None:
        """POST /api/chosen-children/{name}/move。"""
        client.post("/api/chosen-children", json={"name": "肖昆"})
        resp = client.post("/api/chosen-children/肖昆/move", json={"dx": 50, "dy": -30})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "肖昆"
        assert data["position"] == {"x": 550, "y": 370}

    def test_move_not_found(self, client: TestClient) -> None:
        """移动不存在的孩子返回 404。"""
        resp = client.post("/api/chosen-children/nobody/move", json={"dx": 10, "dy": 10})
        assert resp.status_code == 404

    def test_set_partner(self, client: TestClient) -> None:
        """POST /api/chosen-children/{name}/partner 绑定搭档。"""
        client.post("/api/chosen-children", json={"name": "肖昆"})
        resp = client.post("/api/chosen-children/肖昆/partner", json={
            "partner_name": "亚古兽",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["partner_name"] == "亚古兽"

    def test_set_partner_not_found_digimon(self, client: TestClient) -> None:
        """绑定不存在的数码兽返回 404。"""
        client.post("/api/chosen-children", json={"name": "肖昆"})
        resp = client.post("/api/chosen-children/肖昆/partner", json={
            "partner_name": "不存在的数码兽",
        })
        assert resp.status_code == 404

    def test_delete(self, client: TestClient) -> None:
        """DELETE /api/chosen-children/{name}。"""
        client.post("/api/chosen-children", json={"name": "肖昆"})
        resp = client.delete("/api/chosen-children/肖昆")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        # 确认已删除
        resp2 = client.get("/api/chosen-children/肖昆")
        assert resp2.status_code == 404

    def test_delete_not_found(self, client: TestClient) -> None:
        """删除不存在的孩子返回 404。"""
        resp = client.delete("/api/chosen-children/nobody")
        assert resp.status_code == 404

    def test_root_includes_count(self, client: TestClient) -> None:
        """根端点包含 chosen_children_count。"""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == 12
        assert "chosen_children_count" in data
        assert data["chosen_children_count"] == 0

        # 创建一个后 count 变化
        client.post("/api/chosen-children", json={"name": "肖昆"})
        resp2 = client.get("/")
        assert resp2.json()["chosen_children_count"] == 1

    def test_create_with_partner(self, client: TestClient) -> None:
        """创建时直接指定搭档(即使数码兽不存在也不拒绝,POC 阶段允许)。"""
        resp = client.post("/api/chosen-children", json={
            "name": "肖昆",
            "crest": "courage",
            "partner_name": "亚古兽",
        })
        assert resp.status_code == 201
        assert resp.json()["partner_name"] == "亚古兽"

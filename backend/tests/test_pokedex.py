"""图鉴 API 测试: /api/pokedex 列表 + 详情 + 属性克制。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world.api import app
from digimon_world.world import reset_world


@pytest.fixture(autouse=True)
def _reset():
    reset_world()
    yield
    reset_world()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_pokedex(client: TestClient) -> None:
    r = client.get("/api/pokedex")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 8
    species = {e["species"] for e in data["entries"]}
    # 8 只初始数码兽都在
    assert species == {
        "agumon", "gabumon", "biyomon", "tentomon",
        "palmon", "gomamon", "patamon", "tailmon",
    }
    # 列表字段完整性
    for e in data["entries"]:
        assert e["name"]
        assert e["attribute"] in {"vaccine", "data", "virus", "free"}
        assert e["element"]
        assert e["crest"]
        assert e["mega_name"]
        assert e["stages"] == 4


def test_get_entry_detail(client: TestClient) -> None:
    r = client.get("/api/pokedex/agumon")
    assert r.status_code == 200
    data = r.json()
    assert data["species"] == "agumon"
    assert data["name"] == "亚古兽"
    assert data["crest"] == "勇气"
    assert data["description"]
    # 进化链 4 阶,从成长期到究极体
    chain = data["evolution_chain"]
    assert len(chain) == 4
    assert chain[0]["stage"] == "rookie"
    assert chain[-1]["stage"] == "mega"
    assert chain[-1]["name"] == "战斗暴龙兽"
    # 每阶至少一个招式
    for form in chain:
        assert form["skills"]
        assert form["emoji"]


def test_type_matchup(client: TestClient) -> None:
    """疫苗种克制病毒种,惧数据种。"""
    r = client.get("/api/pokedex/agumon")
    tm = r.json()["type_matchup"]
    assert tm["attribute"] == "vaccine"
    assert tm["strong_against"] == "virus"
    assert tm["weak_against"] == "data"
    assert tm["note"]


def test_case_insensitive(client: TestClient) -> None:
    r = client.get("/api/pokedex/AGUMON")
    assert r.status_code == 200
    assert r.json()["species"] == "agumon"


def test_entry_not_found(client: TestClient) -> None:
    r = client.get("/api/pokedex/不存在兽")
    assert r.status_code == 404

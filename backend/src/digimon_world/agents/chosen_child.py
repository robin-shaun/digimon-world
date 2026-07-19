"""
ChosenChildAgent - 被选召的孩子 (玩家角色)
==========================================

Phase 12: 用户以「被选召的孩子」身份进入数码世界。

设计要点:
- 轻量级 agent,不含 LLM 决策/记忆/反思循环
- 手动控制移动,可以跟数码兽互动
- 拥有徽章(crest)和一只搭档数码兽(partner)
- 可在世界地图上自由行走
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar


class Crest(str, Enum):
    """徽章(神圣计划发光标识)。"""

    COURAGE = "courage"        # 勇气
    FRIENDSHIP = "friendship"  # 友情
    LOVE = "love"              # 爱心
    KNOWLEDGE = "knowledge"    # 知识
    HOPE = "hope"              # 希望
    LIGHT = "light"            # 光明
    SINCERITY = "sincerity"    # 诚实
    KINDNESS = "kindness"      # 善良

    @classmethod
    def label(cls, crest: Crest) -> str:
        """返回徽章的中文名。"""
        return {
            cls.COURAGE: "勇气",
            cls.FRIENDSHIP: "友情",
            cls.LOVE: "爱心",
            cls.KNOWLEDGE: "知识",
            cls.HOPE: "希望",
            cls.LIGHT: "光明",
            cls.SINCERITY: "诚实",
            cls.KINDNESS: "善良",
        }.get(crest, crest.value)


@dataclass
class ChosenChildAgent:
    """一个被选召的孩子 —— 用户在数码世界的化身。

    Attributes:
        name: 孩子名字(如"肖昆")
        partner_name: 搭档数码兽的名字(引用 world 里的 DigimonAgent.name)
        crest: 持有的徽章类型
        region_id: 所在地区
        location: 坐标 (x, y)
        created_at: 创建时间
        last_active: 最近活跃时间
    """

    name: str
    partner_name: str | None = None
    crest: Crest = Crest.COURAGE
    region_id: str = "file_island"
    location: tuple[int, int] = (500, 400)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)

    # 步长(像素/次移动)
    DEFAULT_STEP: ClassVar[int] = 20

    def move(self, dx: int, dy: int, clamp_min: int = 0, clamp_max: int = 1000) -> tuple[int, int]:
        """移动指定偏移量,返回新坐标。

        Args:
            dx: X 方向位移(像素)
            dy: Y 方向位移(像素)
            clamp_min: 坐标下限
            clamp_max: 坐标上限

        Returns:
            新坐标 (x, y)
        """
        old_x, old_y = self.location
        new_x = max(clamp_min, min(clamp_max, old_x + dx))
        new_y = max(clamp_min, min(clamp_max, old_y + dy))
        self.location = (new_x, new_y)
        self.last_active = datetime.utcnow()
        return self.location

    def set_partner(self, digimon_name: str) -> None:
        """绑定搭档数码兽。"""
        self.partner_name = digimon_name
        self.last_active = datetime.utcnow()

    def touch(self) -> None:
        """刷新最近活跃时间(任何交互都调用此方法)。"""
        self.last_active = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典(API 响应 + 前端渲染)。"""
        return {
            "name": self.name,
            "partner_name": self.partner_name,
            "crest": self.crest.value,
            "crest_label": Crest.label(self.crest),
            "region_id": self.region_id,
            "position": {"x": self.location[0], "y": self.location[1]},
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChosenChildAgent:
        """从字典反序列化。"""
        return cls(
            name=data["name"],
            partner_name=data.get("partner_name"),
            crest=Crest(data.get("crest", "courage")),
            region_id=data.get("region_id", "file_island"),
            location=(
                int(data["position"]["x"]) if isinstance(data.get("position"), dict)
                else int(data.get("position", [500, 400])[0]),
                int(data["position"]["y"]) if isinstance(data.get("position"), dict)
                else int(data.get("position", [500, 400])[1]),
            ),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            last_active=datetime.fromisoformat(data["last_active"]) if "last_active" in data else datetime.utcnow(),
        )

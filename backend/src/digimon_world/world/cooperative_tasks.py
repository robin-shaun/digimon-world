"""
协作任务系统 (Cooperative Task System) — Phase 31
==================================================

数码宝贝虚拟世界中的协作任务系统，允许多只数码兽组队完成共同目标。
支持探索、防御、建造、狩猎四种任务类型，包含任务注册表、贡献度追踪和任务生成引擎。

核心组件:
- CooperativeTask: 代表一个协作任务的数据类
- CooperativeTaskRegistry: 全局任务注册表（CRUD + 查询）
- TaskGenerationEngine: 基于世界状态自动生成协作任务

设计原则:
- 纯数据驱动，无 LLM 依赖
- 任务状态机: pending → active → completed/failed
- 贡献度追踪支持共享奖励分配
- 任务生成基于区域特性和数码兽 proximity

基础设施: Phase 1 (world_state) + Phase 6 (relationships)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

TASK_TYPES: tuple[str, ...] = ("explore", "defend", "build", "hunt")
"""协作任务类型枚举: explore=探索新区, defend=击退入侵者, build=共同建造, hunt=组队狩猎"""

DEFAULT_COMPLETION_THRESHOLD: float = 1.0
"""默认完成阈值: 总贡献度达到此值即完成"""

MAX_PARTICIPANTS_PER_TASK: int = 10
"""单任务最大参与者数"""

DEFAULT_SHARED_REWARD: float = 0.3
"""默认共享奖励比例"""

DEFAULT_SCAN_MAX_TASKS: int = 3
"""单次扫描最多生成的任务数"""

# 区域 → 适合的任务类型映射
REGION_TASK_PREFERENCES: dict[str, list[str]] = {
    "file_island": ["explore", "hunt", "defend"],
    "server_continent": ["build", "defend", "hunt"],
    "spiral_mountain": ["explore", "hunt"],
    "endless_ocean": ["explore", "defend"],
    "infinity_mountain": ["explore", "build"],
    "village_of_beginnings": ["build", "defend"],
}


# 任务类型 → 标题模板
TASK_TITLE_TEMPLATES: dict[str, list[str]] = {
    "explore": [
        "探索{region}秘境",
        "开拓{region}新区域",
        "调查{region}异常信号",
        "搜寻{region}隐藏通道",
    ],
    "defend": [
        "保卫{region}边境",
        "击退入侵{region}的黑暗势力",
        "守护{region}的和平",
        "防御{region}受到的外来威胁",
    ],
    "build": [
        "在{region}建设新设施",
        "修复{region}受损建筑",
        "打造{region}共同家园",
        "扩建{region}基础设施",
    ],
    "hunt": [
        "组队狩猎{region}强敌",
        "追捕{region}的稀有目标",
        "在{region}开展联合狩猎",
        "挑战{region}的霸主",
    ],
}

# 任务类型 → 描述模板
TASK_DESC_TEMPLATES: dict[str, list[str]] = {
    "explore": [
        "一支探险队正在{region}集结，准备探索未知领域。",
        "{region}出现了异常信号，需要数码兽前往调查。",
        "{region}深处发现了隐藏通道，需要联合力量开拓。",
    ],
    "defend": [
        "黑暗势力正在逼近{region}，需要数码兽联手抵抗。",
        "{region}的边境遭到入侵，急需守卫力量。",
        "有外来威胁出现在{region}附近，需要组织防线。",
    ],
    "build": [
        "数码兽们正计划在{region}建造新的设施。",
        "{region}的部分建筑在战斗中受损，需要修复。",
        "{region}需要扩建基础设施以容纳更多居民。",
    ],
    "hunt": [
        "一只强大的敌人正在{region}横行，需要组队讨伐。",
        "{region}出现了稀有的猎物，组队狩猎的好机会。",
        "多位数码兽决定联手挑战{region}的霸主。",
    ],
}


# ---------------------------------------------------------------------------
# CooperativeTask — 协作任务数据类
# ---------------------------------------------------------------------------


@dataclass
class CooperativeTask:
    """一个协作任务，需要多只数码兽共同完成。

    Attributes:
        task_id: 唯一任务 ID。
        task_type: 任务类型 ("explore" / "defend" / "build" / "hunt")。
        title: 任务标题。
        description: 任务描述。
        required_participants: 最少需要的参与者数量 (≥2)。
        current_participants: 已加入的数码兽名字列表。
        sub_goals: 分配给各参与者的子目标 (agent_name → 子目标描述)。
        shared_reward: 共享奖励比例 (0.0-1.0)。
        individual_contributions: 各参与者贡献度 (agent_name → 贡献值)。
        status: 任务状态 ("pending" / "active" / "completed" / "failed")。
        tick_created: 创建时的世界 tick。
        tick_completed: 完成时的世界 tick，未完成则为 None。
        region_id: 任务所在区域 ID。
        position: 任务坐标 {"x": int, "y": int}。
        completion_threshold: 总贡献度达到此值即完成。
    """

    task_id: str
    task_type: str
    title: str
    description: str
    required_participants: int
    current_participants: list[str] = field(default_factory=list)
    sub_goals: dict[str, str] = field(default_factory=dict)
    shared_reward: float = DEFAULT_SHARED_REWARD
    individual_contributions: dict[str, float] = field(default_factory=dict)
    status: str = "pending"
    tick_created: int = 0
    tick_completed: int | None = None
    region_id: str = ""
    position: dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})
    completion_threshold: float = DEFAULT_COMPLETION_THRESHOLD

    def total_contribution(self) -> float:
        """计算所有参与者的总贡献度。"""
        return sum(self.individual_contributions.values())

    def is_fully_staffed(self) -> bool:
        """是否已达到所需参与者数量。"""
        return len(self.current_participants) >= self.required_participants

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "title": self.title,
            "description": self.description,
            "required_participants": self.required_participants,
            "current_participants": list(self.current_participants),
            "sub_goals": dict(self.sub_goals),
            "shared_reward": self.shared_reward,
            "individual_contributions": dict(self.individual_contributions),
            "status": self.status,
            "tick_created": self.tick_created,
            "tick_completed": self.tick_completed,
            "region_id": self.region_id,
            "position": dict(self.position),
            "completion_threshold": self.completion_threshold,
            "total_contribution": self.total_contribution(),
            "participant_count": len(self.current_participants),
        }


# ---------------------------------------------------------------------------
# CooperativeTaskRegistry — 全局任务注册表
# ---------------------------------------------------------------------------


class CooperativeTaskRegistry:
    """全局协作任务注册表。

    管理所有协作任务的生命周期:
    - 创建任务
    - 加入/离开任务
    - 分配子目标
    - 提交贡献
    - 检查完成
    - 查询（按区域、按参与者、活跃任务）
    """

    def __init__(self) -> None:
        self._tasks: dict[str, CooperativeTask] = {}
        self._by_region: dict[str, list[str]] = {}   # region_id → task_ids
        self._by_agent: dict[str, list[str]] = {}     # agent_name → task_ids
        self._task_counter: int = 0

    # ── 创建任务 ──────────────────────────────────

    def create_task(
        self,
        task_type: str,
        title: str,
        description: str,
        required_participants: int,
        region_id: str,
        position: dict[str, int] | None = None,
    ) -> CooperativeTask:
        """创建一个新的协作任务。

        Args:
            task_type: 任务类型 ("explore" / "defend" / "build" / "hunt")。
            title: 任务标题。
            description: 任务描述。
            required_participants: 最少需要参与者数 (≥2)。
            region_id: 任务所在区域 ID。
            position: 任务坐标。

        Returns:
            新创建的 CooperativeTask。

        Raises:
            ValueError: task_type 无效或 required_participants < 2。
        """
        if task_type not in TASK_TYPES:
            raise ValueError(f"无效任务类型 '{task_type}'，有效类型: {TASK_TYPES}")
        if required_participants < 2:
            raise ValueError(f"required_participants 必须 ≥2，收到 {required_participants}")

        self._task_counter += 1
        task_id = f"coop_{task_type}_{self._task_counter:04d}"

        task = CooperativeTask(
            task_id=task_id,
            task_type=task_type,
            title=title,
            description=description,
            required_participants=required_participants,
            region_id=region_id,
            position=position or {"x": 0, "y": 0},
            tick_created=0,
        )

        self._tasks[task_id] = task

        if region_id not in self._by_region:
            self._by_region[region_id] = []
        self._by_region[region_id].append(task_id)

        logger.debug("协作任务已创建: %s (%s, 需要%d名参与者)", task_id, task_type, required_participants)
        return task

    # ── 加入任务 ──────────────────────────────────

    def join_task(self, task_id: str, agent_name: str) -> bool:
        """让数码兽加入一个协作任务。

        Args:
            task_id: 任务 ID。
            agent_name: 数码兽名字。

        Returns:
            是否成功加入。
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning("join_task: 任务 '%s' 不存在", task_id)
            return False

        if task.status not in ("pending", "active"):
            logger.warning("join_task: 任务 '%s' 已结束 (状态=%s)", task_id, task.status)
            return False

        if agent_name in task.current_participants:
            logger.debug("join_task: '%s' 已在任务 '%s' 中", agent_name, task_id)
            return False

        if len(task.current_participants) >= MAX_PARTICIPANTS_PER_TASK:
            logger.warning("join_task: 任务 '%s' 已达最大参与者数 %d", task_id, MAX_PARTICIPANTS_PER_TASK)
            return False

        task.current_participants.append(agent_name)
        task.individual_contributions[agent_name] = 0.0

        if agent_name not in self._by_agent:
            self._by_agent[agent_name] = []
        self._by_agent[agent_name].append(task_id)

        # 自动激活
        if task.is_fully_staffed() and task.status == "pending":
            task.status = "active"

        logger.debug("'%s' 已加入任务 '%s'", agent_name, task_id)
        return True

    # ── 分配子目标 ────────────────────────────────

    def assign_sub_goals(self, task_id: str) -> dict[str, str]:
        """为任务的所有参与者分配子目标。

        根据任务类型和参与者在列表中的位置分配不同的子目标。

        Args:
            task_id: 任务 ID。

        Returns:
            agent_name → 子目标描述 的字典。
        """
        task = self._tasks.get(task_id)
        if task is None:
            return {}

        sub_goal_options: dict[str, list[str]] = {
            "explore": ["侦察前方地形", "标记安全路线", "收集环境数据", "绘制区域地图"],
            "defend": ["守卫北侧防线", "阻击敌人前锋", "掩护队友侧翼", "固守要害阵地"],
            "build": ["搬运建筑材料", "搭建主体结构", "加固关键节点", "装饰外观细节"],
            "hunt": ["追踪目标踪迹", "设置包围圈", "正面吸引注意", "从侧面发起攻击"],
        }

        options = sub_goal_options.get(task.task_type, ["完成分配的任务"])

        for i, agent_name in enumerate(task.current_participants):
            if agent_name not in task.sub_goals:
                task.sub_goals[agent_name] = options[i % len(options)]

        return dict(task.sub_goals)

    # ── 贡献度 ────────────────────────────────────

    def contribute(self, task_id: str, agent_name: str, amount: float) -> bool:
        """为任务贡献进度。

        Args:
            task_id: 任务 ID。
            agent_name: 贡献者名字。
            amount: 贡献值 (>0)。

        Returns:
            是否成功提交贡献。
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning("contribute: 任务 '%s' 不存在", task_id)
            return False

        if task.status != "active":
            logger.warning("contribute: 任务 '%s' 未激活 (状态=%s)", task_id, task.status)
            return False

        if agent_name not in task.current_participants:
            logger.warning("contribute: '%s' 未参与任务 '%s'", agent_name, task_id)
            return False

        if amount <= 0:
            logger.warning("contribute: 贡献值必须 >0，收到 %f", amount)
            return False

        task.individual_contributions[agent_name] = task.individual_contributions.get(agent_name, 0.0) + amount
        logger.debug("'%s' 向任务 '%s' 贡献了 %.2f (总计: %.2f)", agent_name, task_id, amount, task.individual_contributions[agent_name])
        return True

    # ── 检查完成 ──────────────────────────────────

    def check_completion(self, task_id: str) -> dict[str, Any]:
        """检查任务是否完成，并在完成时分配奖励。

        Args:
            task_id: 任务 ID。

        Returns:
            {
                "task_id": str,
                "completed": bool,
                "total_contribution": float,
                "threshold": float,
                "rewards": {agent_name: float},  # 仅在完成时返回
                "message": str,
            }
        """
        task = self._tasks.get(task_id)
        if task is None:
            return {"task_id": task_id, "completed": False, "total_contribution": 0.0, "threshold": 0.0, "message": "任务不存在"}

        total = task.total_contribution()

        if total >= task.completion_threshold:
            task.status = "completed"
            # 计算奖励分配: 基础奖励 = threshold * (1 - shared_reward) + 各人贡献占比 * shared_reward
            base_reward = task.completion_threshold
            individual_reward = base_reward * (1.0 - task.shared_reward)  # 每人保底
            shared_pool = base_reward * task.shared_reward  # 按贡献比例分配

            rewards: dict[str, float] = {}
            for agent_name, contrib in task.individual_contributions.items():
                share = (contrib / total) * shared_pool if total > 0 else 0.0
                rewards[agent_name] = individual_reward + share

            logger.info("任务 '%s' 已完成! 总贡献: %.2f / %.2f", task_id, total, task.completion_threshold)
            return {
                "task_id": task_id,
                "completed": True,
                "total_contribution": total,
                "threshold": task.completion_threshold,
                "rewards": rewards,
                "message": f"任务已完成! {len(rewards)}名参与者获得奖励。",
            }

        return {
            "task_id": task_id,
            "completed": False,
            "total_contribution": total,
            "threshold": task.completion_threshold,
            "message": f"进度: {total:.2f}/{task.completion_threshold}",
        }

    # ── 查询 ──────────────────────────────────────

    def get_task(self, task_id: str) -> CooperativeTask | None:
        """获取单个任务。"""
        return self._tasks.get(task_id)

    def get_active_tasks(self) -> list[CooperativeTask]:
        """获取所有活跃任务 (pending 或 active)。"""
        return [t for t in self._tasks.values() if t.status in ("pending", "active")]

    def get_all_tasks(self) -> list[CooperativeTask]:
        """获取所有任务（包括已完成的）。"""
        return list(self._tasks.values())

    def get_tasks_by_region(self, region_id: str) -> list[CooperativeTask]:
        """获取指定区域的所有任务。"""
        task_ids = self._by_region.get(region_id, [])
        return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    def get_agent_tasks(self, agent_name: str) -> list[CooperativeTask]:
        """获取某数码兽参与的所有任务。"""
        task_ids = self._by_agent.get(agent_name, [])
        return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    def task_count(self) -> int:
        """任务总数。"""
        return len(self._tasks)

    def active_count(self) -> int:
        """活跃任务数。"""
        return len(self.get_active_tasks())

    # ── 序列化 ────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """序列化所有任务。"""
        return {
            "total_tasks": self.task_count(),
            "active_tasks": self.active_count(),
            "tasks": [t.to_dict() for t in self._tasks.values()],
        }

    # ── 重置 ──────────────────────────────────────

    def reset(self) -> None:
        """重置所有内部状态（测试用）。"""
        self._tasks.clear()
        self._by_region.clear()
        self._by_agent.clear()
        self._task_counter = 0
        logger.debug("CooperativeTaskRegistry: 已重置")


# ---------------------------------------------------------------------------
# TaskGenerationEngine — 任务生成引擎
# ---------------------------------------------------------------------------


class TaskGenerationEngine:
    """协作任务生成引擎。

    根据世界状态、数码兽分布和关系网络自动生成协作任务。

    生成策略:
    - 选址: 随机选择一个区域
    - 选类型: 根据区域特性选择任务类型
    - 选参与者: 按 proximity + 关系距离 选择
    - 只有找到 ≥2 只邻近数码兽时才生成任务
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def generate_random_task(
        self,
        world_state: Any,
        agents: list[Any],
        tick_count: int,
    ) -> CooperativeTask | None:
        """生成一个随机协作任务。

        Args:
            world_state: WorldState 实例 (有 .regions 属性)。
            agents: DigimonAgent 列表。
            tick_count: 当前世界 tick。

        Returns:
            CooperativeTask 或 None (若无合适条件)。
        """
        if len(agents) < 2:
            return None

        # 1. 选址: 随机选择一个区域
        regions = getattr(world_state, "regions", {})
        if not regions:
            return None

        region_ids = list(regions.keys())
        chosen_region_id = self._rng.choice(region_ids)
        region = regions[chosen_region_id]

        # 获取区域边界，用于生成随机位置
        bounds = getattr(region, "bounds", (0, 0, 4000, 3000))
        pos_x = self._rng.randint(bounds[0], bounds[2])
        pos_y = self._rng.randint(bounds[1], bounds[3])

        # 2. 选类型: 根据区域特性选择
        preferred_types = REGION_TASK_PREFERENCES.get(chosen_region_id, list(TASK_TYPES))
        task_type = self._rng.choice(preferred_types)

        # 3. 选参与者: proximity 优先
        candidates = self._select_candidates(agents, pos_x, pos_y)
        if len(candidates) < 2:
            return None

        required = min(self._rng.randint(2, max(2, len(candidates))), MAX_PARTICIPANTS_PER_TASK)
        participants = candidates[:required]

        # 4. 生成标题和描述
        region_name = getattr(region, "name", chosen_region_id)
        title = self._rng.choice(TASK_TITLE_TEMPLATES[task_type]).format(region=region_name)
        description = self._rng.choice(TASK_DESC_TEMPLATES[task_type]).format(region=region_name)

        # 5. 创建任务
        task = CooperativeTask(
            task_id=f"coop_{task_type}_{tick_count:06d}_{self._rng.randint(1000, 9999)}",
            task_type=task_type,
            title=title,
            description=description,
            required_participants=required,
            current_participants=list(participants),
            sub_goals={},
            shared_reward=DEFAULT_SHARED_REWARD,
            individual_contributions=dict.fromkeys(participants, 0.0),
            status="active",
            tick_created=tick_count,
            region_id=chosen_region_id,
            position={"x": pos_x, "y": pos_y},
            completion_threshold=DEFAULT_COMPLETION_THRESHOLD * required,
        )

        # 分配子目标
        sub_goal_options: dict[str, list[str]] = {
            "explore": ["侦察前方地形", "标记安全路线", "收集环境数据", "绘制区域地图"],
            "defend": ["守卫北侧防线", "阻击敌人前锋", "掩护队友侧翼", "固守要害阵地"],
            "build": ["搬运建筑材料", "搭建主体结构", "加固关键节点", "装饰外观细节"],
            "hunt": ["追踪目标踪迹", "设置包围圈", "正面吸引注意", "从侧面发起攻击"],
        }
        options = sub_goal_options.get(task_type, ["完成分配的任务"])
        for i, p in enumerate(participants):
            task.sub_goals[p] = options[i % len(options)]

        logger.info("生成协作任务: %s (区域=%s, 参与者=%s)", task.task_id, chosen_region_id, participants)
        return task

    def _select_candidates(
        self,
        agents: list[Any],
        center_x: int,
        center_y: int,
        max_distance: float = 800.0,
    ) -> list[str]:
        """按 proximity 选择候选参与者。

        距离中心越近的数码兽排名越靠前。

        Args:
            agents: DigimonAgent 列表。
            center_x: 任务中心 x 坐标。
            center_y: 任务中心 y 坐标。
            max_distance: 最大距离阈值。

        Returns:
            按距离排序的 agent 名字列表。
        """
        scored: list[tuple[float, str]] = []
        for agent in agents:
            location = getattr(agent, "location", (0, 0))
            if isinstance(location, (list, tuple)) and len(location) >= 2:
                ax, ay = location[0], location[1]
            else:
                ax, ay = 0, 0

            dist = ((ax - center_x) ** 2 + (ay - center_y) ** 2) ** 0.5
            if dist <= max_distance:
                scored.append((dist, getattr(agent, "name", "unknown")))

        scored.sort(key=lambda item: item[0])
        return [name for _, name in scored]

    def scan_for_opportunities(
        self,
        world_state: Any,
        agents: list[Any],
        tick_count: int,
        relationships: Any | None = None,
    ) -> list[CooperativeTask]:
        """扫描整个世界寻找协作机会。

        遍历所有区域，尝试生成协作任务。

        Args:
            world_state: WorldState 实例。
            agents: DigimonAgent 列表。
            tick_count: 当前世界 tick。
            relationships: RelationshipTracker (可选，用于关系距离排序)。

        Returns:
            最多 DEFAULT_SCAN_MAX_TASKS 个新生成的任务。
        """
        if len(agents) < 2:
            return []

        regions = getattr(world_state, "regions", {})
        if not regions:
            return []

        tasks: list[CooperativeTask] = []
        tried_regions: set[str] = set()

        # 随机打乱区域顺序
        region_ids = list(regions.keys())
        self._rng.shuffle(region_ids)

        for region_id in region_ids:
            if len(tasks) >= DEFAULT_SCAN_MAX_TASKS:
                break
            if region_id in tried_regions:
                continue
            tried_regions.add(region_id)

            task = self.generate_random_task(world_state, agents, tick_count)
            if task is not None and task.region_id == region_id:
                # 如果关系的因素可用，按关系距离重排序参与者
                if relationships is not None and len(task.current_participants) >= 2:
                    task.current_participants = self._rank_by_relationships(
                        task.current_participants,
                        relationships,
                    )
                tasks.append(task)

        return tasks

    def _rank_by_relationships(
        self,
        participants: list[str],
        relationships: Any,
    ) -> list[str]:
        """按关系距离重新排序参与者，关系紧密的排在前面。

        Args:
            participants: 参与者名字列表。
            relationships: RelationshipTracker 实例。

        Returns:
            重新排序后的列表。
        """
        if len(participants) <= 1:
            return list(participants)

        # 以第一个参与者为锚点，按关系亲密度排序
        anchor = participants[0]
        scored: list[tuple[float, str]] = []

        for name in participants:
            if name == anchor:
                scored.append((0.0, name))
            else:
                # 获取关系强度
                try:
                    rel = getattr(relationships, "get_relationship", None)
                    if callable(rel):
                        relation = rel(anchor, name)
                        affinity = getattr(relation, "affinity", 0.5) if relation else 0.5
                    else:
                        affinity = 0.5
                except Exception:
                    affinity = 0.5
                scored.append((1.0 - affinity, name))  # 高亲和力 = 低距离

        scored.sort(key=lambda item: item[0])
        return [name for _, name in scored]


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_registry: CooperativeTaskRegistry | None = None


def get_cooperative_registry() -> CooperativeTaskRegistry:
    """获取全局协作任务注册表单例。

    首次调用时自动创建。用于 scheduler / API 端点访问。

    Returns:
        CooperativeTaskRegistry 单例。
    """
    global _registry
    if _registry is None:
        _registry = CooperativeTaskRegistry()
    return _registry


def reset_cooperative_registry() -> None:
    """重置全局协作任务注册表（测试专用）。

    清空所有任务，使下一次 get_cooperative_registry() 创建全新实例。
    """
    global _registry
    _registry = None

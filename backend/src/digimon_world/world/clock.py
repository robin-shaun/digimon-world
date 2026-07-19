"""
WorldClock - 世界时钟
======================

世界有自己的时间流逝速率,独立于现实时间。
默认 1 秒现实时间 = 1 分钟世界时间(可调)。

参考 Stanford Generative Agents 的 "global_time" 概念:
他们把 "步" 折算成"分钟",以方便观察/反思/计划的判断。

设计要点:
- 用 datetime 存世界当前时刻 + tick() 推进
- 提供 elapsed_minutes / format_clock 方便日志/UI
- 纯同步函数,无 asyncio 依赖(方便测试)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class WorldClock:
    """世界时钟。

    Attributes:
        start: 世界纪元起点(现实 wallclock,启动时记录)
        real_to_world_ratio: 1 秒现实 → 多少秒世界
        now: 当前世界时刻(初始 = start)
        paused: 是否暂停(测试 / 调试用)
    """

    start: datetime = field(default_factory=datetime.utcnow)
    real_to_world_ratio: int = 60
    now: datetime | None = None
    paused: bool = False

    def __post_init__(self) -> None:
        if self.now is None:
            self.now = self.start

    def tick(self, real_seconds: float = 1.0) -> datetime:
        """推进世界时钟。返回推进后的世界时刻。"""
        if self.paused:
            return self.now  # type: ignore[return-value]
        delta = timedelta(seconds=real_seconds * self.real_to_world_ratio)
        self.now = self.now + delta  # type: ignore[operator]
        return self.now  # type: ignore[return-value]

    @property
    def elapsed_minutes(self) -> int:
        """从 start 起已经流逝的世界分钟数。"""
        if self.now is None:
            return 0
        return int((self.now - self.start).total_seconds() // 60)

    def format_clock(self) -> str:
        """人类可读的世界时刻。Phase 4 可换成"数码世界时间"(自定义历法)。"""
        if self.now is None:
            return "?"
        return self.now.strftime("%Y-%m-%d %H:%M:%S")

    def reset(self) -> None:
        """重置到起点(测试用)。"""
        self.now = self.start
        self.paused = False

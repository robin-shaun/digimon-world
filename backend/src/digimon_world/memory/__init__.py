"""记忆流: 数码兽 / NPC 的长期记忆系统。

参考 Stanford Generative Agents 的 memory_stream.py。

核心概念:
- MemoryNode: 一条记忆(时间戳 + 内容 + 重要性)
- MemoryStream: 一个 agent 的全部记忆
- 检索: 时序近因 + 重要性 + 关联性 三维评分
- 反思触发: 当重要性累积和超阈值

Phase 18: 记忆自主规划
- MemoryAutonomy: 主入口类
- ImportanceAssessor: LLM 自评重要性
- ForgettingEngine: Ebbinghaus 遗忘曲线
- MemoryRehearsal: 记忆复述机制
- MemoryUpdateDetector: 记忆过期检测

Phase 20: 自进化世界模型 (WorldEvolver, arXiv:2606.30639)
- WorldModel: 主入口类, per-agent 实例
- EpisodicMemory: 情节记忆 (状态→动作→结果 转换记录)
- SemanticMemory: 语义记忆 (从情节中提取的启发式规则)
- SelectiveForesight: 选择性前瞻引擎 (融合情节+规则进行预测)
- Episode: 单条情节记忆数据结构
- Rule: 单条语义规则数据结构

详细设计: docs/DESIGN.md 第 3.2 节
"""
from .memory_stream import MemoryNode, MemoryStream
from .memory_autonomy import (
    EbbinghausCurve,
    ForgettingEngine,
    ImportanceAssessor,
    MemoryAutonomy,
    MemoryHealth,
    MemoryRehearsal,
    MemoryUpdateDetector,
)

from .world_model import (
    Episode,
    EpisodicMemory,
    PredictionResult,
    Rule,
    SelectiveForesight,
    SemanticMemory,
    WorldModel,
)

__all__ = [
    "EbbinghausCurve",
    "Episode",
    "EpisodicMemory",
    "ForgettingEngine",
    "ImportanceAssessor",
    "MemoryAutonomy",
    "MemoryHealth",
    "MemoryNode",
    "MemoryRehearsal",
    "MemoryStream",
    "MemoryUpdateDetector",
    "PredictionResult",
    "Rule",
    "SelectiveForesight",
    "SemanticMemory",
    "WorldModel",
]

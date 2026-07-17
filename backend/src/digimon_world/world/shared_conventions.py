"""
共享记忆惯例与文化涌现 — Phase 22 核心模块
==========================================

当多个 agent 通过持久化记忆反复交互时，自然发展出共享符号系统和文化惯例。
受 arXiv:2607.00233 启发——记忆架构驱动语言涌现。

三大组件:
1. ConventionDetector — 检测 2+ agent 重复使用的术语/行为模式
2. ConventionPool — 全局共享惯例池，每个惯例有 adoption_count + decay 曲线
3. ConventionPropagation — 按社交网络传播惯例到邻近 agent

设计要点:
- 检测基于文本分析（无需 LLM），保证每 tick 开销可控
- 惯例有自己的生命周期: 涌现 → 传播 → 衰减 → 消亡
- 与 RelationalCircle 集成：关系越近，惯例传播越快
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import string
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

import jieba

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

# 惯例衰减半衰期（秒）—— 默认 4 小时不被采用则开始衰减
CONVENTION_HALF_LIFE_DEFAULT = 4 * 3600.0  # 4 小时

# 惯例强度阈值：低于此值视为消亡，从活跃池中移除
CONVENTION_EXTINCTION_THRESHOLD = 0.1

# 检测用：中文词最小长度（字符数）
MIN_CHINESE_WORD_LENGTH = 2

# 检测用：英文词最小长度
MIN_ENGLISH_WORD_LENGTH = 4

# 检测用：至少被 N 个 agent 使用才算惯例
MIN_AGENTS_FOR_CONVENTION = 2

# 传播权重：关系距离 → 传播概率倍率
RELATIONAL_PROPAGATION_WEIGHTS = {
    "inner": 1.0,       # 内圈: 100% 概率
    "middle": 0.6,      # 中圈: 60%
    "outer": 0.3,       # 外圈: 30%
    "stranger": 0.05,   # 陌生人: 5%
}

# 每次检测最多产生的惯例数（防止爆炸）
MAX_NEW_CONVENTIONS_PER_TICK = 5

# 清理：每 N 个 tick 清理一次过期惯例
CONVENTION_CLEANUP_INTERVAL = 12  # ~每天一次 (12 tick = 12h 世界时间)


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────

@dataclass
class Convention:
    """一条共享惯例。"""

    convention_id: str                          # 唯一标识 (hash of term)
    term: str                                  # 惯例文本（术语/行为描述）
    category: str = "term"                     # term | behavior | ritual
    source_agents: list[str] = field(default_factory=list)  # 最初使用的 agent 名
    adopter_agents: list[str] = field(default_factory=list)  # 所有采用者
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_used: datetime = field(default_factory=datetime.utcnow)
    use_count: int = 0                         # 总使用次数（所有 agent 汇总）
    strength: float = 1.0                      # 当前强度 (0-1)，衰减曲线
    half_life_seconds: float = CONVENTION_HALF_LIFE_DEFAULT

    @property
    def adoption_count(self) -> int:
        """采用该惯例的 agent 数量。"""
        return len(self.adopter_agents)

    @property
    def is_active(self) -> bool:
        """是否活跃（未消亡）。"""
        return self.strength > CONVENTION_EXTINCTION_THRESHOLD

    def compute_strength(self, now: datetime | None = None) -> float:
        """计算当前强度: S = S0 * e^(-Δt / half_life)

        每次被使用时强度重置为 1.0，不使用时按半衰期衰减。
        """
        if now is None:
            now = datetime.utcnow()
        elapsed = (now - self.last_used).total_seconds()
        if elapsed <= 0:
            return 1.0
        return math.exp(-elapsed / self.half_life_seconds)


# ──────────────────────────────────────────────
# ConventionDetector
# ──────────────────────────────────────────────

class ConventionDetector:
    """从 agent 记忆流和交互中检测共享术语/行为模式。

    检测策略:
    1. 扫描所有 agent 的 memory_stream，提取高频词/短语
    2. 统计每个词在多少个 agent 中出现
    3. 满足 MIN_AGENTS_FOR_CONVENTION 的候选进入惯例池
    4. 过滤掉常见停用词（避免噪声）

    不依赖 LLM —— 纯文本统计，适合高频调用。
    """

    # 中文停用词（高频但无意义）
    CHINESE_STOP_WORDS: set[str] = {
        "一个", "一起", "一些", "什么", "没有", "可以", "已经", "不是",
        "这个", "那个", "这里", "那里", "怎么", "因为", "所以", "但是",
        "如果", "虽然", "然后", "并且", "或者", "不过", "还是", "只是",
        "自己", "我们", "他们", "它们", "你们", "大家", "所有", "任何",
        "现在", "马上", "正在", "已经", "就要", "忽然", "突然", "终于",
        "开始", "继续", "结束", "完成", "发现", "看见", "听到", "觉得",
        "应该", "能够", "需要", "想要", "希望", "喜欢", "讨厌", "害怕",
        "可能", "也许", "一定", "必须", "当然", "果然", "竟然", "居然",
    }

    # 英文停用词
    ENGLISH_STOP_WORDS: set[str] = {
        "the", "and", "for", "that", "have", "with", "this", "from",
        "they", "will", "would", "there", "their", "what", "about",
        "which", "when", "make", "like", "just", "been", "into", "has",
        "more", "some", "could", "other", "than", "then", "also", "very",
        "only", "over", "such", "between", "after", "should", "these",
    }

    def detect(
        self,
        agents: list[Any],  # list[DigimonAgent]
        existing_pool: dict[str, Convention] | None = None,
    ) -> list[Convention]:
        """从 agent 记忆中检测新的共享惯例。

        Args:
            agents: 所有活跃 agent 列表
            existing_pool: 已有的惯例池（用于去重）

        Returns:
            新检测到的惯例列表（已去重）
        """
        # 1. 收集所有 agent 的记忆文本
        agent_texts: dict[str, list[str]] = {}
        for agent in agents:
            texts = self._extract_texts_from_agent(agent)
            if texts:
                agent_texts[agent.name] = texts

        if len(agent_texts) < MIN_AGENTS_FOR_CONVENTION:
            return []

        # 2. 提取每个 agent 的词频
        agent_words: dict[str, Counter[str]] = {}
        for name, texts in agent_texts.items():
            words = self._tokenize(" ".join(texts))
            agent_words[name] = Counter(words)

        # 3. 跨 agent 统计
        word_agent_count: Counter[str] = Counter()
        word_total_count: Counter[str] = Counter()
        for name, wc in agent_words.items():
            for word in wc:
                word_agent_count[word] += 1
                word_total_count[word] += wc[word]

        # 4. 筛选候选惯例
        existing_ids = set(existing_pool.keys()) if existing_pool else set()
        candidates = []
        for word, agent_count in word_agent_count.most_common(100):
            if agent_count < MIN_AGENTS_FOR_CONVENTION:
                continue
            if word in self.CHINESE_STOP_WORDS or word in self.ENGLISH_STOP_WORDS:
                continue
            cid = self._make_id(word)
            if cid in existing_ids:
                continue
            candidates.append((word, agent_count, word_total_count[word]))

        # 5. 取 top N 返回
        candidates.sort(key=lambda x: x[2], reverse=True)
        new_conventions = []
        for term, agent_count, total_count in candidates[:MAX_NEW_CONVENTIONS_PER_TICK]:
            # 找到使用该术语的 source agents
            sources = [
                name for name, wc in agent_words.items()
                if term in wc
            ]
            conv = Convention(
                convention_id=self._make_id(term),
                term=term,
                category=self._classify(term),
                source_agents=sources[:],
                adopter_agents=sources[:],
                use_count=total_count,
            )
            new_conventions.append(conv)
            logger.debug(
                "ConventionDetector: new convention '%s' detected in %d agents "
                "(total uses: %d)",
                term, len(sources), total_count,
            )

        return new_conventions

    def detect_from_interaction(
        self,
        speaker_agent: str,
        listener_agent: str,
        dialogue_line: str,
        existing_pool: dict[str, Convention] | None = None,
    ) -> list[Convention]:
        """从单次对话中检测惯例（轻量版）。

        在对话发生时增量检测，避免全量扫描。
        """
        words = self._tokenize(dialogue_line)
        if not words:
            return []

        existing_ids = set(existing_pool.keys()) if existing_pool else set()
        new_conventions = []

        for word in set(words):
            if word in self.CHINESE_STOP_WORDS or word in self.ENGLISH_STOP_WORDS:
                continue
            if len(word) < MIN_CHINESE_WORD_LENGTH:
                continue
            cid = self._make_id(word)
            if cid in existing_ids:
                # 已存在 → 不算新，但由 ConventionPool.notify_use 更新
                continue
            # 增量检测需要至少 2 个不同 agent 使用才标记
            # 但因为这是从单条对话来的，只有 speaker+listener 两个 agent
            # 所以需要检查是否已有其他 agent 用过类似词
            # 简化：对话中的词标记为候选，由 pool 的跨轮聚合决定是否升级
            conv = Convention(
                convention_id=cid,
                term=word,
                category=self._classify(word),
                source_agents=[speaker_agent, listener_agent],
                adopter_agents=[speaker_agent, listener_agent],
                use_count=1,
            )
            new_conventions.append(conv)

        return new_conventions

    # ── 辅助方法 ──

    def _extract_texts_from_agent(self, agent: Any) -> list[str]:
        """从 agent 记忆中提取文本。"""
        texts = []
        if hasattr(agent, "memory") and hasattr(agent.memory, "entries"):
            for entry in agent.memory.entries[-50:]:  # 最近 50 条
                desc = getattr(entry, "description", "")
                if desc:
                    texts.append(desc)
        return texts

    def _tokenize(self, text: str) -> list[str]:
        """分词：jieba 中文分词 + 英文词提取。

        使用 jieba 精准模式进行中文分词，过滤掉单字词和停用词。
        """
        words = []
        # 中文分词 (jieba 精准模式)
        for word in jieba.cut(text, cut_all=False):
            word = word.strip()
            if len(word) < MIN_CHINESE_WORD_LENGTH:
                continue
            if word in self.CHINESE_STOP_WORDS:
                continue
            # 过滤纯标点/数字
            if all(c in string.punctuation or c in string.digits or c.isspace() for c in word):
                continue
            words.append(word)
        # 英文词: 4+ 字母
        for match in re.finditer(r'[a-zA-Z]{4,}', text.lower()):
            w = match.group()
            if w not in self.ENGLISH_STOP_WORDS:
                words.append(w)
        return words

    def _classify(self, term: str) -> str:
        """分类惯例类型。"""
        # 先检查仪式类（因为"进化祭"含"进化"，但应先归类为 ritual）
        ritual_keywords = ["聚集", "庆祝", "纪念", "仪式", "祭",
                           "大会", "集会", "约定", "节日", "狂欢"]
        for kw in ritual_keywords:
            if kw in term:
                return "ritual"
        # 行为动词
        behavior_keywords = ["攻击", "防御", "逃跑", "寻找", "探索",
                             "收集", "治疗", "训练", "进化", "战斗",
                             "移动", "觅食", "巡逻", "侦察", "埋伏"]
        for kw in behavior_keywords:
            if kw in term:
                return "behavior"
        return "term"

    @staticmethod
    def _make_id(term: str) -> str:
        """生成惯例唯一 ID。"""
        return hashlib.sha256(term.encode()).hexdigest()[:16]


# ──────────────────────────────────────────────
# ConventionPool
# ──────────────────────────────────────────────

class ConventionPool:
    """全局共享惯例池。

    功能:
    - 注册新惯例
    - 更新惯例使用（重置衰减时钟）
    - 周期性衰减
    - 查询: 按 agent、按热度、按类别
    """

    def __init__(self):
        self._conventions: dict[str, Convention] = {}
        self.detector = ConventionDetector()
        self._ticks_since_cleanup = 0
        self._total_conventions_ever = 0  # 历史累计惯例数

    # ── 注册与更新 ──

    def register(self, convention: Convention) -> Convention:
        """注册新惯例。如果已存在则忽略。"""
        cid = convention.convention_id
        if cid in self._conventions:
            return self._conventions[cid]
        self._conventions[cid] = convention
        self._total_conventions_ever += 1
        logger.info(
            "ConventionPool: registered '%s' (id=%s), category=%s, "
            "adopters=%d",
            convention.term, cid, convention.category,
            convention.adoption_count,
        )
        return convention

    def register_batch(self, conventions: list[Convention]) -> int:
        """批量注册，返回新增数量。"""
        count = 0
        for conv in conventions:
            if conv.convention_id not in self._conventions:
                self.register(conv)
                count += 1
        return count

    def notify_use(
        self, convention_id: str, agent_name: str, timestamp: datetime | None = None
    ) -> bool:
        """通知某惯例被某 agent 使用。重置衰减、增加计数。

        Returns:
            True 如果惯例存在且被成功更新。
        """
        conv = self._conventions.get(convention_id)
        if conv is None:
            return False

        now = timestamp or datetime.utcnow()
        conv.last_used = now
        conv.use_count += 1
        conv.strength = 1.0  # 使用 → 强度重置

        if agent_name not in conv.adopter_agents:
            conv.adopter_agents.append(agent_name)

        return True

    def adopt(
        self, convention_id: str, agent_name: str, timestamp: datetime | None = None
    ) -> bool:
        """agent 新采用某惯例。"""
        conv = self._conventions.get(convention_id)
        if conv is None:
            return False

        now = timestamp or datetime.utcnow()
        if agent_name not in conv.adopter_agents:
            conv.adopter_agents.append(agent_name)
            conv.last_used = now
            conv.use_count += 1
            conv.strength = 1.0
            logger.info(
                "ConventionPool: agent '%s' adopted '%s' "
                "(now %d adopters)",
                agent_name, conv.term, conv.adoption_count,
            )
        return True

    # ── 衰减 ──

    def decay_all(self) -> int:
        """对所有惯例执行一次衰减更新。返回活跃惯例数。"""
        now = datetime.utcnow()
        active = 0
        for conv in self._conventions.values():
            conv.strength = conv.compute_strength(now)
            if conv.is_active:
                active += 1
        return active

    def cleanup(self) -> int:
        """移除已消亡的惯例。返回移除数量。"""
        dead_ids = [
            cid for cid, conv in self._conventions.items()
            if not conv.is_active
        ]
        for cid in dead_ids:
            conv = self._conventions.pop(cid)
            logger.info(
                "ConventionPool: convention '%s' went extinct "
                "(strength=%.3f, adopters=%d)",
                conv.term, conv.strength, conv.adoption_count,
            )
        return len(dead_ids)

    def tick(self, agents: list[Any]) -> dict[str, Any]:
        """每个世界 tick 调用一次。

        执行:
        1. 检测新惯例
        2. 衰减所有现有惯例
        3. 定期清理消亡惯例

        Returns:
            诊断报告
        """
        # 1. 检测
        new_convs = self.detector.detect(agents, self._conventions)
        new_count = self.register_batch(new_convs)

        # 2. 衰减
        active = self.decay_all()

        # 3. 定期清理
        cleaned = 0
        self._ticks_since_cleanup += 1
        if self._ticks_since_cleanup >= CONVENTION_CLEANUP_INTERVAL:
            cleaned = self.cleanup()
            self._ticks_since_cleanup = 0

        return {
            "total_ever": self._total_conventions_ever,
            "active": active,
            "new_this_tick": new_count,
            "cleaned": cleaned,
        }

    # ── 查询 ──

    def get(self, convention_id: str) -> Convention | None:
        """获取单条惯例。"""
        return self._conventions.get(convention_id)

    def get_by_agent(self, agent_name: str) -> list[Convention]:
        """获取某 agent 采用的所有惯例。"""
        return [
            conv for conv in self._conventions.values()
            if agent_name in conv.adopter_agents
        ]

    def get_active(
        self, sort_by: str = "adoption_count", limit: int = 50
    ) -> list[Convention]:
        """获取活跃惯例列表。

        Args:
            sort_by: 排序方式 — "adoption_count" | "strength" | "use_count" | "recent"
            limit: 返回上限
        """
        active = [c for c in self._conventions.values() if c.is_active]
        if sort_by == "strength":
            active.sort(key=lambda c: c.strength, reverse=True)
        elif sort_by == "use_count":
            active.sort(key=lambda c: c.use_count, reverse=True)
        elif sort_by == "recent":
            active.sort(key=lambda c: c.last_used, reverse=True)
        else:  # adoption_count
            active.sort(key=lambda c: c.adoption_count, reverse=True)
        return active[:limit]

    def get_by_category(self, category: str) -> list[Convention]:
        """按惯例类别过滤。"""
        return [
            c for c in self._conventions.values()
            if c.category == category and c.is_active
        ]

    def stats(self) -> dict[str, Any]:
        """惯例池统计信息。"""
        active = sum(1 for c in self._conventions.values() if c.is_active)
        dead = len(self._conventions) - active
        categories = Counter(c.category for c in self._conventions.values() if c.is_active)
        total_adoptions = sum(c.adoption_count for c in self._conventions.values() if c.is_active)
        return {
            "total_ever": self._total_conventions_ever,
            "active": active,
            "extinct": dead,
            "by_category": dict(categories),
            "total_adoptions": total_adoptions,
            "avg_adoptions": (
                round(total_adoptions / active, 1) if active > 0 else 0
            ),
        }


# ──────────────────────────────────────────────
# ConventionPropagation
# ──────────────────────────────────────────────

class ConventionPropagation:
    """按社交网络传播惯例。

    当两个 agent 交互时（对话、战斗、组队），检查一方是否拥有另一方尚未
    采用的惯例。传播概率由关系距离（RelationalCircle）决定。
    """

    def __init__(self, pool: ConventionPool):
        self.pool = pool

    def propagate_on_interaction(
        self,
        agent_a: str,
        agent_b: str,
        relation_distance: str = "stranger",
    ) -> int:
        """在 agent_a ↔ agent_b 交互时尝试传播惯例。

        Args:
            agent_a: agent A 名称
            agent_b: agent B 名称
            relation_distance: A→B 的关系距离 (inner|middle|outer|stranger)

        Returns:
            传播成功的惯例数
        """
        # 获取双方的惯例
        a_convs = set(c.convention_id for c in self.pool.get_by_agent(agent_a))
        b_convs = set(c.convention_id for c in self.pool.get_by_agent(agent_b))

        # A 有但 B 没有 → 尝试从 A 传播给 B
        a_only = a_convs - b_convs
        b_only = b_convs - a_convs

        # 传播概率权重
        weight = RELATIONAL_PROPAGATION_WEIGHTS.get(relation_distance, 0.1)

        propagated = 0
        import random

        # A → B
        for cid in a_only:
            if random.random() < weight:
                if self.pool.adopt(cid, agent_b):
                    propagated += 1

        # B → A
        for cid in b_only:
            if random.random() < weight:
                if self.pool.adopt(cid, agent_a):
                    propagated += 1

        if propagated > 0:
            logger.debug(
                "ConventionPropagation: %s↔%s (distance=%s) spread %d conventions",
                agent_a, agent_b, relation_distance, propagated,
            )

        return propagated


# ──────────────────────────────────────────────
# 单例
# ──────────────────────────────────────────────

_pool_instance: ConventionPool | None = None
_propagation_instance: ConventionPropagation | None = None


def get_convention_pool() -> ConventionPool:
    """获取全局惯例池单例。"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = ConventionPool()
    return _pool_instance


def get_convention_propagation() -> ConventionPropagation:
    """获取全局惯例传播引擎单例。"""
    global _propagation_instance
    if _propagation_instance is None:
        _propagation_instance = ConventionPropagation(get_convention_pool())
    return _propagation_instance


def reset_convention_pool() -> None:
    """重置惯例池（测试用）。"""
    global _pool_instance, _propagation_instance
    _pool_instance = None
    _propagation_instance = None

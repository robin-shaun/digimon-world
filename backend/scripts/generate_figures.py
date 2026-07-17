#!/usr/bin/env python3
"""
论文图表生成 — 从对照实验 JSON 生成 4 张论文级图表
===================================================

跑法:
    cd backend
    source .venv/bin/activate
    python scripts/generate_figures.py

输入:  backend/data/paper_experiment_results.json
输出:  docs/figures/fig1_social_density.png
       docs/figures/fig2_emergent_events.png
       docs/figures/fig3_behavior_entropy.png
       docs/figures/fig4_combined.png

风格: 暗色主题 (dark background), 学术渲染, 中英文标签
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── 使用 Agg 后端（无 GUI） ────────────────────────────────────────
matplotlib.use("Agg")

# ── 路径 ──────────────────────────────────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
DATA_PATH = BACKEND_ROOT / "data" / "paper_experiment_results.json"
FIGURES_DIR = PROJECT_ROOT / "docs" / "figures"

# ── 中文字体配置 ──────────────────────────────────────────────────
# 尝试查找系统可用的 CJK 字体
_CN_FONT = None
_candidate_fonts = [
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "SimHei",
    "Microsoft YaHei",
    "AR PL UMing CN",
]

# 先通过 matplotlib 字体管理器查找
import matplotlib.font_manager as fm
_available = {f.name for f in fm.fontManager.ttflist}
for _f in _candidate_fonts:
    if _f in _available:
        _CN_FONT = _f
        break

# 回退: 搜索系统字体目录
if _CN_FONT is None:
    import subprocess
    try:
        result = subprocess.run(
            ["fc-list", ":lang=zh", "-f", "%{family}\n"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            name = line.split(",")[0].strip()
            if name:
                _CN_FONT = name
                break
    except Exception:
        pass

if _CN_FONT:
    print(f"[fonts] 使用中文字体: {_CN_FONT}")
    plt.rcParams["font.family"] = _CN_FONT
else:
    print("[fonts] ⚠ 未找到中文字体，中文标签可能显示为方块")

plt.rcParams["font.size"] = 11
plt.rcParams["axes.unicode_minus"] = False  # 正常显示负号

# ── 颜色方案（暗色主题学术风） ────────────────────────────────────
COLORS = {
    "bg": "#1a1a2e",
    "axes_bg": "#16213e",
    "grid": "#2a2a4a",
    "text": "#e0e0e0",
    "world_a": "#00bcd4",   # 青色 — 基准
    "world_b": "#ff9800",   # 橙色 — 高社交
    "world_c": "#e91e63",   # 粉色 — 高战斗
    "bar_a": "#0097a7",
    "bar_b": "#f57c00",
    "bar_c": "#c2185b",
}

WORLD_COLORS = [COLORS["world_a"], COLORS["world_b"], COLORS["world_c"]]
WORLD_BAR_COLORS = [COLORS["bar_a"], COLORS["bar_b"], COLORS["bar_c"]]
WORLD_NAMES = ["World A\nBaseline", "World B\nHigh Social", "World C\nHigh Battle"]
WORLD_SHORT = ["A (基准)", "B (高社交)", "C (高战斗)"]


def _set_dark_style(ax: plt.Axes) -> None:
    """对一个 axes 应用暗色主题。"""
    ax.set_facecolor(COLORS["axes_bg"])
    ax.tick_params(colors=COLORS["text"])
    ax.xaxis.label.set_color(COLORS["text"])
    ax.yaxis.label.set_color(COLORS["text"])
    ax.title.set_color(COLORS["text"])
    for spine in ax.spines.values():
        spine.set_color(COLORS["grid"])
    ax.grid(True, color=COLORS["grid"], alpha=0.4, linestyle="--", linewidth=0.5)


def _load_data() -> dict:
    """加载实验 JSON 数据。"""
    if not DATA_PATH.exists():
        print(f"[ERROR] 数据文件不存在: {DATA_PATH}")
        print("  请先运行: cd backend && source .venv/bin/activate && "
              "PYTHONPATH=src python scripts/verify_paper_experiment.py")
        sys.exit(1)

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fig1_social_density(data: dict) -> None:
    """
    图 1: 社交网络密度随时间演化 (三条曲线 + 误差带)

    X 轴 = tick, Y 轴 = 社交密度
    三条曲线 = 世界 A(基准) / B(高社交) / C(高战斗)
    阴影带 = ±1 标准差 (跨 3 轮)
    """
    worlds = data["worlds"]
    ticks = [s["tick"] for s in worlds[0]["aggregated"]["mean"]]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor(COLORS["bg"])
    _set_dark_style(ax)

    for i, w in enumerate(worlds):
        mean_vals = [s["social_density"] for s in w["aggregated"]["mean"]]
        std_vals = [s["social_density"] for s in w["aggregated"]["std"]]
        color = WORLD_COLORS[i]

        ax.plot(ticks, mean_vals, color=color, linewidth=2.2,
                label=WORLD_NAMES[i], zorder=3)
        ax.fill_between(ticks,
                        [m - s for m, s in zip(mean_vals, std_vals)],
                        [m + s for m, s in zip(mean_vals, std_vals)],
                        color=color, alpha=0.18, linewidth=0)

    ax.set_xlabel("Tick 时间步", fontsize=12)
    ax.set_ylabel("Social Density 社交密度", fontsize=12)
    ax.set_title("Fig 1: Social Network Density Evolution\n社交网络密度随时间演化",
                 fontsize=13, fontweight="bold", pad=12)
    ax.legend(frameon=True, facecolor=COLORS["axes_bg"],
              edgecolor=COLORS["grid"], labelcolor=COLORS["text"],
              fontsize=10, loc="lower right")
    ax.set_xlim(0, data["total_ticks"])
    ax.set_ylim(bottom=0)

    fig.tight_layout(pad=2)
    _save_figure(fig, "fig1_social_density.png")


def fig2_emergent_events(data: dict) -> None:
    """
    图 2: 涌现事件分组柱状图

    三世界对比: 总涌现事件 / 战斗 / 对话
    分组柱状图展示三类事件数量
    """
    worlds = data["worlds"]

    # 从 aggregated mean 中汇总各指标总数
    event_totals = []
    battle_totals = []
    dialogue_totals = []

    for w in worlds:
        mean_snaps = w["aggregated"]["mean"]
        event_totals.append(int(sum(s["emergent_events"] for s in mean_snaps)))
        battle_totals.append(int(sum(s["battle_count"] for s in mean_snaps)))
        dialogue_totals.append(int(sum(s["dialogue_count"] for s in mean_snaps)))

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor(COLORS["bg"])
    _set_dark_style(ax)

    x = np.arange(len(worlds))
    width = 0.25

    bars1 = ax.bar(x - width, event_totals, width,
                   label="Emergent Events 涌现事件", color=COLORS["world_a"],
                   edgecolor=COLORS["bg"], linewidth=0.8, alpha=0.9)
    bars2 = ax.bar(x, battle_totals, width,
                   label="Battles 战斗", color=COLORS["world_c"],
                   edgecolor=COLORS["bg"], linewidth=0.8, alpha=0.9)
    bars3 = ax.bar(x + width, dialogue_totals, width,
                   label="Dialogues 对话", color=COLORS["world_b"],
                   edgecolor=COLORS["bg"], linewidth=0.8, alpha=0.9)

    # 数值标签
    def _label_bar(bar_group, offset_y=0):
        for bar in bar_group:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + offset_y + 1,
                        str(int(h)), ha="center", va="bottom",
                        color=COLORS["text"], fontsize=9)

    _label_bar(bars1, offset_y=max(event_totals) * 0.01)
    _label_bar(bars2, offset_y=max(battle_totals) * 0.02)
    _label_bar(bars3, offset_y=max(dialogue_totals) * 0.02)

    ax.set_xticks(x)
    ax.set_xticklabels(WORLD_SHORT, fontsize=11)
    ax.set_ylabel("Event Count 事件数", fontsize=12)
    ax.set_title("Fig 2: Emergent Events Comparison\n涌现事件对比 (分组柱状图)",
                 fontsize=13, fontweight="bold", pad=12)

    # Add headroom for legend
    max_val = max(max(event_totals), max(battle_totals), max(dialogue_totals))
    ax.set_ylim(0, max_val * 1.35)

    ax.legend(frameon=True, facecolor=COLORS["axes_bg"],
              edgecolor=COLORS["grid"], labelcolor=COLORS["text"],
              fontsize=10, loc="upper right")

    fig.tight_layout(pad=2)
    _save_figure(fig, "fig2_emergent_events.png")


def fig3_behavior_entropy(data: dict) -> None:
    """
    图 3: 行为熵随时间演化 (三条曲线 + 误差带)

    X 轴 = tick, Y 轴 = 行为熵
    三条曲线 = 世界 A / B / C
    阴影带 = ±1 标准差
    """
    worlds = data["worlds"]
    ticks = [s["tick"] for s in worlds[0]["aggregated"]["mean"]]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor(COLORS["bg"])
    _set_dark_style(ax)

    for i, w in enumerate(worlds):
        mean_vals = [s["behavior_entropy"] for s in w["aggregated"]["mean"]]
        std_vals = [s["behavior_entropy"] for s in w["aggregated"]["std"]]
        color = WORLD_COLORS[i]

        ax.plot(ticks, mean_vals, color=color, linewidth=2.2,
                label=WORLD_NAMES[i], zorder=3)
        ax.fill_between(ticks,
                        [m - s for m, s in zip(mean_vals, std_vals)],
                        [m + s for m, s in zip(mean_vals, std_vals)],
                        color=color, alpha=0.18, linewidth=0)

    ax.set_xlabel("Tick 时间步", fontsize=12)
    ax.set_ylabel("Behavioral Entropy 行为熵 (bits)", fontsize=12)
    ax.set_title("Fig 3: Behavioral Entropy Evolution\n行为熵随时间演化",
                 fontsize=13, fontweight="bold", pad=12)
    ax.legend(frameon=True, facecolor=COLORS["axes_bg"],
              edgecolor=COLORS["grid"], labelcolor=COLORS["text"],
              fontsize=10, loc="lower right")
    ax.set_xlim(0, data["total_ticks"])
    ax.set_ylim(bottom=0)

    fig.tight_layout(pad=2)
    _save_figure(fig, "fig3_behavior_entropy.png")


def fig4_combined(data: dict) -> None:
    """
    图 4: 2×2 子图汇总

    - 左上: 社交密度曲线
    - 右上: 涌现事件累计柱状图
    - 左下: 行为熵曲线
    - 右下: 情绪方差曲线
    """
    worlds = data["worlds"]
    ticks = [s["tick"] for s in worlds[0]["aggregated"]["mean"]]

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.patch.set_facecolor(COLORS["bg"])

    # ── 左上: 社交密度 ──
    ax = axes[0, 0]
    _set_dark_style(ax)
    for i, w in enumerate(worlds):
        mean_vals = [s["social_density"] for s in w["aggregated"]["mean"]]
        std_vals = [s["social_density"] for s in w["aggregated"]["std"]]
        color = WORLD_COLORS[i]
        ax.plot(ticks, mean_vals, color=color, linewidth=1.8, label=WORLD_SHORT[i])
        ax.fill_between(ticks,
                        [m - s for m, s in zip(mean_vals, std_vals)],
                        [m + s for m, s in zip(mean_vals, std_vals)],
                        color=color, alpha=0.12, linewidth=0)
    ax.set_title("(a) Social Density 社交密度", fontsize=12, fontweight="bold")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Density")
    ax.legend(frameon=True, facecolor=COLORS["axes_bg"],
              edgecolor=COLORS["grid"], labelcolor=COLORS["text"], fontsize=8)
    ax.set_xlim(0, data["total_ticks"])
    ax.set_ylim(bottom=0)

    # ── 右上: 涌现事件累计 ──
    ax = axes[0, 1]
    _set_dark_style(ax)
    for i, w in enumerate(worlds):
        mean_snaps = w["aggregated"]["mean"]
        cumulative = np.cumsum([s["emergent_events"] for s in mean_snaps])
        ax.plot(ticks, cumulative, color=WORLD_COLORS[i], linewidth=1.8,
                label=WORLD_SHORT[i])
    ax.set_title("(b) Cumulative Emergent Events 累计涌现事件", fontsize=12, fontweight="bold")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Cumulative Events")
    ax.legend(frameon=True, facecolor=COLORS["axes_bg"],
              edgecolor=COLORS["grid"], labelcolor=COLORS["text"], fontsize=8)
    ax.set_xlim(0, data["total_ticks"])

    # ── 左下: 行为熵 ──
    ax = axes[1, 0]
    _set_dark_style(ax)
    for i, w in enumerate(worlds):
        mean_vals = [s["behavior_entropy"] for s in w["aggregated"]["mean"]]
        std_vals = [s["behavior_entropy"] for s in w["aggregated"]["std"]]
        color = WORLD_COLORS[i]
        ax.plot(ticks, mean_vals, color=color, linewidth=1.8, label=WORLD_SHORT[i])
        ax.fill_between(ticks,
                        [m - s for m, s in zip(mean_vals, std_vals)],
                        [m + s for m, s in zip(mean_vals, std_vals)],
                        color=color, alpha=0.12, linewidth=0)
    ax.set_title("(c) Behavioral Entropy 行为熵", fontsize=12, fontweight="bold")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Entropy (bits)")
    ax.legend(frameon=True, facecolor=COLORS["axes_bg"],
              edgecolor=COLORS["grid"], labelcolor=COLORS["text"], fontsize=8)
    ax.set_xlim(0, data["total_ticks"])
    ax.set_ylim(bottom=0)

    # ── 右下: 情绪方差 ──
    ax = axes[1, 1]
    _set_dark_style(ax)
    for i, w in enumerate(worlds):
        mean_vals = [s["emotional_variance"] for s in w["aggregated"]["mean"]]
        std_vals = [s["emotional_variance"] for s in w["aggregated"]["std"]]
        color = WORLD_COLORS[i]
        ax.plot(ticks, mean_vals, color=color, linewidth=1.8, label=WORLD_SHORT[i])
        ax.fill_between(ticks,
                        [m - s for m, s in zip(mean_vals, std_vals)],
                        [m + s for m, s in zip(mean_vals, std_vals)],
                        color=color, alpha=0.12, linewidth=0)
    ax.set_title("(d) Emotional Variance 情绪方差", fontsize=12, fontweight="bold")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Variance")
    ax.legend(frameon=True, facecolor=COLORS["axes_bg"],
              edgecolor=COLORS["grid"], labelcolor=COLORS["text"], fontsize=8)
    ax.set_xlim(0, data["total_ticks"])
    ax.set_ylim(bottom=0)

    fig.suptitle("Fig 4: Multi-Dimensional Comparison\n多维度对照实验汇总",
                 fontsize=14, fontweight="bold", color=COLORS["text"], y=1.01)
    fig.tight_layout(pad=3)
    _save_figure(fig, "fig4_combined.png")


def _save_figure(fig: plt.Figure, filename: str) -> None:
    """保存图片到 docs/figures/。"""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    filepath = FIGURES_DIR / filename
    fig.savefig(filepath, dpi=200, bbox_inches="tight",
                facecolor=COLORS["bg"], edgecolor="none")
    plt.close(fig)
    print(f"  ✅ {filepath}")


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 70)
    print("  论文图表生成 — Paper Figure Generator")
    print(f"  数据源: {DATA_PATH}")
    print(f"  输出目录: {FIGURES_DIR}")
    print("=" * 70)

    data = _load_data()

    print(f"\n  实验信息:")
    print(f"    时间戳: {data.get('timestamp', 'N/A')}")
    print(f"    总 tick: {data.get('total_ticks')}")
    print(f"    每世界 agents: {data.get('agents_per_world')}")
    print(f"    每条件轮数: {data.get('rounds_per_config')}")
    print(f"    世界数: {len(data['worlds'])}")

    print(f"\n  生成图表...")
    fig1_social_density(data)
    fig2_emergent_events(data)
    fig3_behavior_entropy(data)
    fig4_combined(data)

    print(f"\n{'=' * 70}")
    print(f"  ALL FIGURES GENERATED ✓")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()

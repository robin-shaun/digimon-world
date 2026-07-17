#!/usr/bin/env python3
# ruff: noqa: E402
"""Generate paper-quality comparison charts from paper_experiment_results.json.

Produces 5 figures in backend/data/paper_figures/:
  - paper_fig1_social_density.png
  - paper_fig2_behavior_entropy.png
  - paper_fig3_emergent_events.png
  - paper_fig4_radar.png
  - paper_fig0_combined.png (2x2 composite)
"""

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as ticker
import numpy as np

# ── paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "paper_experiment_results.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "paper_figures"

# ── labels / colours / line-styles ─────────────────────────────────────────
WORLD_LABEL_MAP = {
    "world_a_baseline":    "World A (Baseline)",
    "world_b_high_social": "World B (High Social)",
    "world_c_high_battle": "World C (High Battle)",
}
COLORS   = ["#1f77b4", "#d62728", "#2ca02c"]   # blue, red, green
LINESTYLES = ["-", "--", "-."]
MARKERS   = ["o", "s", "D"]

RADAR_DIMS = [
    "social_density",
    "behavior_entropy",
    "emergent_events",
    "emotional_variance",
    "personality_drift",
]
RADAR_LABELS = [
    "Social Density",
    "Behavior Entropy",
    "Emergent Events",
    "Emotional Variance",
    "Personality Drift",
]

DPI = 150


# ── helpers ────────────────────────────────────────────────────────────────
def setup_chinese_font() -> None:
    """Set WenQuanYi Zen Hei (or fallback) as default font for CJK support."""
    candidates = ["WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "DejaVu Sans"]
    for name in candidates:
        for f in fm.fontManager.ttflist:
            if f.name == name:
                plt.rcParams["font.family"] = f.name
                return
    # last resort: use system default sans-serif
    plt.rcParams["font.family"] = "sans-serif"


def load_data() -> dict:
    """Load and return the experiment results JSON."""
    if not DATA_FILE.exists():
        print(f"[ERROR] Data file not found: {DATA_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(DATA_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def world_label(raw: str) -> str:
    return WORLD_LABEL_MAP.get(raw, raw)


def get_snapshots(world: dict) -> list[dict]:
    """Return the snapshot list from a world (use aggregated mean)."""
    return world["aggregated"]["mean"]


def total_events(world: dict) -> int:
    return sum(s["emergent_events"] for s in get_snapshots(world))


def minmax_scale(values: list[float]) -> list[float]:
    """Linearly scale a list of values into [0, 1]."""
    mi, ma = min(values), max(values)
    if ma == mi:
        return [0.5] * len(values)
    return [(v - mi) / (ma - mi) for v in values]


# ── figure generators ─────────────────────────────────────────────────────
def fig1_social_density(worlds: list[dict]) -> None:
    """Line chart: social_density over ticks, three worlds overlaid."""
    fig, ax = plt.subplots(figsize=(10, 6))
    for idx, world in enumerate(worlds):
        snaps = get_snapshots(world)
        ticks = [s["tick"] for s in snaps]
        vals  = [s["social_density"] for s in snaps]
        ax.plot(ticks, vals,
                color=COLORS[idx], linestyle=LINESTYLES[idx],
                marker=MARKERS[idx], markersize=5, linewidth=2,
                label=world_label(world["label"]))

    ax.set_xlabel("Tick", fontsize=13)
    ax.set_ylabel("Social Density", fontsize=13)
    ax.set_title("Social Network Density Over Time", fontsize=15, fontweight="bold")
    ax.legend(fontsize=11, framealpha=0.9, edgecolor="gray")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    out = OUTPUT_DIR / "paper_fig1_social_density.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"[OK] {out}")


def fig2_behavior_entropy(worlds: list[dict]) -> None:
    """Line chart: behavior_entropy over ticks, three worlds overlaid."""
    fig, ax = plt.subplots(figsize=(10, 6))
    for idx, world in enumerate(worlds):
        snaps = get_snapshots(world)
        ticks = [s["tick"] for s in snaps]
        vals  = [s["behavior_entropy"] for s in snaps]
        ax.plot(ticks, vals,
                color=COLORS[idx], linestyle=LINESTYLES[idx],
                marker=MARKERS[idx], markersize=5, linewidth=2,
                label=world_label(world["label"]))

    ax.set_xlabel("Tick", fontsize=13)
    ax.set_ylabel("Behavior Entropy", fontsize=13)
    ax.set_title("Behavior Entropy Over Time", fontsize=15, fontweight="bold")
    ax.legend(fontsize=11, framealpha=0.9, edgecolor="gray")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.set_xlim(left=0)
    fig.tight_layout()
    out = OUTPUT_DIR / "paper_fig2_behavior_entropy.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"[OK] {out}")


def fig3_emergent_events(worlds: list[dict]) -> None:
    """Grouped bar chart: total emergent events per world, labelled."""
    labels = [world_label(w["label"]) for w in worlds]
    totals = [total_events(w) for w in worlds]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(x, totals, color=COLORS, width=0.55, edgecolor="black", linewidth=0.8)

    for bar, val in zip(bars, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                str(val), ha="center", va="bottom", fontsize=13, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylabel("Total Emergent Events", fontsize=13)
    ax.set_title("Cumulative Emergent Events by World", fontsize=15, fontweight="bold")
    ax.set_ylim(0, max(totals) * 1.18)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()
    out = OUTPUT_DIR / "paper_fig3_emergent_events.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"[OK] {out}")


def fig4_radar(worlds: list[dict]) -> None:
    """Radar chart: 5 normalized metrics, one polygon per world."""
    # aggregate final snapshot or mean?  Use mean of each dimension.
    n_dims = len(RADAR_DIMS)
    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})

    # collect raw averages across worlds for normalisation
    raw = {dim: [] for dim in RADAR_DIMS}
    for world in worlds:
        snaps = get_snapshots(world)
        for dim in RADAR_DIMS:
            raw[dim].append(np.mean([s[dim] for s in snaps]))

    for idx, world in enumerate(worlds):
        snaps = get_snapshots(world)
        values = [np.mean([s[dim] for s in snaps]) for dim in RADAR_DIMS]
        # normalise across worlds
        normed = []
        for i, dim in enumerate(RADAR_DIMS):
            all_vals = raw[dim]
            mi, ma = min(all_vals), max(all_vals)
            if ma == mi:
                normed.append(0.5)
            else:
                normed.append((values[i] - mi) / (ma - mi))
        normed += normed[:1]

        ax.fill(angles, normed, color=COLORS[idx], alpha=0.1)
        ax.plot(angles, normed, color=COLORS[idx], linewidth=2,
                linestyle=LINESTYLES[idx], label=world_label(world["label"]))
        ax.fill(angles, normed, color=COLORS[idx], alpha=0.1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(RADAR_LABELS, fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels([f"{v:.1f}" for v in [0.2, 0.4, 0.6, 0.8, 1.0]], fontsize=8)
    ax.set_title("Cross-World Radar Comparison (Normalized)", fontsize=14,
                 fontweight="bold", pad=25)
    ax.legend(loc="upper right", bbox_to_anchor=(1.32, 1.12), fontsize=10,
              framealpha=0.9, edgecolor="gray")
    fig.tight_layout()
    out = OUTPUT_DIR / "paper_fig4_radar.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"[OK] {out}")


def fig0_combined(worlds: list[dict]) -> None:
    """2x2 composite figure of all four charts above."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 13))

    # -- (0,0) Social Density ------------------------------------------------
    ax = axes[0, 0]
    for idx, world in enumerate(worlds):
        snaps = get_snapshots(world)
        ticks = [s["tick"] for s in snaps]
        vals  = [s["social_density"] for s in snaps]
        ax.plot(ticks, vals, color=COLORS[idx], linestyle=LINESTYLES[idx],
                marker=MARKERS[idx], markersize=4, linewidth=1.8,
                label=world_label(world["label"]))
    ax.set_title("(a) Social Network Density", fontsize=13, fontweight="bold")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Social Density")
    ax.legend(fontsize=9, framealpha=0.9, edgecolor="gray")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.set_xlim(left=0)

    # -- (0,1) Behavior Entropy ----------------------------------------------
    ax = axes[0, 1]
    for idx, world in enumerate(worlds):
        snaps = get_snapshots(world)
        ticks = [s["tick"] for s in snaps]
        vals  = [s["behavior_entropy"] for s in snaps]
        ax.plot(ticks, vals, color=COLORS[idx], linestyle=LINESTYLES[idx],
                marker=MARKERS[idx], markersize=4, linewidth=1.8,
                label=world_label(world["label"]))
    ax.set_title("(b) Behavior Entropy", fontsize=13, fontweight="bold")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Behavior Entropy")
    ax.legend(fontsize=9, framealpha=0.9, edgecolor="gray")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.set_xlim(left=0)

    # -- (1,0) Emergent Events -----------------------------------------------
    ax = axes[1, 0]
    labels = [world_label(w["label"]) for w in worlds]
    totals = [total_events(w) for w in worlds]
    x = np.arange(len(labels))
    bars = ax.bar(x, totals, color=COLORS, width=0.55, edgecolor="black", linewidth=0.8)
    for bar, val in zip(bars, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                str(val), ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_title("(c) Cumulative Emergent Events", fontsize=13, fontweight="bold")
    ax.set_ylabel("Total Events")
    ax.set_ylim(0, max(totals) * 1.18)
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # -- (1,1) Radar ---------------------------------------------------------
    ax = axes[1, 1]
    ax.remove()
    ax = fig.add_subplot(2, 2, 4, projection="polar")
    n_dims = len(RADAR_DIMS)
    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist() + [0]

    raw = {dim: [] for dim in RADAR_DIMS}
    for world in worlds:
        snaps = get_snapshots(world)
        for dim in RADAR_DIMS:
            raw[dim].append(np.mean([s[dim] for s in snaps]))

    for idx, world in enumerate(worlds):
        snaps = get_snapshots(world)
        values = [np.mean([s[dim] for s in snaps]) for dim in RADAR_DIMS]
        normed = []
        for i, dim in enumerate(RADAR_DIMS):
            all_vals = raw[dim]
            mi, ma = min(all_vals), max(all_vals)
            if ma == mi:
                normed.append(0.5)
            else:
                normed.append((values[i] - mi) / (ma - mi))
        normed += normed[:1]
        ax.plot(angles, normed, color=COLORS[idx], linewidth=1.8,
                linestyle=LINESTYLES[idx], label=world_label(world["label"]))
        ax.fill(angles, normed, color=COLORS[idx], alpha=0.08)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(RADAR_LABELS, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_title("(d) Normalized Radar", fontsize=13, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.38, 1.10), fontsize=8,
              framealpha=0.9, edgecolor="gray")

    fig.suptitle("Digimon World: Controlled Emergence Experiment Results",
                 fontsize=17, fontweight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = OUTPUT_DIR / "paper_fig0_combined.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"[OK] {out}")


# ── main ───────────────────────────────────────────────────────────────────
def main() -> None:
    setup_chinese_font()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data = load_data()
    worlds = data["worlds"]
    print(f"Loaded {len(worlds)} worlds from {DATA_FILE}")

    fig1_social_density(worlds)
    fig2_behavior_entropy(worlds)
    fig3_emergent_events(worlds)
    fig4_radar(worlds)
    fig0_combined(worlds)

    print(f"\nAll {5} figures saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()

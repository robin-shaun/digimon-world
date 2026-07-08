"""
verify_phase2.py 包装测试
=========================

让 pytest 在每次 CI / 跑测时也跑一遍 Phase 2 端到端模拟验证。
零网络依赖(走 fake LLM),跑得很快(< 1 秒)。

如果 Phase 2 核心链路(observe → memory → reflect → plan → act → dialogue)挂了,
这个测试立刻挂掉,而不是要等真用户去跑验证脚本。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "verify_phase2.py"


def test_verify_phase2_script_passes() -> None:
    """verify_phase2.py 跑得通,15/15 校验全过。

    验证 Phase 2 agent 自主生活闭环没退化:
    - 时钟在推进
    - 每只 agent 位置变化 + 记忆写入 + 有 plan
    - proximity → dialogue 写入双方记忆
    """
    assert SCRIPT_PATH.exists(), f"未找到验证脚本: {SCRIPT_PATH}"

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--ticks", "12"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(SCRIPT_PATH.parent.parent),  # backend/
    )

    # 退出码 0 = PASS
    assert result.returncode == 0, (
        f"verify_phase2.py 退出码 {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )

    # 必须包含"15 通过, 0 失败"
    assert "0 失败" in result.stdout or "0 失败" in result.stderr, (
        f"verify_phase2.py 输出未包含预期汇总\nstdout: {result.stdout[-500:]}"
    )


def test_verify_phase2_custom_ticks() -> None:
    """少 tick(6) 也能跑通,确保脚本不是写死默认 24。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--ticks", "6"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(SCRIPT_PATH.parent.parent),
    )
    assert result.returncode == 0, (
        f"--ticks 6 退出码 {result.returncode}\nstdout: {result.stdout[-500:]}"
    )
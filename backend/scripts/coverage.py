#!/usr/bin/env python3
"""
测试覆盖率报告(静态启发式)
============================

扫描 backend/src/digimon_world/ 下的所有源码,以及 backend/tests/ 下的所有
测试文件,用标准库 ``ast`` 估算每个模块的"测试覆盖率":

覆盖率的定义
------------
本脚本不做运行时行覆盖(项目未安装 coverage.py / pytest-cov),而是做
**静态引用覆盖**:统计每个源码模块里的公开函数 / 方法,再看这些名字是否
在测试代码中被引用(import、调用、属性访问)。一个函数只要在任意测试文件里
被引用到,就算"被覆盖"。

    模块覆盖率 = 被测试引用的公开函数数 / 模块公开函数总数

这是一个偏乐观的下界估计:它能快速告诉你"哪些函数根本没被任何测试碰过",
但不能证明一个被引用的函数真的被断言验证过。想要精确行覆盖,请安装
``pytest-cov`` 后跑 ``pytest --cov``。

统计口径
--------
- 只统计**公开**函数 / 方法:跳过以 ``_`` 开头的名字(私有 / dunder)。
- 统计模块级 ``def``、``async def``,以及类里的方法。
- property / staticmethod / classmethod 一并计入。
- 测试侧的引用来源:``import`` 的符号名、任意 ``Name``、任意属性名
  (``obj.method`` 里的 ``method``)。只要名字匹配即视为覆盖。

跑法(零依赖,仅用标准库 ast):

    cd backend
    python scripts/coverage.py

退出码:全部模块 100% 覆盖返回 0,否则返回 1(方便接 CI)。
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

# backend/src/digimon_world/  与  backend/tests/
BACKEND_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = BACKEND_ROOT / "src" / "digimon_world"
TESTS_ROOT = BACKEND_ROOT / "tests"
PACKAGE_NAME = PACKAGE_ROOT.name  # "digimon_world"


# ----------------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------------
@dataclass
class ModuleReport:
    """单个源码模块的覆盖情况。"""

    name: str  # 点分模块名,如 digimon_world.world.clock
    functions: list[str] = field(default_factory=list)  # 公开函数 / 方法名
    covered: set[str] = field(default_factory=set)  # 被测试引用到的函数名

    @property
    def total(self) -> int:
        return len(self.functions)

    @property
    def covered_count(self) -> int:
        return len(self.covered)

    @property
    def uncovered(self) -> list[str]:
        return sorted(f for f in self.functions if f not in self.covered)

    @property
    def pct(self) -> float:
        if self.total == 0:
            return 100.0  # 没有公开函数的模块视为满覆盖(没什么可测的)
        return 100.0 * self.covered_count / self.total


# ----------------------------------------------------------------------------
# 源码侧:收集每个模块的公开函数 / 方法
# ----------------------------------------------------------------------------
def module_name_for(path: Path) -> str:
    """把文件路径映射成点分模块名(相对包根,去掉 __init__)。"""
    rel = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    parts.insert(0, PACKAGE_NAME)
    return ".".join(parts)


def _is_public(name: str) -> bool:
    """公开名字:不以下划线开头。"""
    return not name.startswith("_")


def collect_functions(path: Path) -> list[str]:
    """解析一个源码文件,返回其中所有公开函数 / 方法名(去重,保持出现顺序)。

    - 模块级 def / async def
    - 类体内的 def / async def(方法)
    嵌套在函数里的局部函数不计入(它们不是可测的公开 API)。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # 语法错误的文件跳过但提示
        print(f"# 跳过(语法错误): {path}: {exc}", file=sys.stderr)
        return []

    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if _is_public(name) and name not in seen:
            seen.add(name)
            names.append(name)

    def visit_body(body: list[ast.stmt], *, in_class: bool) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add(node.name)
                # 只下钻到类里找方法,不进函数体找局部函数
            elif isinstance(node, ast.ClassDef):
                visit_body(node.body, in_class=True)

    visit_body(tree.body, in_class=False)
    return names


def collect_modules() -> dict[str, list[str]]:
    """返回 {模块名: [公开函数名...]},跳过 __pycache__ 和空的 __init__。"""
    modules: dict[str, list[str]] = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        modules[module_name_for(path)] = collect_functions(path)
    return modules


# ----------------------------------------------------------------------------
# 测试侧:收集测试代码里引用到的所有名字
# ----------------------------------------------------------------------------
def collect_test_references() -> set[str]:
    """扫描 tests/ 下所有 .py,返回被引用到的名字集合。

    引用来源:
    - from x import a, b     -> a, b(以及 as 别名的原名)
    - import x.y             -> y
    - 任意 Name 节点          -> 变量 / 函数调用名
    - 任意 Attribute 节点     -> obj.attr 里的 attr(捕获方法调用)
    """
    refs: set[str] = set()
    if not TESTS_ROOT.is_dir():
        return refs

    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            print(f"# 跳过测试(语法错误): {path}: {exc}", file=sys.stderr)
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    refs.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    refs.add(alias.name.split(".")[-1])
            elif isinstance(node, ast.Name):
                refs.add(node.id)
            elif isinstance(node, ast.Attribute):
                refs.add(node.attr)
    return refs


# ----------------------------------------------------------------------------
# 组装报告
# ----------------------------------------------------------------------------
def build_reports(
    modules: dict[str, list[str]], refs: set[str]
) -> list[ModuleReport]:
    reports: list[ModuleReport] = []
    for name, functions in modules.items():
        report = ModuleReport(name=name, functions=functions)
        report.covered = {f for f in functions if f in refs}
        reports.append(report)
    return reports


def short(name: str) -> str:
    """去掉包前缀,显示更短的名字。"""
    prefix = PACKAGE_NAME + "."
    return name[len(prefix):] if name.startswith(prefix) else name


def _bar(pct: float, width: int = 20) -> str:
    """一个简易 ASCII 进度条。"""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def print_report(reports: list[ModuleReport]) -> None:
    print("=" * 72)
    print(f"测试覆盖率报告(静态引用启发式)  包: {PACKAGE_NAME}")
    print("=" * 72)
    print(f"{'模块':<34}{'覆盖率':>8}  {'函数':>7}  进度")
    print("-" * 72)

    for report in sorted(reports, key=lambda r: (r.pct, r.name)):
        name = short(report.name) or "(包根)"
        ratio = f"{report.covered_count}/{report.total}"
        print(
            f"{name:<34}{report.pct:>6.1f}%  {ratio:>7}  {_bar(report.pct)}"
        )


def print_uncovered(reports: list[ModuleReport]) -> None:
    """打印每个模块里未被任何测试引用的公开函数。"""
    gaps = [r for r in sorted(reports, key=lambda r: r.name) if r.uncovered]
    print("\n" + "=" * 72)
    print("未覆盖的公开函数 / 方法")
    print("=" * 72)
    if not gaps:
        print("\n✓ 所有公开函数都被测试引用到了")
        return
    for report in gaps:
        print(f"\n[{short(report.name)}]  ({len(report.uncovered)} 个未覆盖)")
        for fn in report.uncovered:
            print(f"    ✗ {fn}()")


def print_summary(reports: list[ModuleReport]) -> float:
    """打印总计并返回整体覆盖率(按函数加权)。"""
    total_fns = sum(r.total for r in reports)
    covered_fns = sum(r.covered_count for r in reports)
    overall = 100.0 if total_fns == 0 else 100.0 * covered_fns / total_fns

    fully = sum(1 for r in reports if r.pct >= 100.0)
    print("\n" + "-" * 72)
    print(
        f"模块数: {len(reports)}    "
        f"全覆盖模块: {fully}/{len(reports)}    "
        f"公开函数: {covered_fns}/{total_fns}"
    )
    print(f"整体覆盖率: {overall:.1f}%  {_bar(overall)}")
    return overall


def main() -> int:
    if not PACKAGE_ROOT.is_dir():
        print(f"找不到包目录: {PACKAGE_ROOT}", file=sys.stderr)
        return 2

    modules = collect_modules()
    if not modules:
        print(f"在 {PACKAGE_ROOT} 下没找到 .py 文件", file=sys.stderr)
        return 2

    refs = collect_test_references()
    reports = build_reports(modules, refs)

    print_report(reports)
    print_uncovered(reports)
    overall = print_summary(reports)

    # 全覆盖返回 0,否则返回 1(方便 CI 门禁)
    return 0 if overall >= 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
模块依赖分析
=============

扫描 backend/src/digimon_world/ 下所有 .py 文件,解析其 import 语句,
构建包内模块之间的依赖图,并:

- 打印每个模块的 ASCII 依赖图([name] --> [dep])
- 检测并报告循环依赖(Tarjan 强连通分量)

跑法(零依赖,仅用标准库 ast):

    cd backend
    python scripts/analyze_deps.py

只统计包内部依赖(digimon_world.* 与包内相对 import),
标准库与第三方 import 会被忽略。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# backend/src/digimon_world/
PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "digimon_world"
PACKAGE_NAME = PACKAGE_ROOT.name  # "digimon_world"


def module_name_for(path: Path) -> str:
    """把文件路径映射成点分模块名(相对包根,去掉 __init__)。"""
    rel = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    parts.insert(0, PACKAGE_NAME)
    return ".".join(parts)


def collect_modules() -> dict[str, Path]:
    """返回 {模块名: 文件路径},跳过 __pycache__。"""
    modules: dict[str, Path] = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        modules[module_name_for(path)] = path
    return modules


def resolve_relative(current: str, node: ast.ImportFrom) -> str:
    """把相对 import(from . / from ..x)解析成绝对点分模块名。"""
    # current 是当前文件的模块名;包上下文是它去掉最后一段
    pkg_parts = current.split(".")
    if not current.endswith("__init__"):
        # 文件模块的包是它的父路径;level=1 表示当前包
        pkg_parts = pkg_parts[:-1]
    # level 每多一层就再上升一级
    up = node.level - 1
    if up > 0:
        pkg_parts = pkg_parts[: len(pkg_parts) - up] if up <= len(pkg_parts) else []
    base = ".".join(pkg_parts)
    if node.module:
        return f"{base}.{node.module}" if base else node.module
    return base


def imported_targets(path: Path, current: str) -> set[str]:
    """解析单个文件的 import,返回它引用到的绝对模块名集合(未过滤)。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # 语法错误的文件跳过但提示
        print(f"# 跳过(语法错误): {path}: {exc}", file=sys.stderr)
        return set()

    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                targets.add(resolve_relative(current, node))
            elif node.module:
                targets.add(node.module)
    return targets


def to_internal_module(target: str, modules: set[str]) -> str | None:
    """把一个 import 目标归约到已知的包内模块名,否则返回 None。

    例:from digimon_world.world.clock import WorldClock
        -> target = "digimon_world.world.clock"(命中模块)
        from digimon_world.world import events (import 的是子模块)
        -> "digimon_world.world.events" 命中,或退化到包 "digimon_world.world"
    """
    if not target.startswith(PACKAGE_NAME):
        return None
    if target in modules:
        return target
    # 逐级去掉尾部(处理 `from pkg.mod import symbol` -> symbol 不是模块)
    parts = target.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
        parts.pop()
    return None


def build_graph(modules: dict[str, Path]) -> dict[str, set[str]]:
    """构建 {模块: {它 import 的包内模块}},忽略自引用。"""
    names = set(modules)
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        for target in imported_targets(path, name):
            dep = to_internal_module(target, names)
            if dep and dep != name:
                graph[name].add(dep)
    return graph


def short(name: str) -> str:
    """去掉包前缀,显示更短的名字。"""
    prefix = PACKAGE_NAME + "."
    return name[len(prefix):] if name.startswith(prefix) else name


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan 强连通分量,返回节点数 >1 或自环的 SCC(即循环依赖)。"""
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []

    def strongconnect(v: str) -> None:
        indices[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            result.append(component)

    # 递归深度对本项目足够;若模块超深可改迭代版
    sys.setrecursionlimit(max(1000, len(graph) * 4))
    for node in graph:
        if node not in indices:
            strongconnect(node)

    cycles: list[list[str]] = []
    for comp in result:
        if len(comp) > 1 or (comp[0] in graph.get(comp[0], set())):
            cycles.append(comp)
    return cycles


def print_graph(graph: dict[str, set[str]]) -> None:
    print("=" * 60)
    print(f"模块依赖图  (包: {PACKAGE_NAME})")
    print("=" * 60)
    for name in sorted(graph):
        deps = sorted(graph[name])
        if deps:
            print(f"\n[{short(name)}]")
            for dep in deps:
                print(f"    --> [{short(dep)}]")
        else:
            print(f"\n[{short(name)}]  (无包内依赖)")


def print_cycles(cycles: list[list[str]]) -> None:
    print("\n" + "=" * 60)
    print("循环依赖检测")
    print("=" * 60)
    if not cycles:
        print("\n✓ 未检测到循环依赖")
        return
    print(f"\n✗ 检测到 {len(cycles)} 处循环依赖:\n")
    for i, comp in enumerate(cycles, 1):
        loop = " -> ".join(f"[{short(m)}]" for m in comp)
        # 补上回到起点的箭头,直观展示环
        print(f"  {i}. {loop} -> [{short(comp[0])}]")


def main() -> int:
    if not PACKAGE_ROOT.is_dir():
        print(f"找不到包目录: {PACKAGE_ROOT}", file=sys.stderr)
        return 2

    modules = collect_modules()
    if not modules:
        print(f"在 {PACKAGE_ROOT} 下没找到 .py 文件", file=sys.stderr)
        return 2

    graph = build_graph(modules)
    print_graph(graph)

    total_edges = sum(len(deps) for deps in graph.values())
    print("\n" + "-" * 60)
    print(f"模块数: {len(modules)}    依赖边数: {total_edges}")

    cycles = find_cycles(graph)
    print_cycles(cycles)

    return 1 if cycles else 0


if __name__ == "__main__":
    raise SystemExit(main())

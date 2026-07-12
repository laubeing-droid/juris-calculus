"""v3 正式求值入口的静态架构门禁。"""

from __future__ import annotations

import ast
from pathlib import Path
import tokenize


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = ("compiler_core", "pipeline", "addons", "tools")
EVALUATOR_TYPES = frozenset({"FixpointEvaluator", "StratifiedEvaluator"})

# 只有唯一 application、底层语义 stage 和明确归类为 CLI/CI 的 harness 可直调。
EVALUATOR_CONSTRUCTOR_ALLOWLIST = frozenset(
    {
        "compiler_core/application.py",
        "compiler_core/prc_collision_engine.py",
        "compiler_core/spec_shadow_harness.py",
        "compiler_core/stratified_evaluator.py",
        "tools/perf_baseline.py",
        "tools/run_trirail_matrix.py",
    }
)
CANONICAL_ENTRYPOINTS = {
    "compiler_core/application.py": "evaluate_case",
    "compiler_core/audit_bundle.py": "evaluate_to_audit_bundle",
}


def _production_files() -> list[Path]:
    """返回确定性排序的生产 Python 文件，不扫描测试、构建产物或虚拟环境。"""

    files = [ROOT / "mcp_server.py"]
    for directory in PRODUCTION_ROOTS:
        files.extend((ROOT / directory).rglob("*.py"))
    return sorted(path for path in files if path.is_file())


def _constructor_aliases(tree: ast.AST) -> set[str]:
    """收集 evaluator 的直接导入名，防止 ``as`` 别名绕过构造器检查。"""

    aliases = set(EVALUATOR_TYPES)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for imported in node.names:
            if imported.name in EVALUATOR_TYPES:
                aliases.add(imported.asname or imported.name)
    return aliases


def _parse_module(path: Path) -> ast.Module:
    """按 Python 源文件编码声明读取模块，兼容仓库内既有 UTF-8 BOM 文件。"""

    with tokenize.open(path) as source:
        return ast.parse(source.read(), filename=str(path))


def _constructor_calls(path: Path) -> list[tuple[int, str]]:
    """解析单个模块并返回其中 evaluator 构造调用的行号和类型名。"""

    tree = _parse_module(path)
    aliases = _constructor_aliases(tree)
    calls: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in aliases:
            calls.append((node.lineno, node.func.id))
        elif isinstance(node.func, ast.Attribute) and node.func.attr in EVALUATOR_TYPES:
            calls.append((node.lineno, node.func.attr))
    return sorted(calls)


def test_canonical_entrypoints_exist() -> None:
    """固定两个正式入口，防止迁移时误删、改名或新增平行入口。"""

    expected_locations = {name: path for path, name in CANONICAL_ENTRYPOINTS.items()}
    actual_locations = {name: [] for name in expected_locations}
    for path in _production_files():
        relative_path = path.relative_to(ROOT).as_posix()
        for node in _parse_module(path).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in actual_locations:
                actual_locations[node.name].append(f"{relative_path}:{node.lineno}")

    errors = []
    for function_name, expected_path in sorted(expected_locations.items()):
        locations = actual_locations[function_name]
        if len(locations) != 1 or not locations[0].startswith(f"{expected_path}:"):
            errors.append(
                f"{function_name}: expected only in {expected_path}, found {locations or ['<missing>']}"
            )
    assert not errors, "canonical entrypoint violations:\n" + "\n".join(errors)


def test_production_evaluator_construction_is_allowlisted() -> None:
    """禁止正式生产模块绕过 application 直接构造任一 evaluator。"""

    violations: list[str] = []
    for path in _production_files():
        relative_path = path.relative_to(ROOT).as_posix()
        if relative_path in EVALUATOR_CONSTRUCTOR_ALLOWLIST:
            continue
        for line_number, constructor in _constructor_calls(path):
            violations.append(f"{relative_path}:{line_number}: direct {constructor} construction")

    assert not violations, "production evaluator boundary violations:\n" + "\n".join(violations)

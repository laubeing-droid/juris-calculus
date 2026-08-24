#!/usr/bin/env python3
"""Validate the manual V4 authority policy against source observations.

Policy is human-authored. AST, dynamic-import declarations, packaging metadata,
and CodeGraph only report whether the current tree conforms to that policy.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import tomllib
from collections import deque
from pathlib import Path
from typing import Any


AUTHORITY_CLASSES = {
    "FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT", "SOURCE_TOOL",
    "EXPERIMENT_ONLY", "CANDIDATE_ASSET", "BUILD_ONLY", "TEST_ONLY", "REMOVE",
}
AUTHORITY_ROLES = {
    "application", "contract", "certificate_issuer", "independent_checker",
}
CODEGRAPH_ASSET_ONLY = {"tools/remediate_v4.py"}
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
EXIT_OK = 0
EXIT_FAILURE = 4


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_object(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + _sha256(payload)


def _git(root: Path, *args: str, raw: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
    return completed.stdout if raw else completed.stdout.decode("utf-8", errors="strict").strip()


def _tracked_python(root: Path) -> list[str]:
    payload = _git(root, "-c", "core.quotepath=false", "ls-files", "-z", "--", "*.py", raw=True)
    assert isinstance(payload, bytes)
    return sorted(
        item.decode("utf-8").replace("\\", "/")
        for item in payload.split(b"\0") if item
    )


def _module_name(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.endswith("/__init__.py"):
        return normalized[:-12].replace("/", ".")
    if normalized.endswith(".py"):
        return normalized[:-3].replace("/", ".")
    raise ValueError(f"not a Python path: {path}")


def _resolve_internal_module(module: str, modules: dict[str, str]) -> str | None:
    candidate = module
    while candidate:
        if candidate in modules:
            return modules[candidate]
        candidate = candidate.rpartition(".")[0]
    return None


def _relative_module(source_path: str, module: str | None, level: int) -> str:
    source_module = _module_name(source_path)
    package = source_module if source_path.endswith("/__init__.py") else source_module.rpartition(".")[0]
    if level == 0:
        return module or ""
    relative = "." * level + (module or "")
    try:
        return importlib.util.resolve_name(relative, package)
    except (ImportError, ValueError):
        return relative


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _expression(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - ast.unparse exists on supported Python
        return type(node).__name__


class _ImportVisitor(ast.NodeVisitor):
    def __init__(self, source_path: str, modules: dict[str, str]) -> None:
        self.source_path = source_path
        self.modules = modules
        self.scope_depth = 0
        self.edges: list[dict[str, Any]] = []
        self.unresolved_dynamic: list[dict[str, Any]] = []
        self.external: list[dict[str, Any]] = []

    @property
    def scope(self) -> str:
        return "function" if self.scope_depth else "module"

    def _record_module(self, module: str, line: int, kind: str, evidence: str) -> None:
        target = _resolve_internal_module(module, self.modules)
        item = {
            "source": self.source_path,
            "line": line,
            "kind": kind,
            "scope": self.scope,
            "evidence": evidence,
            "module": module,
        }
        if target is None:
            self.external.append(item)
        else:
            self.edges.append({**item, "target": target})

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._record_module(alias.name, node.lineno, "import", "python_ast")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        base = _relative_module(self.source_path, node.module, node.level)
        candidates: list[str] = []
        for alias in node.names:
            child = f"{base}.{alias.name}" if base else alias.name
            candidates.append(child if child in self.modules else base)
        kind = "reexport" if self.source_path.endswith("/__init__.py") and self.scope_depth == 0 else "import"
        for module in sorted(set(item for item in candidates if item)):
            self._record_module(module, node.lineno, kind, "python_ast")

    def _visit_scope(self, node: ast.AST) -> None:
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_scope(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        self._visit_scope(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _call_name(node.func)
        kinds = {
            "importlib.import_module": "dynamic_import",
            "import_module": "dynamic_import",
            "__import__": "dynamic_import",
            "importlib.util.find_spec": "availability_probe",
            "find_spec": "availability_probe",
            "importlib.util.spec_from_file_location": "dynamic_path_load",
            "spec_from_file_location": "dynamic_path_load",
        }
        kind = kinds.get(name)
        if kind and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                self._record_module(first.value, node.lineno, kind, "python_ast_dynamic")
            else:
                self.unresolved_dynamic.append({
                    "source": self.source_path,
                    "line": node.lineno,
                    "kind": kind,
                    "scope": self.scope,
                    "evidence": "python_ast_dynamic",
                    "expression": _expression(first),
                    "call": name,
                })
        self.generic_visit(node)


def _scan_imports(root: Path, paths: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    modules = {_module_name(path): path for path in paths}
    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    external: list[dict[str, Any]] = []
    for path in paths:
        payload = (root / path).read_text(encoding="utf-8-sig")
        tree = ast.parse(payload, filename=path)
        visitor = _ImportVisitor(path, modules)
        visitor.visit(tree)
        edges.extend(visitor.edges)
        unresolved.extend(visitor.unresolved_dynamic)
        external.extend(visitor.external)
    edge_keys = ("source", "line", "kind", "scope", "target", "module", "evidence")
    unique_edges = {
        tuple(item.get(key) for key in edge_keys): item for item in edges
    }
    external_keys = ("source", "line", "kind", "scope", "module", "evidence")
    unique_external = {
        tuple(item.get(key) for key in external_keys): item for item in external
    }
    return (
        sorted(unique_edges.values(), key=lambda item: tuple(str(item.get(key, "")) for key in edge_keys)),
        sorted(unresolved, key=lambda item: (item["source"], item["line"], item["kind"])),
        sorted(unique_external.values(), key=lambda item: tuple(str(item.get(key, "")) for key in external_keys)),
    )


def _policy_classes(policy: dict[str, Any], errors: list[dict[str, Any]]) -> dict[str, dict]:
    classes = policy.get("classes")
    if not isinstance(classes, dict) or set(classes) != AUTHORITY_CLASSES:
        errors.append({
            "code": "POLICY_CLASS_SET",
            "detail": f"classes must be exactly {sorted(AUTHORITY_CLASSES)}",
        })
        return {}
    for name, declaration in classes.items():
        if not isinstance(declaration, dict):
            errors.append({"code": "POLICY_CLASS_DECLARATION", "class": name})
            continue
        if not isinstance(declaration.get("deployable"), bool) or not isinstance(
            declaration.get("production_wheel"), bool
        ):
            errors.append({"code": "POLICY_CLASS_FLAGS", "class": name})
        may_import = declaration.get("may_import")
        if not isinstance(may_import, list) or not set(may_import) <= AUTHORITY_CLASSES:
            errors.append({"code": "POLICY_CLASS_IMPORTS", "class": name})
    return classes


def _classify_paths(
    tracked: list[str], policy: dict[str, Any], classes: dict[str, dict],
    errors: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, Any]]:
    exact: dict[str, dict] = {}
    duplicate_exact: list[str] = []
    for rule in policy.get("path_rules", []):
        if not isinstance(rule, dict) or set(rule) != {"path", "class", "rationale"}:
            errors.append({"code": "POLICY_PATH_RULE_SHAPE", "detail": repr(rule)})
            continue
        path = rule["path"].replace("\\", "/")
        if path in exact:
            duplicate_exact.append(path)
        exact[path] = rule
    if duplicate_exact:
        errors.append({"code": "DUPLICATE_EXACT_RULE", "paths": sorted(set(duplicate_exact))})

    prefixes: list[dict] = []
    for rule in policy.get("prefix_rules", []):
        if not isinstance(rule, dict) or set(rule) != {"prefix", "class", "rationale"}:
            errors.append({"code": "POLICY_PREFIX_RULE_SHAPE", "detail": repr(rule)})
            continue
        prefixes.append(rule)
    classified: dict[str, str] = {}
    ambiguous: list[str] = []
    for path in tracked:
        if path in exact:
            authority_class = exact[path].get("class")
        else:
            matches = [rule for rule in prefixes if path.startswith(rule["prefix"])]
            if not matches:
                continue
            longest = max(len(rule["prefix"]) for rule in matches)
            selected = [rule for rule in matches if len(rule["prefix"]) == longest]
            if len(selected) != 1:
                ambiguous.append(path)
                continue
            authority_class = selected[0].get("class")
        if authority_class not in classes:
            errors.append({
                "code": "UNKNOWN_PATH_CLASS", "path": path, "class": authority_class,
            })
            continue
        classified[path] = str(authority_class)
    stale_exact = sorted(set(exact) - set(tracked))
    stale_prefix = sorted(
        rule["prefix"] for rule in prefixes
        if not any(path.startswith(rule["prefix"]) for path in tracked)
    )
    unclassified = sorted(set(tracked) - set(classified) - set(ambiguous))
    if unclassified:
        errors.append({"code": "UNCLASSIFIED_PYTHON", "paths": unclassified})
    if ambiguous:
        errors.append({"code": "AMBIGUOUS_PATH_POLICY", "paths": sorted(ambiguous)})
    if stale_exact:
        errors.append({"code": "STALE_EXACT_RULE", "paths": stale_exact})
    if stale_prefix:
        errors.append({"code": "STALE_PREFIX_RULE", "prefixes": stale_prefix})
    return classified, {
        "tracked_python": len(tracked),
        "classified_python": len(classified),
        "unclassified": unclassified,
        "ambiguous": sorted(ambiguous),
        "stale_exact_rules": stale_exact,
        "stale_prefix_rules": stale_prefix,
        "class_counts": {
            name: sum(value == name for value in classified.values())
            for name in sorted(AUTHORITY_CLASSES)
        },
    }


def _codegraph_evidence(
    root: Path, database: Path, tracked: list[str], errors: list[dict[str, Any]],
) -> dict[str, Any]:
    if not database.is_file():
        errors.append({"code": "CODEGRAPH_MISSING"})
        return {
            "integrity": "missing", "indexed_python": 0,
            "content_mismatches": tracked, "missing_python": tracked,
            "orphan_python": [], "parse_errors": [], "unresolved_refs": None,
            "secondary_import_edges": None, "secondary_call_edges": None,
        }
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        try:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            rows = connection.execute(
                "SELECT path, content_hash, errors FROM files WHERE language='python' OR path LIKE '%.py'"
            ).fetchall()
            unresolved = int(connection.execute("SELECT COUNT(*) FROM unresolved_refs").fetchone()[0])
            edge_counts = dict(connection.execute("SELECT kind, COUNT(*) FROM edges GROUP BY kind").fetchall())
        except sqlite3.DatabaseError as exc:
            errors.append({"code": "CODEGRAPH_SCHEMA", "detail": str(exc)})
            return {
                "integrity": "schema-error", "indexed_python": 0,
                "content_mismatches": [], "missing_python": tracked,
                "orphan_python": [], "parse_errors": [], "unresolved_refs": None,
                "secondary_import_edges": None, "secondary_call_edges": None,
                "enforcement_role": "freshness_and_secondary_observation_only",
            }
    finally:
        connection.close()
    indexed = {str(path).replace("\\", "/"): (content_hash, parse_error) for path, content_hash, parse_error in rows}
    missing = sorted(set(tracked) - set(indexed) - CODEGRAPH_ASSET_ONLY)
    orphan = sorted(set(indexed) - set(tracked))
    mismatches = sorted(
        path for path in set(tracked) & set(indexed)
        if indexed[path][0] != _sha256((root / path).read_bytes())
    )
    parse_errors = sorted(path for path, (_, value) in indexed.items() if value)
    if integrity != "ok":
        errors.append({"code": "CODEGRAPH_INTEGRITY", "detail": integrity})
    if missing:
        errors.append({"code": "CODEGRAPH_MISSING_PYTHON", "paths": missing})
    if orphan:
        errors.append({"code": "CODEGRAPH_ORPHAN_PYTHON", "paths": orphan})
    if mismatches:
        errors.append({"code": "CODEGRAPH_CONTENT_MISMATCH", "paths": mismatches})
    if parse_errors:
        errors.append({"code": "CODEGRAPH_PARSE_ERRORS", "paths": parse_errors})
    if unresolved:
        errors.append({"code": "CODEGRAPH_UNRESOLVED_REFS", "count": unresolved})
    logical_rows = [
        {"path": path, "content_hash": value[0], "errors": value[1]}
        for path, value in sorted(indexed.items())
    ]
    return {
        "integrity": integrity,
        "indexed_python": len(indexed),
        "content_mismatches": mismatches,
        "missing_python": missing,
        "orphan_python": orphan,
        "parse_errors": parse_errors,
        "unresolved_refs": unresolved,
        "secondary_import_edges": int(edge_counts.get("imports", 0)),
        "secondary_call_edges": int(edge_counts.get("calls", 0)),
        "logical_file_index_digest": _digest_object(logical_rows),
        "enforcement_role": "freshness_and_secondary_observation_only",
    }


def _declared_dynamic_edges(
    unresolved: list[dict[str, Any]], policy: dict[str, Any], classes: dict[str, dict],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    declarations = policy.get("declared_dynamic_edges", [])
    by_key: dict[tuple[str, int, str], dict] = {}
    duplicates: list[tuple[str, int, str]] = []
    for item in declarations:
        key = (item.get("importer", ""), item.get("line", -1), item.get("kind", ""))
        if key in by_key:
            duplicates.append(key)
        by_key[key] = item
    if duplicates:
        errors.append({"code": "DUPLICATE_DYNAMIC_DECLARATION", "keys": duplicates})
    matched: set[tuple[str, int, str]] = set()
    edges: list[dict[str, Any]] = []
    for item in unresolved:
        key = (item["source"], item["line"], item["kind"])
        declaration = by_key.get(key)
        if declaration is None:
            errors.append({
                "code": "UNDECLARED_DYNAMIC_IMPORT", "source": item["source"],
                "line": item["line"], "kind": item["kind"],
                "expression": item["expression"],
            })
            continue
        target_class = declaration.get("target_class")
        if target_class not in classes:
            errors.append({"code": "DYNAMIC_TARGET_CLASS", "key": key, "class": target_class})
            continue
        matched.add(key)
        edges.append({
            "source": item["source"], "line": item["line"], "kind": item["kind"],
            "scope": item["scope"], "evidence": "manual_dynamic_declaration+python_ast",
            "module": declaration.get("target_pattern"),
            "target": "pattern:" + str(declaration.get("target_pattern")),
            "declared_target_class": target_class,
        })
    stale = sorted(set(by_key) - matched)
    if stale:
        errors.append({"code": "STALE_DYNAMIC_DECLARATION", "keys": stale})
    return edges


def _entrypoints(
    root: Path, policy: dict[str, Any], classified: dict[str, str],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pyproject_path = root / "pyproject.toml"
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8")) if pyproject_path.is_file() else {}
    observed = payload.get("project", {}).get("scripts", {}) or {}
    declared_items = policy.get("entrypoints", [])
    declared = {item.get("name"): item for item in declared_items}
    if len(declared) != len(declared_items):
        errors.append({"code": "DUPLICATE_ENTRYPOINT_POLICY"})
    if set(observed) != set(declared):
        errors.append({
            "code": "ENTRYPOINT_POLICY_MISMATCH",
            "missing_policy": sorted(set(observed) - set(declared)),
            "stale_policy": sorted(set(declared) - set(observed)),
        })
    modules = {_module_name(path): path for path in classified}
    results: list[dict[str, Any]] = []
    for name, target in sorted(observed.items()):
        module = str(target).partition(":")[0]
        target_path = _resolve_internal_module(module, modules)
        target_class = classified.get(target_path or "")
        declaration = declared.get(name, {})
        if declaration.get("target") != target or declaration.get("class") != target_class:
            errors.append({
                "code": "ENTRYPOINT_TARGET_MISMATCH", "name": name,
                "observed": target, "declared": declaration,
                "observed_class": target_class,
            })
        results.append({
            "name": name, "target": target, "target_path": target_path,
            "target_class": target_class,
        })
    return results


def _packaged_paths(root: Path, tracked: list[str]) -> set[str]:
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        return set()
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    packages = payload.get("tool", {}).get("setuptools", {}).get("packages", {})
    if isinstance(packages, list):
        include = packages
        exclude: list[str] = []
    else:
        finder = packages.get("find", {})
        include = list(finder.get("include", ["*"]))
        exclude = list(finder.get("exclude", []))
    tracked_set = set(tracked)
    packaged: set[str] = set()
    for path in tracked:
        if "/" not in path:
            continue
        parent = path.rpartition("/")[0]
        if f"{parent}/__init__.py" not in tracked_set:
            continue
        package = parent.replace("/", ".")
        if any(fnmatch.fnmatchcase(package, pattern) for pattern in include) and not any(
            fnmatch.fnmatchcase(package, pattern) for pattern in exclude
        ):
            packaged.add(path)
    return packaged


def _backlog_item(kind: str, closure_task: str, **fields: Any) -> dict[str, Any]:
    identity = {"kind": kind, **fields}
    return {
        "id": _digest_object(identity), "kind": kind, "status": "OPEN",
        "closure_task": closure_task, **fields,
    }


def _shortest_path(adjacency: dict[str, set[str]], source: str, target: str) -> list[str] | None:
    queue: deque[list[str]] = deque([[source]])
    seen = {source}
    while queue:
        path = queue.popleft()
        current = path[-1]
        if current == target:
            return path
        for candidate in sorted(adjacency.get(current, set())):
            if candidate not in seen:
                seen.add(candidate)
                queue.append([*path, candidate])
    return None


def build_report(root: Path, policy_path: Path, codegraph_path: Path) -> dict[str, Any]:
    root = root.resolve()
    policy_path = policy_path.resolve()
    codegraph_path = codegraph_path.resolve()
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    errors: list[dict[str, Any]] = []
    if policy.get("schema_version") != "jc/module-authority/1.0":
        errors.append({"code": "POLICY_SCHEMA_VERSION", "value": policy.get("schema_version")})
    classes = _policy_classes(policy, errors)
    tracked = _tracked_python(root)
    classified, coverage = _classify_paths(tracked, policy, classes, errors)
    codegraph = _codegraph_evidence(root, codegraph_path, tracked, errors)
    try:
        ast_edges, unresolved, external = _scan_imports(root, tracked)
    except (SyntaxError, UnicodeError) as exc:
        errors.append({"code": "AST_PARSE_FAILURE", "detail": str(exc)})
        ast_edges, unresolved, external = [], [], []
    dynamic_edges = _declared_dynamic_edges(unresolved, policy, classes, errors)
    edges = sorted(
        [*ast_edges, *dynamic_edges],
        key=lambda item: (
            item["source"], item["line"], item["kind"], item["target"], item["scope"],
        ),
    )
    entrypoints = _entrypoints(root, policy, classified, errors)

    dirty = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        errors.append({"code": "WORKTREE_NOT_CLEAN", "paths": str(dirty).splitlines()})

    closure = policy.get("backlog_closure_tasks", {})
    backlog: list[dict[str, Any]] = []
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if not edge["target"].startswith("pattern:"):
            adjacency.setdefault(edge["source"], set()).add(edge["target"])
    for edge in edges:
        source_class = classified.get(edge["source"])
        target_class = edge.get("declared_target_class") or classified.get(edge["target"])
        if source_class not in classes or target_class not in classes:
            errors.append({
                "code": "EDGE_CLASSIFICATION_MISSING", "source": edge["source"],
                "target": edge["target"],
            })
            continue
        if target_class not in classes[source_class]["may_import"]:
            entrypoint_paths: list[list[str]] = []
            for entrypoint in entrypoints:
                entrypoint_source = entrypoint.get("target_path")
                if not entrypoint_source:
                    continue
                prefix = _shortest_path(adjacency, entrypoint_source, edge["source"])
                if prefix:
                    entrypoint_paths.append([*prefix, edge["target"]])
            backlog.append(_backlog_item(
                "class_edge", closure.get("class_edge", "W5-CUTOVER"),
                source=edge["source"], line=edge["line"], target=edge["target"],
                source_class=source_class, target_class=target_class,
                evidence=edge["evidence"], scope=edge["scope"],
                entrypoint_paths=entrypoint_paths,
            ))

    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    external_policy = policy.get("external_imports", {})
    default_external = set(external_policy.get("deployable_allowlist", []))
    class_external = external_policy.get("class_allowlist", {})
    forbidden_external = set(external_policy.get("forbidden_roots", []))
    for edge in external:
        source_class = classified.get(edge["source"])
        if source_class not in classes or not classes[source_class].get("deployable"):
            continue
        root_module = edge["module"].partition(".")[0]
        forbidden = root_module in forbidden_external
        allowed_external = set(class_external.get(source_class, default_external))
        unknown_third_party = root_module not in stdlib and root_module not in allowed_external
        if forbidden or unknown_third_party:
            backlog.append(_backlog_item(
                "external_import", closure.get("external", "W5-CUTOVER"),
                source=edge["source"], line=edge["line"], module=edge["module"],
                source_class=source_class,
                reason="forbidden_boundary" if forbidden else "third_party_not_allowlisted",
            ))

    packaged = _packaged_paths(root, tracked)
    for path, authority_class in sorted(classified.items()):
        expected = bool(classes[authority_class]["production_wheel"])
        actual = path in packaged
        if actual and not expected:
            backlog.append(_backlog_item(
                "wheel_forbidden", closure.get("wheel", "W6-01"),
                source=path, source_class=authority_class,
            ))
        elif expected and not actual:
            backlog.append(_backlog_item(
                "wheel_missing", closure.get("wheel", "W6-01"),
                source=path, source_class=authority_class,
            ))

    roles = policy.get("authority_roles", {})
    if set(roles) != AUTHORITY_ROLES:
        errors.append({
            "code": "AUTHORITY_ROLE_SET", "roles": sorted(roles),
            "expected": sorted(AUTHORITY_ROLES),
        })
    authority_targets = {
        role: declaration.get("target_path") for role, declaration in sorted(roles.items())
    }
    nonempty_targets = [path for path in authority_targets.values() if path]
    if len(nonempty_targets) != len(set(nonempty_targets)):
        errors.append({"code": "DUPLICATE_AUTHORITY_TARGET", "targets": nonempty_targets})
    for role, declaration in sorted(roles.items()):
        target = declaration.get("target_path")
        if target not in classified:
            backlog.append(_backlog_item(
                "authority_target_missing", declaration.get("closure_task", closure.get("authority", "W4-04")),
                role=role, target=target,
            ))
        elif classified[target] != "FORMAL_CORE":
            errors.append({
                "code": "AUTHORITY_TARGET_CLASS", "role": role,
                "target": target, "class": classified[target],
            })

    runtime_policy = policy.get("runtime_output", {})
    runtime_closure = runtime_policy.get("closure_task", "W4-03")
    for source, authority_class in sorted(classified.items()):
        if authority_class != "RUNTIME_OUTPUT":
            continue
        for target in sorted(runtime_policy.get("forbidden_reachability_paths", [])):
            if target not in classified:
                continue
            path = _shortest_path(adjacency, source, target)
            if path:
                backlog.append(_backlog_item(
                    "runtime_output_reachability", runtime_closure,
                    source=source, target=target, path=path,
                ))

    errors = sorted(errors, key=lambda item: (item.get("code", ""), json.dumps(item, sort_keys=True)))
    backlog = sorted(backlog, key=lambda item: (item["kind"], item["id"]))
    status = (
        "INVALID" if errors
        else "OPEN_VIOLATIONS" if backlog
        else "CLEAN"
    )
    report: dict[str, Any] = {
        "schema_version": "jc/observed-authority-graph/1.0",
        "status": status,
        "source_commit": _git(root, "rev-parse", "HEAD"),
        "source_tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "policy_digest": "sha256:" + _sha256(policy_path.read_bytes()),
        "authority_roles": authority_targets,
        "coverage": coverage,
        "codegraph": codegraph,
        "entrypoints": entrypoints,
        "edges": edges,
        "external_import_observations": external,
        "packaging": {
            "currently_packaged_python": len(packaged),
            "policy_wheel_python": sum(
                bool(classes.get(authority_class, {}).get("production_wheel"))
                for authority_class in classified.values()
            ),
        },
        "structural_errors": errors,
        "backlog": backlog,
        "enforcement_sources": [
            "manual_policy", "python_ast", "declared_dynamic_edges",
            "pyproject_entrypoints", "setuptools_package_discovery",
        ],
    }
    report["report_digest"] = _digest_object(report)
    return report


def mode_exit_code(report: dict[str, Any], mode: str) -> int:
    if report["structural_errors"]:
        return EXIT_FAILURE
    if mode == "require-clean" and report["backlog"]:
        return EXIT_FAILURE
    return EXIT_OK


def _write_report(report: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    os.replace(temporary, target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate manual module authority against observations")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--codegraph", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--mode", choices=["record", "require-clean"], required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.root, args.policy, args.codegraph)
        output = (
            args.state_root.resolve() / "evidence" / "authority"
            / report["source_tree"] / "observed-graph.json"
        )
        _write_report(report, output)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as exc:
        print(f"authority observation failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    payload_digest = "sha256:" + _sha256(output.read_bytes())
    print(
        f"authority status={report['status']} structural_errors={len(report['structural_errors'])} "
        f"open_backlog={len(report['backlog'])} report={report['report_digest']}"
    )
    print(f"JC_ARTIFACT\tauthority-observed-graph\t{output}\t{payload_digest}")
    return mode_exit_code(report, args.mode)


if __name__ == "__main__":
    raise SystemExit(main())

"""W5-05 current-authority convergence gates."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
import tomllib


REPO = Path(__file__).resolve().parents[2]
POLICY = REPO / "docs" / "architecture" / "module-authority.json"
DEPLOYABLE = {"FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT"}
RETIRED_REGISTRIES = (
    REPO / "docs" / "architecture" / "module-authority-v4.json",
    REPO / "docs" / "architecture" / "module-authority-registry.json",
)
RETIRED_MARKERS = (
    "addons/workbuddy_mcp.py",
    "compiler_core/argumentation_v2.py",
    "compiler_core/backend_router_v1.py",
    "compiler_core/certificate_v1.py",
    "compiler_core/compat_v3_v4.py",
    "compiler_core/contracts_v4.py",
    "compiler_core/fact_admission_v1.py",
    "compiler_core/legal_ir_v3.py",
    "compiler_core/proleg_translator.py",
    "compiler_core/source_service_v2.py",
    "schemas/jc-v3.schema.json",
    "schemas/w1b/",
)


def _policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def _module_name(path: str) -> str:
    value = path[:-3].replace("/", ".")
    return value.removesuffix(".__init__")


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports


def test_current_claims_have_one_authority() -> None:
    policy = _policy()
    rules = policy["path_rules"]
    by_path = {row["path"]: row for row in rules}

    assert POLICY.is_file()
    assert not any(path.exists() for path in RETIRED_REGISTRIES)
    assert len(by_path) == len(rules)
    assert set(policy["authority_roles"]) == {
        "application", "certificate_issuer", "contract", "independent_checker",
    }
    assert all(
        by_path[declaration["target_path"]]["class"] == "FORMAL_CORE"
        for declaration in policy["authority_roles"].values()
    )
    assert not set(RETIRED_MARKERS) & set(by_path)

    from compiler_core.audit import AuditEventV4
    from compiler_core.audit_bundle import AuditEventV4 as BundledAuditEventV4

    assert AuditEventV4 is BundledAuditEventV4
    assert AuditEventV4.__module__ == "compiler_core.audit"
    audit_imports = _module_imports(REPO / "compiler_core" / "audit.py")
    assert {module for module in audit_imports if module.startswith("compiler_core.")} == {
        "compiler_core.contracts"
    }


def test_declared_current_modules_exist_and_import() -> None:
    current = [
        row for row in _policy()["path_rules"]
        if row["class"] in DEPLOYABLE and row["path"].endswith(".py")
    ]
    assert current
    for row in current:
        path = REPO / row["path"]
        assert path.is_file(), row["path"]
        assert importlib.import_module(_module_name(row["path"])) is not None


def test_deployable_import_graph_has_one_application_sink() -> None:
    policy = _policy()
    rules = {row["path"]: row["class"] for row in policy["path_rules"]}
    modules = {
        _module_name(path): path
        for path, authority_class in rules.items()
        if authority_class in DEPLOYABLE and path.endswith(".py")
    }
    graph: dict[str, set[str]] = {path: set() for path in modules.values()}
    for module, source in modules.items():
        allowed = set(policy["classes"][rules[source]]["may_import"])
        for imported in _module_imports(REPO / source):
            target = modules.get(imported)
            if target is None:
                continue
            assert rules[target] in allowed, f"{source} -> {target}"
            graph[source].add(target)

    sink = policy["authority_roles"]["application"]["target_path"]
    for source, authority_class in rules.items():
        if authority_class != "PUBLIC_ADAPTER":
            continue
        seen = {source}
        pending = [source]
        while pending:
            pending.extend(graph[pending.pop()] - seen)
            seen.update(pending)
        assert sink in seen, f"{source} does not reach {sink}"

    scripts = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["scripts"]
    assert scripts == {
        "jc": "compiler_core.cli:main",
        "jc-formal": "compiler_core.formal_bridge:main",
    }


def test_current_architecture_docs_are_v4_only() -> None:
    current_docs = (
        POLICY,
        REPO / "docs" / "architecture" / "contract-authority-v4.md",
        REPO / "docs" / "architecture" / "runtime-path-inventory.md",
    )
    joined = "\n".join(path.read_text(encoding="utf-8") for path in current_docs)
    for marker in RETIRED_MARKERS:
        assert marker not in joined
    assert "compiler_core/contracts.py" in joined
    assert "schemas/jc-v4.schema.json" in joined
    assert "compiler_core/application.py" in joined

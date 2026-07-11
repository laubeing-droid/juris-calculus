"""原子审计包、内容寻址pack缓存、完整性校验和离线语义replay。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from compiler_core.application import evaluate_case
from compiler_core.audit import AuditEvent, AuditRecorder, GraphDocument, build_reasoning_graph
from compiler_core.canonical_serialization import semantic_digest
from compiler_core.contracts import CanonicalResult, CaseRequest, SemanticResult
from compiler_core.rule_packs import LoadedRulePack, RulePackError, RulePackRegistry, sha256_file


BUNDLE_SCHEMA_VERSION = "1.0"
_BUNDLE_FILES = ("graph.json", "input.json", "events.jsonl", "manifest.json", "result.json")


class AuditBundleError(RuntimeError):
    """持久化、完整性、隐私或replay错误，code映射CLI退出码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuditBundle:
    """已完成审计包的逻辑引用；path只供本地调用方，不进入机器stdout。"""

    result: CanonicalResult
    graph: GraphDocument
    events: tuple[AuditEvent, ...]
    run_directory: Path
    bundle_digest: str

    def public_dict(self) -> dict[str, Any]:
        """返回不泄漏绝对状态目录的机器结果。"""

        return {
            "canonical_result": self.result.to_dict(),
            "graph_digest": self.graph.graph_digest,
            "events_digest": semantic_digest([event.to_dict() for event in self.events]),
            "bundle_digest": self.bundle_digest,
            "run_id": self.result.semantic.run_id,
        }


@dataclass(frozen=True)
class VerifiedAuditBundle:
    """通过文件与语义摘要验证的审计包材料。"""

    request: CaseRequest
    semantic_result: SemanticResult
    graph_payload: dict[str, Any]
    events: tuple[AuditEvent, ...]
    manifest: dict[str, Any]
    bundle_digest: str
    run_directory: Path


def default_state_root() -> Path:
    """返回用户级state root，默认不写仓库。"""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "juris-calculus"
    xdg = os.environ.get("XDG_STATE_HOME")
    return Path(xdg) / "juris-calculus" if xdg else Path.home() / ".local" / "state" / "juris-calculus"


def state_root_diagnostics(state_root: Path | None = None) -> dict[str, Any]:
    """检查用户state目录可写性、仓库隔离、空间和权限能力边界。"""

    root = Path(state_root or default_state_root()).resolve()
    in_repository = _is_inside_repository(root)
    writable = False
    error_code = ""
    if not in_repository:
        try:
            _ensure_private_directory(root)
            probe = root / ".doctor-write-probe"
            _atomic_write(probe, b"ok\n")
            probe.unlink()
            writable = True
        except OSError as exc:
            error_code = type(exc).__name__
    free_bytes = shutil.disk_usage(root if root.exists() else root.parent).free
    dangerous_permissions = False
    acl_verified = False
    if os.name != "nt" and root.exists():
        dangerous_permissions = bool(root.stat().st_mode & 0o077)
        acl_verified = True
    return {
        "resource": "user-state-root" if state_root is None else "explicit-state-root",
        "writable": writable,
        "in_repository": in_repository,
        "free_bytes": free_bytes,
        "dangerous_permissions": dangerous_permissions,
        "acl_verified": acl_verified,
        "error_code": error_code,
    }


def evaluate_to_audit_bundle(
    request: CaseRequest,
    loaded_pack: LoadedRulePack,
    *,
    state_root: Path | None = None,
) -> AuditBundle:
    """净化请求、正式求值、构图、缓存pack并最后写COMPLETE。"""

    safe_request = audit_safe_request(request)
    run_id = _run_id(safe_request)
    recorder = AuditRecorder(run_id)
    result = evaluate_case(
        safe_request,
        loaded_pack.descriptor,
        loaded_pack.rules,
        source_manifest=loaded_pack.source_manifest,
        audit_sink=recorder,
    )
    graph = build_reasoning_graph(result, recorder.events)
    root = Path(state_root or default_state_root()).resolve()
    _reject_repository_state_root(root)
    _ensure_private_directory(root)
    cache_loaded_pack(loaded_pack, root)
    run_folder = _run_folder(run_id)
    run_directory = root / "runs" / run_folder
    artifact_refs = tuple(f"runs/{run_folder}/{name}" for name in _BUNDLE_FILES + ("checksums.sha256", "COMPLETE"))
    canonical = CanonicalResult(result, artifact_refs)
    bundle_digest = _write_bundle(
        safe_request,
        canonical,
        graph,
        recorder.events,
        recorder.events_digest,
        run_directory,
    )
    return AuditBundle(canonical, graph, recorder.events, run_directory, bundle_digest)


def evaluate_registered_case(
    request: CaseRequest,
    registry: RulePackRegistry,
    *,
    state_root: Path | None = None,
) -> AuditBundle:
    """从显式registry解析pack，并通过唯一application生成完整审计包。"""

    loaded_pack = registry.load_reasoning_pack(request.rule_pack_id)
    return evaluate_to_audit_bundle(request, loaded_pack, state_root=state_root)


def audit_safe_request(request: CaseRequest) -> CaseRequest:
    """移除原始文本/说明/任意provenance，只保留重放所需结构事实。"""

    payload = request.to_dict()
    safe_facts: list[dict[str, Any]] = []
    for fact in payload["facts"]:
        safe_facts.append({
            "id": fact["id"],
            "value": fact.get("value"),
            "status": fact["status"],
            "source_ids": fact.get("source_ids", []),
            "alternatives": fact.get("alternatives", []),
            "human_reviewed": fact.get("human_reviewed", False),
            "created_by": fact.get("created_by", "system"),
            "reasoning_tier": fact.get("reasoning_tier", "P0"),
            "formalizable": fact.get("formalizable", 1.0),
            "taint_status": fact.get("taint_status", "CLEAR"),
            "extraction_confidence": fact.get("extraction_confidence", 1.0),
            "carrier_level": fact.get("carrier_level", ""),
            "source_anchor": fact.get("source_anchor", ""),
        })
    payload["facts"] = safe_facts
    if _contains_absolute_path(payload):
        raise AuditBundleError("AUDIT_PRIVACY_VIOLATION", "structured audit input contains an absolute path")
    return CaseRequest.from_dict(payload)


def cache_loaded_pack(loaded_pack: LoadedRulePack, state_root: Path) -> Path:
    """把pack资源按content digest只缓存一份，并以原manifest重新验证。"""

    cache_root = state_root / "packs" / loaded_pack.descriptor.content_digest
    complete = cache_root / "PACK_COMPLETE"
    if complete.is_file():
        _verify_cached_pack(cache_root, loaded_pack.descriptor.pack_id, loaded_pack.descriptor.content_digest)
        return cache_root
    if cache_root.exists():
        raise AuditBundleError("PACK_CACHE_INCOMPLETE", loaded_pack.descriptor.content_digest)
    staging = cache_root.with_name(cache_root.name + ".tmp")
    if staging.exists():
        raise AuditBundleError("PACK_CACHE_INCOMPLETE", loaded_pack.descriptor.content_digest)
    _ensure_private_directory(staging)
    try:
        for source in loaded_pack.resource_paths:
            relative = source.resolve().relative_to(loaded_pack.config_root)
            target = staging / "configs" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if os.name != "nt":
                target.chmod(0o400)
        _verify_cached_pack(staging, loaded_pack.descriptor.pack_id, loaded_pack.descriptor.content_digest)
        _atomic_write(staging / "PACK_COMPLETE", (loaded_pack.descriptor.content_digest + "\n").encode("utf-8"))
        cache_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, cache_root)
    except Exception:
        raise
    return cache_root


def verify_audit_bundle(state_root: Path, run_id: str) -> VerifiedAuditBundle:
    """验证COMPLETE、逐文件hash、bundle digest和各语义摘要。"""

    if not run_id or any(character in run_id for character in ("/", "\\", "..")):
        raise AuditBundleError("INVALID_RUN_ID", "run_id is not a logical identifier")
    run_directory = Path(state_root).resolve() / "runs" / _run_folder(run_id)
    complete_path = run_directory / "COMPLETE"
    if not complete_path.is_file():
        raise AuditBundleError("AUDIT_BUNDLE_INCOMPLETE", run_id)
    expected_hashes, bundle_digest = _parse_checksums(run_directory / "checksums.sha256")
    for name in _BUNDLE_FILES:
        path = run_directory / name
        if not path.is_file() or sha256_file(path) != expected_hashes.get(name):
            raise AuditBundleError("AUDIT_CHECKSUM_MISMATCH", name)
    calculated_bundle = semantic_digest([
        {"path": name, "sha256": expected_hashes[name]}
        for name in sorted(_BUNDLE_FILES)
    ])
    if calculated_bundle != bundle_digest or complete_path.read_text(encoding="utf-8").strip() != bundle_digest:
        raise AuditBundleError("AUDIT_BUNDLE_DIGEST_MISMATCH", run_id)

    input_payload = _read_json(run_directory / "input.json")
    result_envelope = _read_json(run_directory / "result.json")
    graph_payload = _read_json(run_directory / "graph.json")
    manifest = _read_json(run_directory / "manifest.json")
    events = _read_events(run_directory / "events.jsonl")
    try:
        request = CaseRequest.from_dict(input_payload)
        semantic_result = SemanticResult.from_dict(result_envelope["semantic"])
        _validate_event_sequence(events, run_id)
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditBundleError("INVALID_AUDIT_CONTRACT", type(exc).__name__) from exc
    events_digest = semantic_digest([event.to_dict() for event in events])
    request_digest = semantic_digest(request.to_dict())
    result_digest = semantic_digest({
        key: value
        for key, value in semantic_result.to_dict().items()
        if key != "result_digest"
    })
    graph_digest = semantic_digest({
        key: value
        for key, value in graph_payload.items()
        if key != "graph_digest"
    })
    expected = {
        "request_digest": request_digest,
        "result_digest": result_digest,
        "events_digest": events_digest,
        "graph_digest": graph_digest,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise AuditBundleError("AUDIT_SEMANTIC_DIGEST_MISMATCH", field)
    manifest_expected = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "run_id": run_id,
        "engine_version": semantic_result.engine_version,
        "pack_id": semantic_result.pack_id,
        "pack_version": semantic_result.pack_version,
        "pack_digest": semantic_result.pack_digest,
        "source_ids": list(semantic_result.source_ids),
        "files": list(_BUNDLE_FILES),
    }
    for field, value in manifest_expected.items():
        if manifest.get(field) != value:
            raise AuditBundleError("AUDIT_MANIFEST_MISMATCH", field)
    if semantic_result.result_digest != result_digest:
        raise AuditBundleError("AUDIT_SEMANTIC_DIGEST_MISMATCH", "result.json")
    if graph_payload.get("graph_digest") != graph_digest or result_envelope.get("graph_digest") != graph_digest:
        raise AuditBundleError("AUDIT_SEMANTIC_DIGEST_MISMATCH", "graph.json")
    if result_envelope.get("events_digest") != events_digest:
        raise AuditBundleError("AUDIT_SEMANTIC_DIGEST_MISMATCH", "events.jsonl")
    expected_refs = sorted(
        f"runs/{_run_folder(run_id)}/{name}"
        for name in _BUNDLE_FILES + ("checksums.sha256", "COMPLETE")
    )
    if result_envelope.get("artifact_refs") != expected_refs:
        raise AuditBundleError("AUDIT_MANIFEST_MISMATCH", "artifact_refs")
    return VerifiedAuditBundle(
        request=request,
        semantic_result=semantic_result,
        graph_payload=graph_payload,
        events=events,
        manifest=manifest,
        bundle_digest=bundle_digest,
        run_directory=run_directory,
    )


def replay_audit_bundle(state_root: Path, run_id: str) -> dict[str, Any]:
    """完全离线重跑application并比较语义事件、结果和graph。"""

    verified = verify_audit_bundle(state_root, run_id)
    if _run_id(verified.request) != run_id:
        raise AuditBundleError("REPLAY_MISMATCH", "input:$.run_id:value")
    cache_root = Path(state_root).resolve() / "packs" / verified.semantic_result.pack_digest
    if not (cache_root / "PACK_COMPLETE").is_file():
        raise AuditBundleError("REPLAY_MATERIAL_MISSING", verified.semantic_result.pack_digest)
    try:
        loaded = RulePackRegistry(cache_root / "configs").load_reasoning_pack(verified.semantic_result.pack_id)
    except RulePackError as exc:
        raise AuditBundleError("REPLAY_PACK_INVALID", exc.code) from exc
    if loaded.descriptor.content_digest != verified.semantic_result.pack_digest:
        raise AuditBundleError("REPLAY_PACK_MISMATCH", loaded.descriptor.content_digest)
    recorder = AuditRecorder(run_id)
    replayed = evaluate_case(
        verified.request,
        loaded.descriptor,
        loaded.rules,
        source_manifest=loaded.source_manifest,
        audit_sink=recorder,
    )
    replayed_graph = build_reasoning_graph(replayed, recorder.events)
    comparisons = (
        ("events", [event.to_dict() for event in verified.events], [event.to_dict() for event in recorder.events]),
        ("semantic_result", verified.semantic_result.to_dict(), replayed.to_dict()),
        ("graph", verified.graph_payload, replayed_graph.to_dict()),
    )
    for label, expected, actual in comparisons:
        if expected != actual:
            raise AuditBundleError("REPLAY_MISMATCH", _first_difference(label, expected, actual))
    return {
        "status": "PASS",
        "run_id": run_id,
        "result_digest": replayed.result_digest,
        "events_digest": recorder.events_digest,
        "graph_digest": replayed_graph.graph_digest,
        "bundle_digest": verified.bundle_digest,
    }


def audit_bundle_schema_document() -> dict[str, Any]:
    """返回审计manifest和result envelope的严格公共schema片段。"""

    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    strings = {"type": "array", "items": {"type": "string"}, "uniqueItems": True}
    return {
        "$defs": {
            "AuditBundleManifest": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version", "run_id", "request_digest", "result_digest", "events_digest",
                    "graph_digest", "engine_version", "pack_id", "pack_version", "pack_digest",
                    "source_ids", "files",
                ],
                "properties": {
                    "schema_version": {"const": BUNDLE_SCHEMA_VERSION},
                    "run_id": {"type": "string"},
                    "request_digest": digest,
                    "result_digest": digest,
                    "events_digest": digest,
                    "graph_digest": digest,
                    "engine_version": {"type": "string"},
                    "pack_id": {"type": "string"},
                    "pack_version": {"type": "string"},
                    "pack_digest": digest,
                    "source_ids": strings,
                    "files": strings,
                },
            },
            "AuditResultEnvelope": {
                "type": "object",
                "additionalProperties": False,
                "required": ["semantic", "events_digest", "graph_digest", "artifact_refs"],
                "properties": {
                    "semantic": {"$ref": "#/$defs/SemanticResult"},
                    "events_digest": digest,
                    "graph_digest": digest,
                    "artifact_refs": strings,
                },
            },
        }
    }


def _write_bundle(
    request: CaseRequest,
    canonical: CanonicalResult,
    graph: GraphDocument,
    events: tuple[AuditEvent, ...],
    events_digest: str,
    run_directory: Path,
) -> str:
    """按固定最终化顺序写规范文件、checksums并最后写COMPLETE。"""

    if (run_directory / "COMPLETE").is_file():
        return verify_audit_bundle(run_directory.parents[1], canonical.semantic.run_id).bundle_digest
    if run_directory.exists():
        raise AuditBundleError("AUDIT_BUNDLE_INCOMPLETE", canonical.semantic.run_id)
    _ensure_private_directory(run_directory)
    input_payload = request.to_dict()
    graph_payload = graph.to_dict()
    result_payload = {
        "semantic": canonical.semantic.to_dict(),
        "events_digest": events_digest,
        "graph_digest": graph.graph_digest,
        "artifact_refs": list(canonical.artifact_refs),
    }
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "run_id": canonical.semantic.run_id,
        "request_digest": semantic_digest(input_payload),
        "result_digest": canonical.semantic.result_digest,
        "events_digest": events_digest,
        "graph_digest": graph.graph_digest,
        "engine_version": canonical.semantic.engine_version,
        "pack_id": canonical.semantic.pack_id,
        "pack_version": canonical.semantic.pack_version,
        "pack_digest": canonical.semantic.pack_digest,
        "source_ids": list(canonical.semantic.source_ids),
        "files": list(_BUNDLE_FILES),
    }
    payloads = {
        "input.json": _json_bytes(input_payload),
        "events.jsonl": b"".join(_json_bytes(event.to_dict()) for event in events),
        "result.json": _json_bytes(result_payload),
        "graph.json": _json_bytes(graph_payload),
        "manifest.json": _json_bytes(manifest),
    }
    for name in ("input.json", "events.jsonl", "result.json", "graph.json", "manifest.json"):
        _atomic_write(run_directory / name, payloads[name])
    hashes = {name: sha256_file(run_directory / name) for name in _BUNDLE_FILES}
    bundle_digest = semantic_digest([
        {"path": name, "sha256": hashes[name]}
        for name in sorted(_BUNDLE_FILES)
    ])
    checksum_text = "".join(f"{hashes[name]}  {name}\n" for name in sorted(_BUNDLE_FILES))
    checksum_text += f"BUNDLE  {bundle_digest}\n"
    _atomic_write(run_directory / "checksums.sha256", checksum_text.encode("utf-8"))
    _atomic_write(run_directory / "COMPLETE", (bundle_digest + "\n").encode("utf-8"))
    return bundle_digest


def _verify_cached_pack(cache_root: Path, pack_id: str, digest: str) -> None:
    """用复制后的manifest重新验证缓存，而非信任复制动作。"""

    try:
        result = RulePackRegistry(cache_root / "configs").verify(pack_id)
    except RulePackError as exc:
        raise AuditBundleError("PACK_CACHE_INVALID", exc.code) from exc
    if not result.integrity_valid or result.content_digest != digest:
        raise AuditBundleError("PACK_CACHE_INVALID", pack_id)


def _parse_checksums(path: Path) -> tuple[dict[str, str], str]:
    """严格解析checksums文件，不允许重复/额外规范文件。"""

    if not path.is_file():
        raise AuditBundleError("AUDIT_BUNDLE_INCOMPLETE", "checksums.sha256")
    hashes: dict[str, str] = {}
    bundle_digest = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("BUNDLE  "):
            bundle_digest = line.split("  ", 1)[1]
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or parts[1] in hashes:
            raise AuditBundleError("INVALID_CHECKSUM_FILE", "malformed or duplicate entry")
        hashes[parts[1]] = parts[0]
    if set(hashes) != set(_BUNDLE_FILES) or len(bundle_digest) != 64:
        raise AuditBundleError("INVALID_CHECKSUM_FILE", "file set or bundle digest mismatch")
    return hashes, bundle_digest


def _read_events(path: Path) -> tuple[AuditEvent, ...]:
    """逐行读取JSONL；截断或空行均为篡改。"""

    events: list[AuditEvent] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or any(not line for line in lines):
            raise ValueError("empty event line")
        for line in lines:
            events.append(AuditEvent.from_dict(json.loads(line)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AuditBundleError("INVALID_EVENT_STREAM", type(exc).__name__) from exc
    return tuple(events)


def _validate_event_sequence(events: tuple[AuditEvent, ...], run_id: str) -> None:
    """验证run、连续seq和只向前引用的父事件。"""

    seen: set[str] = set()
    for expected_seq, event in enumerate(events, 1):
        if event.run_id != run_id or event.seq != expected_seq or not set(event.parent_event_ids) <= seen:
            raise AuditBundleError("INVALID_EVENT_SEQUENCE", event.event_id)
        seen.add(event.event_id)


def _atomic_write(path: Path, payload: bytes) -> None:
    """同目录临时文件落盘后原子替换目标。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _ensure_private_directory(path: Path) -> None:
    """创建用户state目录；POSIX收紧权限，Windows不夸称ACL已验证。"""

    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


def _reject_repository_state_root(path: Path) -> None:
    """禁止默认/显式审计目录落入当前源码仓库。"""

    if _is_inside_repository(path):
        raise AuditBundleError("AUDIT_PATH_IN_REPOSITORY", "audit state root must be outside the repository")


def _is_inside_repository(path: Path) -> bool:
    """检测目标或任一祖先的Git工作树标记，不依赖当前工作目录。"""

    return any((candidate / ".git").exists() for candidate in (path, *path.parents))


def _contains_absolute_path(value: Any) -> bool:
    """递归检测结构字段中的Windows/POSIX绝对机器路径。"""

    if isinstance(value, Mapping):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_absolute_path(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(
        (len(value) >= 3 and value[1:3] in {":\\", ":/"} and value[0].isalpha())
        or value.startswith(("/home/", "/Users/", "/tmp/", "/var/", "/private/"))
    )


def _run_id(request: CaseRequest) -> str:
    """复用application内容寻址run ID算法。"""

    from compiler_core.canonical_serialization import content_id

    return content_id("run", request.to_dict())


def _run_folder(run_id: str) -> str:
    """把逻辑run ID确定性编码为Windows/POSIX均合法的目录名。"""

    folder = run_id.replace("::", "--")
    if not folder or any(character in folder for character in '<>:"/\\|?*'):
        raise AuditBundleError("INVALID_RUN_ID", "run_id cannot be encoded as a directory")
    return folder


def _json_bytes(value: Any) -> bytes:
    """写出确定性UTF-8 JSON并保留单一末尾换行。"""

    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    """读取顶层JSON对象。"""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditBundleError("INVALID_AUDIT_JSON", path.name) from exc
    if not isinstance(value, dict):
        raise AuditBundleError("INVALID_AUDIT_JSON", path.name)
    return value


def _first_difference(label: str, expected: Any, actual: Any, path: str = "$") -> str:
    """返回确定性首个差异位置，不输出私有完整值。"""

    if type(expected) is not type(actual):
        return f"{label}:{path}:type"
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return f"{label}:{path}:keys"
        for key in sorted(expected):
            difference = _first_difference(label, expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
        return ""
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{label}:{path}:length"
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = _first_difference(label, left, right, f"{path}[{index}]")
            if difference:
                return difference
        return ""
    return "" if expected == actual else f"{label}:{path}:value"

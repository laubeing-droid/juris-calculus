"""版本化规则包manifest、文件hash和正式准入验证。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import yaml

from compiler_core.types import DataQuality, normalize_rule_admission


PACK_SCHEMA_VERSION = "1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_MODALITIES = {"OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE", "UNKNOWN", ""}
_TEXT_HASH_SUFFIXES = {".json", ".yaml", ".yml"}


class RulePackError(ValueError):
    """规则包结构或选择错误；code供CLI稳定映射。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PackVerification:
    """一次manifest完整性与正式可用性验证结果。"""

    pack_id: str
    version: str
    jurisdiction: str
    kind: str
    integrity_valid: bool
    reasoning_ready: bool
    content_digest: str
    inventory: dict[str, int]
    candidate_rule_ids: tuple[str, ...]
    issues: tuple[dict[str, str], ...]
    development_override: bool = False
    override_path_hash: str = ""

    def to_dict(self, *, include_candidates: bool = True) -> dict[str, Any]:
        """返回确定性机器结果；list命令可省略大候选列表。"""

        payload = {
            "pack_id": self.pack_id,
            "version": self.version,
            "jurisdiction": self.jurisdiction,
            "kind": self.kind,
            "integrity_valid": self.integrity_valid,
            "reasoning_ready": self.reasoning_ready,
            "content_digest": self.content_digest,
            "inventory": dict(self.inventory),
            "candidate_rule_count": len(self.candidate_rule_ids),
            "issues": [dict(issue) for issue in self.issues],
            "development_override": self.development_override,
            "override_path_hash": self.override_path_hash,
        }
        if include_candidates:
            payload["candidate_rule_ids"] = list(self.candidate_rule_ids)
        return payload


@dataclass(frozen=True)
class LoadedRulePack:
    """通过完整门禁后可交给application和离线缓存的规则包材料。"""

    descriptor: Any
    rules: tuple[Any, ...]
    source_manifest: Any
    verification: PackVerification
    manifest_path: Path
    config_root: Path
    resource_paths: tuple[Path, ...]


@dataclass(frozen=True)
class LoadedCorpusPack:
    """通过manifest完整性门禁、但不具备正式推理资格的语料材料。"""

    verification: PackVerification
    manifest: Mapping[str, Any]
    manifest_path: Path
    rule_paths: tuple[Path, ...]
    source_paths: tuple[Path, ...]
    config_root: Path


class RulePackRegistry:
    """扫描单一configs根下的pack manifests并拒绝重复pack ID。"""

    def __init__(self, config_root: Path, *, development_override: bool = False) -> None:
        self.config_root = Path(config_root).resolve()
        self.development_override = development_override
        self.override_path_hash = (
            hashlib.sha256(str(self.config_root).encode("utf-8")).hexdigest()
            if development_override
            else ""
        )
        # Pack由manifest内容摘要绑定；同一registry内可安全复用只读加载结果，不复用案件状态或recorder。
        self._reasoning_cache: dict[str, LoadedRulePack] = {}

    def manifests(self) -> dict[str, Path]:
        """返回pack ID到manifest路径的稳定映射。"""

        discovered: dict[str, Path] = {}
        for path in sorted((self.config_root / "packs").glob("*/manifest.yaml")):
            document = _load_yaml_mapping(path)
            pack_id = str(document.get("pack_id", "")).strip()
            if not pack_id:
                raise RulePackError("MISSING_PACK_ID", f"manifest has no pack_id: {path.name}")
            if pack_id in discovered:
                raise RulePackError("DUPLICATE_PACK_ID", pack_id)
            discovered[pack_id] = path
        return discovered

    def verify(self, pack_id: str) -> PackVerification:
        """验证一个已注册pack；缺失可选pack不得回退其他法域。"""

        manifests = self.manifests()
        if pack_id not in manifests:
            raise RulePackError("PACK_NOT_INSTALLED", pack_id)
        return verify_pack_manifest(
            manifests[pack_id],
            self.config_root,
            development_override=self.development_override,
            override_path_hash=self.override_path_hash,
        )

    def list_installed(self) -> tuple[dict[str, Any], ...]:
        """只读manifest摘要，不把list命令伪装成完整hash验证。"""

        summaries: list[dict[str, Any]] = []
        for pack_id, path in sorted(self.manifests().items()):
            document = _load_yaml_mapping(path)
            summaries.append({
                "pack_id": pack_id,
                "version": str(document.get("version", "")),
                "jurisdiction": str(document.get("jurisdiction", "")),
                "kind": str(document.get("kind", "")),
                "declared_status": str(document.get("status", "")),
                "content_digest": str(document.get("content_digest", "")),
                "inventory": dict(document.get("inventory", {})),
                "verification_status": "not_run",
                "development_override": self.development_override,
                "override_path_hash": self.override_path_hash,
            })
        return tuple(summaries)

    def verify_all(self) -> tuple[PackVerification, ...]:
        """按pack ID排序验证全部已安装manifest。"""

        return tuple(self.verify(pack_id) for pack_id in sorted(self.manifests()))

    def load_reasoning_pack(self, pack_id: str) -> LoadedRulePack:
        """加载已验证且非空的official pack；candidate pack不得进入application。"""

        if pack_id in self._reasoning_cache:
            return self._reasoning_cache[pack_id]

        verification = self.verify(pack_id)
        if not verification.integrity_valid or not verification.reasoning_ready:
            raise RulePackError("PACK_NOT_REASONING_READY", pack_id)
        manifest_path = self.manifests()[pack_id]
        document = _load_yaml_mapping(manifest_path)
        from compiler_core.contracts import RulePackDescriptor
        from compiler_core.evaluator import load_rules_from_yaml
        from compiler_core.source_manifest import SourceManifest

        rules: list[Any] = []
        resources: list[Path] = [manifest_path]
        for entry in document["rule_files"]:
            path = self.config_root / entry["path"]
            rules.extend(load_rules_from_yaml(str(path)))
            resources.append(path)
        source_manifest = SourceManifest()
        for entry in document["source_files"]:
            path = self.config_root / entry["path"]
            source_manifest.load(str(path))
            resources.append(path)
        for entry in document["config_files"]:
            resources.append(self.config_root / entry["path"])
        candidate_ids = set(verification.candidate_rule_ids)
        verified_ids = tuple(sorted(rule.id for rule in rules if rule.id not in candidate_ids))
        descriptor = RulePackDescriptor(
            pack_id=verification.pack_id,
            version=verification.version,
            content_digest=verification.content_digest,
            verified_rule_ids=verified_ids,
        )
        loaded = LoadedRulePack(
            descriptor=descriptor,
            rules=tuple(rules),
            source_manifest=source_manifest,
            verification=verification,
            manifest_path=manifest_path,
            config_root=self.config_root,
            resource_paths=tuple(resources),
        )
        self._reasoning_cache[pack_id] = loaded
        return loaded

    def load_corpus_pack(self, pack_id: str) -> LoadedCorpusPack:
        """加载完整性有效的语料pack，且不把candidate晋升为reasoning-ready。"""

        verification = self.verify(pack_id)
        if not verification.integrity_valid:
            raise RulePackError("PACK_INTEGRITY_INVALID", pack_id)
        manifest_path = self.manifests()[pack_id]
        document = _load_yaml_mapping(manifest_path)
        rule_paths = tuple(
            (self.config_root / str(entry["path"])).resolve()
            for entry in document.get("rule_files", ())
        )
        source_paths = tuple(
            (self.config_root / str(entry["path"])).resolve()
            for entry in document.get("source_files", ())
        )
        for path in (*rule_paths, *source_paths):
            try:
                path.relative_to(self.config_root)
            except ValueError as exc:
                raise RulePackError("PACK_PATH_ESCAPE", path.name) from exc
        return LoadedCorpusPack(
            verification=verification,
            manifest=document,
            manifest_path=manifest_path,
            rule_paths=rule_paths,
            source_paths=source_paths,
            config_root=self.config_root,
        )


def verify_pack_manifest(
    manifest_path: Path,
    config_root: Path,
    *,
    development_override: bool = False,
    override_path_hash: str = "",
) -> PackVerification:
    """校验manifest、文件hash、ID唯一性、计数及正式来源准入。"""

    document = _load_yaml_mapping(manifest_path)
    issues: list[dict[str, str]] = []
    required = {
        "schema_version", "pack_id", "version", "kind", "jurisdiction", "governing_law",
        "effective_from", "effective_to", "rule_files", "source_files", "inventory",
        "config_files", "content_digest", "build_commit",
    }
    for field in sorted(required - set(document)):
        _issue(issues, "MISSING_MANIFEST_FIELD", field)
    if document.get("schema_version") != PACK_SCHEMA_VERSION:
        _issue(issues, "UNSUPPORTED_PACK_SCHEMA", str(document.get("schema_version", "")))
    _validate_date(document.get("effective_from"), "effective_from", issues, allow_empty=False)
    _validate_date(document.get("effective_to"), "effective_to", issues, allow_empty=True)
    _validate_effective_range(document, issues)
    if not _SHA256_RE.fullmatch(str(document.get("content_digest", ""))):
        _issue(issues, "INVALID_CONTENT_DIGEST", "content_digest must be SHA-256")

    config_root = Path(config_root).resolve()
    rules: list[dict[str, Any]] = []
    source_entries: dict[str, dict[str, Any]] = {}
    for entry in _file_entries(document.get("rule_files"), "rule_files", issues):
        path = _validated_resource_path(config_root, entry, issues)
        if path is None:
            continue
        _verify_file_hash(path, entry, issues)
        loaded = _load_yaml_mapping(path)
        file_rules = loaded.get("rules", [])
        if not isinstance(file_rules, list):
            _issue(issues, "INVALID_RULE_ARRAY", entry["path"])
            continue
        meta = loaded.get("_meta", {})
        if isinstance(meta, Mapping) and "total" in meta and meta["total"] != len(file_rules):
            _issue(issues, "META_TOTAL_MISMATCH", entry["path"])
        rules.extend(dict(rule) for rule in file_rules if isinstance(rule, Mapping))
    for entry in _file_entries(document.get("source_files"), "source_files", issues):
        path = _validated_resource_path(config_root, entry, issues)
        if path is None:
            continue
        _verify_file_hash(path, entry, issues)
        loaded = _load_yaml_mapping(path)
        for source in loaded.get("sources", []) if isinstance(loaded.get("sources", []), list) else []:
            if not isinstance(source, Mapping):
                continue
            source_id = str(source.get("source_id", ""))
            if source_id in source_entries:
                _issue(issues, "DUPLICATE_SOURCE_ID", source_id)
            source_entries[source_id] = dict(source)
    for entry in _file_entries(document.get("config_files"), "config_files", issues):
        path = _validated_resource_path(config_root, entry, issues)
        if path is not None:
            _verify_file_hash(path, entry, issues)

    ids = [str(rule.get("id", "")) for rule in rules]
    for rule_id in sorted(rule_id for rule_id, count in Counter(ids).items() if count > 1):
        _issue(issues, "DUPLICATE_RULE_ID", rule_id)
    if any(not rule_id for rule_id in ids):
        _issue(issues, "EMPTY_RULE_ID", "one or more rules have no id")

    eligible_ids: list[str] = []
    candidate_ids: list[str] = []
    official = document.get("kind") == "official"
    relation_validity = _validate_rule_relations(rules, issues) if official else {}
    for rule in rules:
        rule_id = str(rule.get("id", ""))
        eligible = (
            official
            and relation_validity.get(rule_id, False)
            and _official_rule_eligible(rule, source_entries, issues)
        )
        (eligible_ids if eligible else candidate_ids).append(rule_id)
    inventory = {
        "corpus_total": len(rules),
        "reasoning_eligible_total": len(eligible_ids),
        "candidate_only_total": len(candidate_ids),
    }
    expected_inventory = document.get("inventory")
    if expected_inventory != inventory:
        _issue(issues, "INVENTORY_MISMATCH", json.dumps(inventory, sort_keys=True))
    calculated_digest = manifest_content_digest(document)
    if document.get("content_digest") != calculated_digest:
        _issue(issues, "MANIFEST_DIGEST_MISMATCH", calculated_digest)

    blocker_codes = {issue["code"] for issue in issues}
    integrity_valid = not blocker_codes
    reasoning_ready = bool(
        integrity_valid
        and official
        and eligible_ids
        and document.get("status") == "active"
    )
    if official and not eligible_ids:
        _issue(issues, "EMPTY_OFFICIAL_PACK", "no reasoning-eligible rules")
    return PackVerification(
        pack_id=str(document.get("pack_id", "")),
        version=str(document.get("version", "")),
        jurisdiction=str(document.get("jurisdiction", "")),
        kind=str(document.get("kind", "")),
        integrity_valid=integrity_valid,
        reasoning_ready=reasoning_ready,
        content_digest=str(document.get("content_digest", "")),
        inventory=inventory,
        candidate_rule_ids=tuple(sorted(candidate_ids)),
        issues=tuple(sorted(issues, key=lambda item: (item["code"], item["detail"]))),
        development_override=development_override,
        override_path_hash=override_path_hash,
    )


def manifest_content_digest(document: Mapping[str, Any]) -> str:
    """计算排除content_digest自身的规范manifest摘要。"""

    projection = {key: value for key, value in document.items() if key != "content_digest"}
    encoded = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    """计算文件SHA-256；文本资源规范化CRLF，避免跨平台规则包漂移。"""

    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if path.suffix.lower() in _TEXT_HASH_SUFFIXES:
            for line in stream:
                digest.update(line.replace(b"\r\n", b"\n"))
        else:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _official_rule_eligible(
    raw_rule: Mapping[str, Any],
    source_entries: Mapping[str, Mapping[str, Any]],
    issues: list[dict[str, str]],
) -> bool:
    """执行official规则的来源、质量、日期和modality准入。"""

    rule = normalize_rule_admission(raw_rule)
    rule_id = str(rule.get("id", ""))
    anchor = str(rule.get("source_anchor", ""))
    source = source_entries.get(anchor)
    source_verified = bool(
        source
        and source.get("verified") is True
        and _SHA256_RE.fullmatch(str(source.get("content_hash", "")))
    )
    quality = str(rule.get("data_quality", DataQuality.CLEAN.value))
    modality = str(rule.get("norm_modality", ""))
    dates_valid = _rule_dates_valid(rule, rule_id, issues)
    modality_valid = modality in _ALLOWED_MODALITIES
    if not modality_valid:
        _issue(issues, "INVALID_RULE_MODALITY", rule_id)
    return bool(anchor and source_verified and quality != DataQuality.CANDIDATE_ONLY.value and dates_valid and modality_valid)


def _rule_dates_valid(rule: Mapping[str, Any], rule_id: str, issues: list[dict[str, str]]) -> bool:
    """验证规则可选生效/失效日期，不补造缺失日期。"""

    valid = True
    for field in ("valid_from", "valid_to"):
        value = rule.get(field)
        if not value:
            continue
        try:
            date.fromisoformat(str(value))
        except ValueError:
            _issue(issues, "INVALID_RULE_DATE", f"{rule_id}:{field}")
            valid = False
    return valid


def _validate_rule_relations(
    rules: Iterable[Mapping[str, Any]],
    issues: list[dict[str, str]],
) -> dict[str, bool]:
    """验证official exception与priority引用，防止悬空覆盖关系进入索引。"""

    material = tuple(rules)
    rule_ids = {str(rule.get("id", "")) for rule in material}
    claim_ids = {str(rule.get("head_claim", "")) for rule in material}
    validity: dict[str, bool] = {}
    for rule in material:
        rule_id = str(rule.get("id", ""))
        valid = True
        exceptions = rule.get("exception_chain", [])
        priorities = rule.get("priority_over", [])
        if not isinstance(exceptions, list) or not isinstance(priorities, list):
            _issue(issues, "INVALID_RULE_RELATION", rule_id)
            validity[rule_id] = False
            continue
        for target in exceptions:
            if str(target) not in rule_ids:
                _issue(issues, "UNKNOWN_EXCEPTION_TARGET", f"{rule_id}:{target}")
                valid = False
        for target in priorities:
            if str(target) not in rule_ids | claim_ids:
                _issue(issues, "UNKNOWN_PRIORITY_TARGET", f"{rule_id}:{target}")
                valid = False
        validity[rule_id] = valid
    return validity


def _file_entries(value: Any, label: str, issues: list[dict[str, str]]) -> tuple[dict[str, str], ...]:
    """严格解析manifest文件项。"""

    if not isinstance(value, list):
        _issue(issues, "INVALID_FILE_LIST", label)
        return ()
    entries: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            _issue(issues, "INVALID_FILE_ENTRY", label)
            continue
        entries.append({"path": str(item["path"]), "sha256": str(item["sha256"])})
    return tuple(entries)


def _validated_resource_path(
    config_root: Path,
    entry: Mapping[str, str],
    issues: list[dict[str, str]],
) -> Path | None:
    """拒绝绝对路径和越出configs根的manifest引用。"""

    relative = Path(entry["path"])
    if relative.is_absolute() or ".." in relative.parts:
        _issue(issues, "UNSAFE_RESOURCE_PATH", entry["path"])
        return None
    path = (config_root / relative).resolve()
    if config_root not in path.parents:
        _issue(issues, "UNSAFE_RESOURCE_PATH", entry["path"])
        return None
    if not path.is_file():
        _issue(issues, "RESOURCE_NOT_FOUND", entry["path"])
        return None
    return path


def _verify_file_hash(path: Path, entry: Mapping[str, str], issues: list[dict[str, str]]) -> None:
    """精确比较manifest文件hash。"""

    if not _SHA256_RE.fullmatch(entry["sha256"]):
        _issue(issues, "INVALID_FILE_HASH", entry["path"])
    elif sha256_file(path) != entry["sha256"]:
        _issue(issues, "FILE_HASH_MISMATCH", entry["path"])


def _validate_date(value: Any, field: str, issues: list[dict[str, str]], *, allow_empty: bool) -> None:
    """验证manifest ISO日期。"""

    if allow_empty and value in (None, ""):
        return
    try:
        date.fromisoformat(str(value))
    except ValueError:
        _issue(issues, "INVALID_MANIFEST_DATE", field)


def _validate_effective_range(document: Mapping[str, Any], issues: list[dict[str, str]]) -> None:
    """拒绝结束日期早于开始日期。"""

    start = document.get("effective_from")
    end = document.get("effective_to")
    if not start or not end:
        return
    try:
        if date.fromisoformat(str(end)) < date.fromisoformat(str(start)):
            _issue(issues, "INVALID_EFFECTIVE_RANGE", "effective_to precedes effective_from")
    except ValueError:
        return


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """读取UTF-8 YAML并要求顶层对象。"""

    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RulePackError("MANIFEST_READ_ERROR", type(exc).__name__) from exc
    if not isinstance(value, Mapping):
        raise RulePackError("INVALID_YAML_DOCUMENT", Path(path).name)
    return dict(value)


def _issue(issues: list[dict[str, str]], code: str, detail: str) -> None:
    """追加不含机器路径和异常repr的确定性问题。"""

    issues.append({"code": code, "detail": str(detail)})

"""Neutral presentation of an independently verified V4 audit bundle."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
from pathlib import Path
from typing import Any

import yaml

from compiler_core.audit_bundle import VerifiedAuditBundleV4
from compiler_core.resources import neutral_profile_path
from compiler_core.version import __version__


class RendererV4Error(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RenderOutputV4:
    result_digest: str
    renderer_version: str
    profile_id: str
    profile_version: str
    audience: str
    locale: str
    format: str
    content: str
    content_sha256: str
    warnings: tuple[str, ...]

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        document: dict[str, Any] = {
            "result_digest": self.result_digest,
            "renderer_version": self.renderer_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "audience": self.audience,
            "locale": self.locale,
            "format": self.format,
            "content_sha256": self.content_sha256,
            "warnings": list(self.warnings),
        }
        if include_content:
            document["content"] = self.content
        return document


def _profile() -> dict[str, Any]:
    path = neutral_profile_path()
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RendererV4Error("PROFILE_UNAVAILABLE", type(exc).__name__) from exc
    required = {
        "schema_version", "profile_id", "version", "locale", "heading_order",
        "heading_aliases", "forbidden_phrases",
    }
    if not isinstance(document, dict) or not required <= set(document):
        raise RendererV4Error("INVALID_RENDERER_PROFILE", "neutral profile is incomplete")
    if document["schema_version"] != "1.0" or document["profile_id"] != "neutral":
        raise RendererV4Error("INVALID_RENDERER_PROFILE", "neutral profile identity drifted")
    return document


def _ref(reference: object) -> str:
    kind = getattr(reference, "kind", "")
    digest = getattr(getattr(reference, "digest", None), "hex", "")
    return f"{kind}:{digest}"


def _lines(verified: VerifiedAuditBundleV4, audience: str) -> list[str]:
    result = verified.result
    lines = [
        "# JC V4 verified result",
        "",
        "## status",
        "",
        f"- decision_status: `{result.decision_status.value}`",
        f"- execution_status: `{result.execution_status.value}`",
        f"- certificate_kind: `{result.certificate_kind.value}`",
        f"- review_status: `{result.review_state.status}`",
        f"- audience: `{audience}`",
        "",
        "## claims",
        "",
    ]
    lines.extend(
        f"- `{claim.claim_id}`" for claim in result.claims
    )
    if not result.claims:
        lines.append("- none")
    lines.extend(["", "## sources", ""])
    sources = sorted({_ref(ref) for claim in result.claims for ref in claim.source_refs})
    lines.extend(f"- `{value}`" for value in sources)
    if not sources:
        lines.append("- none")
    lines.extend(["", "## risks", ""])
    lines.extend(f"- `{value}`" for value in result.risk_codes)
    if not result.risk_codes:
        lines.append("- none")
    lines.extend(["", "## review", ""])
    lines.append(f"- required: `{str(result.review_state.status != 'not_required').lower()}`")
    lines.extend(f"- missing: `{item.fact_id}`" for item in result.missing_facts)
    lines.extend([
        "",
        f"- run_identity_ref: `{_ref(result.run_identity_ref)}`",
        f"- result_digest: `{result.result_digest}`",
    ])
    return lines


def _mermaid(verified: VerifiedAuditBundleV4) -> str:
    result = verified.result
    lines = [
        "flowchart TD",
        f'  result["{result.decision_status.value}"]',
    ]
    for index, claim in enumerate(result.claims):
        label = claim.claim_id.replace('"', "'")
        lines.append(f'  claim{index}["{label}"] --> result')
    return "\n".join(lines) + "\n"


def render_verified_bundle(
    verified: VerifiedAuditBundleV4,
    *,
    output_format: str = "markdown",
    audience: str = "agent",
    profile_path: Path | None = None,
) -> RenderOutputV4:
    """Render only a verifier-issued bundle; never evaluate or infer new facts."""

    if type(verified) is not VerifiedAuditBundleV4 or verified.verification.status != "VERIFIED":
        raise RendererV4Error("VERIFIED_BUNDLE_REQUIRED", "render requires a verified V4 bundle")
    if output_format not in {"markdown", "mermaid", "html"}:
        raise RendererV4Error("INVALID_RENDER_FORMAT", "format must be markdown, mermaid, or html")
    if audience not in {"agent", "lawyer"}:
        raise RendererV4Error("INVALID_AUDIENCE", "audience must be agent or lawyer")
    if profile_path is not None:
        raise RendererV4Error("PROFILE_OVERRIDE_DISABLED", "only the neutral profile is allowed")
    profile = _profile()
    before = verified.result.to_dict()
    markdown = "\n".join(_lines(verified, audience)).rstrip() + "\n"
    if output_format == "mermaid":
        content = _mermaid(verified)
    elif output_format == "html":
        content = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'">'
            f"</head><body><pre>{html.escape(markdown)}</pre></body></html>\n"
        )
    else:
        content = markdown
    if verified.result.to_dict() != before:
        raise RendererV4Error("CANONICAL_RESULT_DRIFT", "renderer changed the formal result")
    for phrase in profile.get("forbidden_phrases", ()):
        if str(phrase).casefold() in content.casefold():
            raise RendererV4Error("FORBIDDEN_PHRASE_EMITTED", str(phrase))
    warnings = tuple(sorted({*verified.result.risk_codes, *verified.result.taint_codes}))
    return RenderOutputV4(
        result_digest=verified.result.result_digest.hex,
        renderer_version=__version__,
        profile_id=str(profile["profile_id"]),
        profile_version=str(profile["version"]),
        audience=audience,
        locale=str(profile["locale"]),
        format=output_format,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        warnings=warnings,
    )


__all__ = ("RenderOutputV4", "RendererV4Error", "render_verified_bundle")

#!/usr/bin/env python3
"""
V6 FastMCP Server for juris-calculus
Exposes LegalOS kernel as MCP tools for WorkBuddy integration.

Usage:
    python mcp_server.py
    # Or register as MCP tool in WorkBuddy/Codex config
"""

import json, sys, os, uuid, hashlib
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(__file__))

from compiler_core.types import LegalRule, LegalFact, LegalClaim, IRState, TaintNode
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.domain_config import get_domain_config, check_discretionary

# V6 证据分类器已移至 contrib/ — MCP Server 降级加载
try:
    from compiler_core.classifier import EvidenceClassifier, detect_label_hijacking, verify_raw_text
    _classifier = EvidenceClassifier()
except ImportError:
    _classifier = None
# === Global state ===
_config = get_domain_config()
_rules_cache: Dict[str, FixpointEvaluator] = {}


def _get_evaluator(rules_path: str = "configs/zh_CN/rules.yaml") -> FixpointEvaluator:
    """Lazy-load and cache evaluator for a rules path."""
    if rules_path not in _rules_cache:
        rules = load_rules_from_yaml(rules_path)
        _rules_cache[rules_path] = FixpointEvaluator(rules, _config)
    return _rules_cache[rules_path]


def _generate_trace_id() -> str:
    """Generate unique ExecutionTraceID."""
    ts = datetime.now(timezone.utc).isoformat()
    uid = uuid.uuid4().hex[:8]
    return f"TRACE-{ts}-{uid}"


def evidence_review(
    facts: Dict[str, str],
    rules_path: str = "configs/zh_CN/rules.yaml",
    enable_taint_gate: bool = True,
) -> dict:
    """
    EvidenceCopilot: Review case facts against LegalOS kernel.

    Args:
        facts: Dict of fact_id -> description, e.g. {"loan_agreement": "双方签订借条10万"}
        rules_path: Path to rules YAML (default: zh_CN)
        enable_taint_gate: Enable discretionary concept taint detection

    Returns:
        {
            "trace_id": "...",
            "claims": [...],
            "negative_specs": [...],
            "tainted_facts": [...],
            "human_review_required": bool,
            "audit_summary": {...}
        }
    """
    trace_id = _generate_trace_id()
    ev = _get_evaluator(rules_path)
    state = IRState(world_id=trace_id)

    # Build facts
    for fid, desc in facts.items():
        fact = LegalFact(fid, description=desc)
        # Classify evidence carrier level
        fact.carrier_level = _classifier.classify(desc)
        fact.raw_text = desc
        # Discretionary taint check
        if enable_taint_gate and _config.enable_discretionary_taint:
            disc = check_discretionary(desc)
            if disc["tainted"]:
                fact.taint_status = "TAINTED"
                fact.extraction_confidence = disc["confidence_cap"]
        state.facts[fid] = fact

    # Evaluate
    claims_list = []
    halted = False
    try:
        result = ev.evaluate(state)
        for cid, claim in result.claims.items():
            claims_list.append({
                "id": cid,
                "confidence": claim.confidence,
                "taint_chain": claim.taint_summary(),
                "requires_human_review": claim.requires_human_review,
                "trace_id": trace_id,
            })
    except CriticalClarityFailure as e:
        halted = True
        claims_list.append({"error": str(e), "trace_id": trace_id})

    # Tainted facts
    tainted = [
        {"id": fid, "status": f.taint_status, "carrier_level": f.carrier_level,
         "confidence": f.extraction_confidence}
        for fid, f in state.facts.items() if f.taint_status != "CLEAR"
    ]

    # Audit summary
    total = len(claims_list)
    det = sum(1 for c in claims_list if not c.get("requires_human_review", True))
    audit = {
        "trace_id": trace_id,
        "total_claims": total,
        "deterministic": det,
        "tainted": total - det,
        "coverage": round(det / max(1, total), 2),
        "halted": halted,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "trace_id": trace_id,
        "claims": claims_list,
        "tainted_facts": tainted,
        "negative_specs": [],  # TODO: implement NegativeSpec check
        "human_review_required": any(c.get("requires_human_review") for c in claims_list),
        "audit_summary": audit,
    }


def argument_lint(
    argument_text: str,
    stance: str = "BALANCED",
    rules_path: str = "configs/zh_CN/rules.yaml",
) -> dict:
    """
    ArgumentLint: Scan legal argument for structural gaps.

    Args:
        argument_text: Full text of complaint/defense/representation
        stance: "AGGRESSIVE" | "BALANCED" | "DEFENSIVE"
        rules_path: Rules YAML path

    Returns:
        {
            "trace_id": "...",
            "gaps": [...],
            "anti_patterns_hit": [...],
            "structure_score": float
        }
    """
    trace_id = _generate_trace_id()

    # Anti-patterns check
    anti_patterns = {
        "DEFERRED_TO_COURT": ["由法院.*计算", "依法.*计算", "由法院.*酌定"],
        "VAGUE_REFERENCE": ["上述.*金额", "前述.*款项", "相关.*费用"],
        "CIRCULAR_CITATION": ["如前所述", "同上", "详见.*部分"],
    }
    hits = []
    for name, patterns in anti_patterns.items():
        for p in patterns:
            import re
            if re.search(p, argument_text):
                hits.append({"pattern_name": name, "pattern": p})

    return {
        "trace_id": trace_id,
        "gaps": [],  # TODO: subslot type checking
        "anti_patterns_hit": hits,
        "structure_score": max(0.0, 1.0 - len(hits) * 0.2),
        "stance": stance,
    }


def contract_review(
    contract_text: str,
    posture: str = "BALANCED",
    rules_path: str = "configs/zh_CN/rules.yaml",
) -> dict:
    """
    ContractReviewCore: Review contract clauses.

    Args:
        contract_text: Full contract text
        posture: "DOMINANT" | "BALANCED" | "SUPPLICANT"
        rules_path: Rules YAML path

    Returns:
        {
            "trace_id": "...",
            "clauses": [...],
            "risk_level": str,
            "cross_clause_taints": [...]
        }
    """
    trace_id = _generate_trace_id()

    # Basic clause extraction (placeholder - real impl uses LLM for extraction only)
    risk_level = "LOW" if posture == "DOMINANT" else ("MEDIUM" if posture == "BALANCED" else "HIGH")

    return {
        "trace_id": trace_id,
        "clauses": [],
        "risk_level": risk_level,
        "cross_clause_taints": [],
        "posture": posture,
    }


# === MCP Server Shim ===
# If FastMCP is available, use it. Otherwise, provide stdio JSON-RPC fallback.

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False


# ── 统一推理入口（供 FastMCP 和 JSON-RPC fallback 共用）──
def _juris_evaluate_core(domain: str, facts_json: str, source_law: str = "CN",
                          dry_run: bool = False, rules_path: str = "configs/zh_CN/rules.yaml"):
    from pipeline.prc_us_alignment import run_alignment_watchdog

    facts = json.loads(facts_json)
    wd = run_alignment_watchdog(
        json.dumps(facts, ensure_ascii=False),
        source="US" if source_law == "CN" else "CN",
        target=source_law,
    )
    if dry_run:
        return {
            "dry_run": True,
            "validated_facts": wd["pre_triggered_atoms"],
            "blocked_reasons": wd["block_reasons"],
            "direction": wd["direction"],
        }

    ev = _get_evaluator(rules_path)
    state = IRState(world_id="mcp_eval")
    for fid, desc in wd["pre_triggered_atoms"].items():
        state.facts[fid] = LegalFact(fid, str(desc)[:200])
    for fid, desc in facts.items():
        if fid not in wd["pre_triggered_atoms"]:
            state.facts[fid] = LegalFact(fid, str(desc)[:200])

    result = ev.evaluate(state)
    return {
        "domain": domain,
        "source_law": source_law,
        "total_claims": len(result.claims),
        "top_claims": sorted(
            [{"id": c.id[:80], "confidence": round(c.confidence, 2),
              "taint": c.taint_summary()[:100]} for c in result.claims.values()],
            key=lambda x: -x["confidence"],
        )[:10],
        "blocked_reasons": wd["block_reasons"],
    }


def _juris_evaluate_sync(**params):
    """JSON-RPC fallback 同步包装"""
    return _juris_evaluate_core(**params)


if HAS_FASTMCP:
    import asyncio

    app = Server("juris-calculus-v1")

    @app.tool()
    async def juris_evaluate(
        domain: str,
        facts_json: str,
        source_law: str = "CN",
        dry_run: bool = False,
        rules_path: str = "configs/zh_CN/rules.yaml",
    ) -> str:
        """统一推理入口。domain=contract|criminal|admin|ip|family|... facts_json=JSON事实字典 source_law=CN/US dry_run=true仅预检不跑Fixpoint"""
        return json.dumps(_juris_evaluate_core(domain, facts_json, source_law, dry_run, rules_path),
                          ensure_ascii=False, indent=2)

    @app.tool()
    async def juris_evaluate(
        domain: str,
        facts_json: str,
        source_law: str = "CN",
        dry_run: bool = False,
        rules_path: str = "configs/zh_CN/rules.yaml",
    ) -> str:
        """统一推理入口：domain=cn.contract|cn.criminal|cn.admin|... facts_json=JSON事实字典 source_law=CN/US dry_run=True仅预检"""
        return json.dumps(_juris_evaluate_core(domain, facts_json, source_law, dry_run, rules_path),
                          ensure_ascii=False, indent=2)

    def main():
        asyncio.run(stdio_server(app))

else:
    # Fallback: JSON-RPC over stdio
    def main():
        print("juris-calculus MCP Server (fallback mode)", file=sys.stderr)
        print("Install FastMCP: pip install mcp", file=sys.stderr)
        print("Ready for JSON-RPC on stdin...", file=sys.stderr)
        for line in sys.stdin:
            try:
                req = json.loads(line.strip())
                method = req.get("method", "")
                params = req.get("params", {})

                if method == "juris_evaluate":
                    result = _juris_evaluate_sync(**params)
                elif method == "ping":
                    result = {"status": "ok", "version": "1.1.0"}
                else:
                    result = {"error": f"Unknown method: {method}"}

                resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": result}
                print(json.dumps(resp, ensure_ascii=False))
                sys.stdout.flush()
            except Exception as e:
                err_resp = {"jsonrpc": "2.0", "id": req.get("id", 0),
                           "error": {"code": -1, "message": str(e)}}
                print(json.dumps(err_resp, ensure_ascii=False))
                sys.stdout.flush()


if __name__ == "__main__":
    main()

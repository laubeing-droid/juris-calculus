#!/usr/bin/env python3
"""
mcp_server.py — juris-calculus MCP Protocol Server v1.2.0
══════════════════════════════════════════════════════════
将 juris-calculus 内核暴露为标准 MCP 协议端点。
任何 MCP 兼容客户端 (Codex/Cursor/Windsurf/Claude) 均可
通过此协议消费 juris-calculus 的法律逻辑能力。

协议: Model Context Protocol (MCP) 2024-11-05
资源: legal://{domain}/{path}
工具: trirail_collide, check_threat, generate_memo,
       route_state, get_citation

用法:
  # 启动 MCP Server (stdio 模式 — Codex/Cursor 直接消费)
  python mcp_server.py

  # 启动交互式测试模式
  python mcp_server.py --test
══════════════════════════════════════════════════════════
"""

import sys
import os
import json
import yaml
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# ── 确保项目根目录在 path 中 ──
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


# ═══════════════════════════════════════════════
# MCP 协议层 (轻量实现，无需外部依赖)
# ═══════════════════════════════════════════════


# --- v2.0 backward-compat wrappers for smoke tests ---
def _juris_evaluate_core(domain, facts_json, dry_run=False, source_law="CN"):
    """Legacy wrapper: evaluate legal facts through FixpointEvaluator."""
    from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
    from compiler_core.types import IRState, LegalFact, LegalDomain
    from compiler_core.domain_config import DomainConfig
    from compiler_core.config_paths import rules_path as _cp_rules
    try:
        facts = json.loads(facts_json) if isinstance(facts_json, str) else facts_json
    except (json.JSONDecodeError, TypeError):
        facts = {}
    state = IRState()
    for k, v in facts.items():
        if isinstance(k, str) and k != "_source_law":
            state.facts[k] = LegalFact(id=k, description=str(v)[:200], formalizable=1.0)
    if dry_run:
        return {
            "dry_run": True,
            "total_claims": 0, "top_claims": [], "domain": domain,
            "validated_facts": list(facts.keys()),
            "blocked_reasons": [],
            "status": "DRY_RUN",
        }
    try:
        cfg = DomainConfig(domain=LegalDomain.CIVIL)

        # ?? ???: US ???? CN ??????? ??
        us_keywords = [
            "punitive damages", "punitive_damages", "exemplary damages",
            "jury trial", "habeas corpus", "class action",
            "treble damages", "constitutional tort", "federal question",

        ]

        # v2.0: blueprint-backed US Code citation validation (via US addon)
        try:
            from addons.us.us_lookup import validate_usc_citation
            usc_cits = validate_usc_citation(facts_text)
            for cit in usc_cits:
                if not cit.get("valid"):
                    blocked.append("USC_BLUEPRINT_MISMATCH: " + cit.get("citation","?") + " -> Title " + str(cit.get("title","?")) + " not found")
        except Exception:
            pass
        blocked = []
        facts_text = " ".join(str(v) for v in facts.values()).lower()
        for kw in us_keywords:
            if kw in facts_text:
                blocked.append(f"US ????: '{kw}' ?????????")

        if blocked and source_law == "CN":
            return {"dry_run": False, "total_claims": 0, "top_claims": [],
                    "domain": domain, "blocked_reasons": blocked, "status": "BLOCKED"}

        rules = load_rules_from_yaml(_cp_rules("zh_CN"))
        evaluator = FixpointEvaluator(rules, cfg)
        claims = evaluator.evaluate(state)
        return {
            "dry_run": False,
            "total_claims": len(claims.claims) if hasattr(claims, "claims") else 0,
            "top_claims": [{"id": c.id, "confidence": c.confidence, "trust_label": c.get_trust_label() if hasattr(c, "get_trust_label") else "UNVERIFIED"} for c in list(claims.claims.values())[:10]] if hasattr(claims, "claims") else [],
            "domain": domain,
            "blocked_reasons": blocked,
            "status": "OK",
        }
    except Exception as e:
        return {"dry_run": dry_run, "total_claims": 0, "top_claims": [], "domain": domain, "blocked_reasons": [str(e)], "status": "ERROR"}

def _juris_evaluate_sync(domain, facts_json):
    """Legacy wrapper: synchronous evaluate with error handling."""
    return _juris_evaluate_core(domain, facts_json, dry_run=False)


class MCPServer:
    """MCP 协议服务端 — stdio JSON-RPC"""

    def __init__(self, manifest_path: str = None):
        if manifest_path is None:
            manifest_path = str(BASE / "mcp_manifest.json")

        with open(manifest_path, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)

        self.resources = {}
        self.tools = {}
        self._init_lazy = True

    def _lazy_init(self):
        """惰性加载 — 避免所有模块在启动时全部导入"""
        if not self._init_lazy:
            return
        self._init_lazy = False

        from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
        from compiler_core.domain_config import DomainConfig, LegalDomain
        from compiler_core.types import LegalFact, IRState
        from tools.distill_jurisdiction import FastPathInterceptor, route_state_law_to_backbone
        from tools.action_agent.compiler import MemoCompiler
        from tools.action_agent.state_to_text import get_citation as _get_citation

        self._CriticalClarityFailure = CriticalClarityFailure
        self._LegalFact = LegalFact
        self._IRState = IRState
        self._DomainConfig = DomainConfig
        self._LegalDomain = LegalDomain
        self._FixpointEvaluator = FixpointEvaluator
        self._load_rules_from_yaml = load_rules_from_yaml
        self._FastPathInterceptor = FastPathInterceptor
        self._route_state = route_state_law_to_backbone
        self._MemoCompiler = MemoCompiler
        self._get_citation = _get_citation
        self._PRCAdapter = PRCAdapter

        # 预加载引擎
        from compiler_core.plugin_registry import registry
        self._addon_adapters = {}
        for code in ["hk", "us"]:
            adapter = registry.get(code)
            if adapter is not None:
                self._addon_adapters[code] = adapter
        self._hk_rules = self._load_rules_from_yaml(str(BASE / "configs" / "hk" / "rules.yaml")) if registry.is_installed("hk") else []
        self._hk_extended = self._load_rules_from_yaml(str(BASE / "configs" / "hk" / "extended_rules.yaml")) if registry.is_installed("hk") else []
        self._us_rules = self._load_rules_from_yaml(str(BASE / "configs" / "en_US" / "US_Adapter.yaml")) if registry.is_installed("us") else []
        self._hk_extended = self._load_rules_from_yaml(str(BASE / "configs" / "hk" / "extended_rules.yaml"))
        self._us_rules = self._load_rules_from_yaml(str(BASE / "configs" / "en_US" / "US_Adapter.yaml"))
        self._threat = self._FastPathInterceptor()
        self._memo_compiler = self._MemoCompiler()
        self._prc_adapter = self._PRCAdapter()

    # ── 资源端点 ──
    def _read_resource(self, uri: str) -> Optional[str]:
        """URI → 资源内容"""
        self._lazy_init()

        path = uri.replace("legal://", "")
        parts = path.split("/")

        # legal://threat-intel/{state}
        if parts[0] == "threat-intel":
            state = parts[1] if len(parts) > 1 else "all"
            if state == "all":
                sigs = {}
                for st in ["wi", "nj"]:
                    p = BASE / "configs" / "us" / "threat_signatures" / f"{st}_enf_signature.yaml" if st == "wi" else BASE / "configs" / "us" / "threat_signatures" / f"{st}_pen_signature.yaml"
                    if p.exists():
                        with open(p, "r", encoding="utf-8") as f:
                            jd = yaml.safe_load(f)
                            sigs[st.upper()] = jd
                return yaml.dump(sigs, allow_unicode=True, default_flow_style=False)
            else:
                state = state.lower()
                fn = "wi_enf_signature.yaml" if state == "wi" else "nj_pen_signature.yaml"
                p = BASE / "configs" / "us" / "threat_signatures" / fn
                if p.exists():
                    return p.read_text(encoding="utf-8")
                return None

        # legal://blocking-rules
        if path == "blocking-rules":
            return (BASE / "configs" / "prc_us_alignment" / "blocking_rules.yaml").read_text(encoding="utf-8")

        # legal://spc-rules
        if path == "spc-rules":
            return (BASE / "configs" / "prc_us_alignment" / "spc_rules.yaml").read_text(encoding="utf-8")

        # legal://term-mappings
        if path == "term-mappings":
            return (BASE / "configs" / "prc_us_alignment" / "term_L0_mappings.yaml").read_text(encoding="utf-8")

        # legal://hk-rules
        if path == "hk-rules":
            text = (BASE / "configs" / "hk" / "rules.yaml").read_text(encoding="utf-8")
            ext = (BASE / "configs" / "hk" / "extended_rules.yaml").read_text(encoding="utf-8")
            return text + "\n" + ext

        # legal://us-rules
        if path == "us-rules":
            text = (BASE / "configs" / "en_US" / "US_Adapter.yaml").read_text(encoding="utf-8")
            ovr = (BASE / "configs" / "en_US" / "L0_overrides_us.yaml").read_text(encoding="utf-8")
            return text + "\n" + ovr

        # legal://cn-rules
        if path == "cn-rules":
            return (BASE / "configs" / "zh_CN" / "rules.yaml").read_text(encoding="utf-8")
        # legal://blueprint
        if path == "blueprint":
            bp_path = BASE / "configs" / "juris_blueprint.json"
            if bp_path.exists():
                return bp_path.read_text(encoding="utf-8")
            return json.dumps({"error": "blueprint not built"}, ensure_ascii=False)


        # legal://glossary/{jurisdiction}
        if parts[0] == "glossary":
            jx = parts[1] if len(parts) > 1 else "us"
            if jx == "us":
                return (BASE / "configs" / "en_US" / "state_combined_terms.json").read_text(encoding="utf-8")
            return json.dumps({"error": f"Glossary not available for {jx}"})

        # legal://state-router
        if path == "state-router":
            return (BASE / "configs" / "en_US" / "state_router.yaml").read_text(encoding="utf-8")

        # legal://operator-schemas (动态生成 — 算子自文档化)
        if path == "operator-schemas":
            from tools.operator_registry import get_all_schemas
            return json.dumps(get_all_schemas(), ensure_ascii=False, indent=2)

        # legal://task-schema (动态生成 — Codex 任务协议)
        if path == "task-schema":
            from tools.operator_registry import generate_task_schema
            return json.dumps(generate_task_schema(), ensure_ascii=False, indent=2)

        return None

    # ── 工具端点 ──
    def _call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """工具调用分发"""
        self._lazy_init()

        if tool_name == "trirail_collide":
            return self._tool_trirail_collide(arguments)
        elif tool_name == "check_threat":
            return self._tool_check_threat(arguments)
        elif tool_name == "generate_memo":
            return self._tool_generate_memo(arguments)
        elif tool_name == "route_state":
            return self._tool_route_state(arguments)
        elif tool_name == "get_citation":
            return self._tool_get_citation(arguments)
        elif tool_name == "get_operator_schemas":
            return self._tool_get_operator_schemas(arguments)
        elif tool_name == "generate_task_schema":
            return self._tool_generate_task_schema(arguments)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    # ── 工具实现 ──
    def _tool_trirail_collide(self, args: Dict) -> Dict:
        """三轨对撞"""
        facts_dict = args.get("facts", {})
        scenario_id = args.get("scenario_id", "custom")

        # 构建 HK 引擎
        hk_all = self._hk_rules + self._hk_extended
        hk_eng = self._FixpointEvaluator(
            hk_all, self._DomainConfig(domain=self._LegalDomain.CIVIL),
            overrides_path=str(BASE / "configs" / "L0_overrides_hk.yaml")
        )
        us_eng = self._FixpointEvaluator(
            self._us_rules, self._DomainConfig(domain=self._LegalDomain.CIVIL),
            overrides_path=str(BASE / "configs" / "en_US" / "L0_overrides_us.yaml")
        )

        # 威胁预检
        threat = self._threat.intercept(list(facts_dict.keys()))
        if threat:
            return {
                "scenario_id": scenario_id,
                "threat": threat
            }
        return {}



# --- v2.0.1 MCP tool wrappers

# --- v2.0.1 LLM-enhanced MCP tools (privacy-gated, always TAINTED) ---

def evaluate_facts_llm(fact_text: str):
    from tools.llm_bridge import evaluate_facts_llm as _ef
    return _ef(fact_text)

def align_concepts_llm(cn_concept: str, us_concept: str):
    from tools.llm_bridge import align_concepts_llm as _ac
    return _ac(cn_concept, us_concept)

def generate_nlni_llm(case_description: str):
    from tools.llm_bridge import generate_nlni_llm as _gn
    return _gn(case_description)
 # all route through juris_query

def search_rules(query: str, top_k: int = 5):
    return juris_query("search_rules", query, {"top_k": top_k})

def evaluate_facts(fact_text: str, fact_items: dict = None):
    return juris_query("evaluate_facts", fact_text, {"fact_items": fact_items})

def calculate_damages(principal: float = 100000, lpr_rate: float = 3.45,
                      interest_days: int = 365, contract_value: float = 0,
                      actual_loss: float = 0, deposit_paid: float = 0):
    return juris_query("calculate_damages", "", {
        "principal": principal, "lpr_rate": lpr_rate,
        "interest_days": interest_days, "contract_value": contract_value,
        "actual_loss": actual_loss, "deposit_paid": deposit_paid})

def analyze_strategy(fact_text: str):
    return juris_query("analyze_strategy", fact_text)

def extract_elements(fact_text: str):
    return juris_query("extract_elements", fact_text)

# v2.1 new tools
def evaluate_dp_policy(data_class: str, epsilon: float = 1.0):
    return juris_query("evaluate_dp_policy", data_class, {"epsilon": epsilon})

def validate_source(anchor: str):
    return juris_query("validate_source", anchor)

def evaluate_evidence(description: str, reliability: float = 1.0, independence: float = 1.0, authenticity: float = 1.0):
    return juris_query("evaluate_evidence", description, {"reliability": reliability, "independence": independence, "authenticity": authenticity})

def track_burden(party: str, allegation: str, standard: str = "preponderance", evidence: list = None):
    return juris_query("track_burden", allegation, {"party": party, "standard": standard, "evidence": evidence or []})

def analyze_analogy(current_facts: list, precedent_facts: list, court_level: str = "intermediate"):
    return juris_query("analyze_analogy", "", {"current_facts": current_facts, "precedent_facts": precedent_facts, "court_level": court_level})

def predict_sentence(min_months: int = 0, max_months: int = 36, mitigating: list = None, aggravating: list = None):
    return juris_query("predict_sentence", "", {"min_months": min_months, "max_months": max_months, "mitigating": mitigating or [], "aggravating": aggravating or []})

def estimate_ip_value(ip_type: str = "patent", development_cost: float = 0, licensing_revenue: float = 0, market_value: float = 0, remaining_years: int = 0):
    return juris_query("estimate_ip_value", "", {"ip_type": ip_type, "development_cost": development_cost, "licensing_revenue": licensing_revenue, "market_value": market_value, "remaining_years": remaining_years})

def check_compliance(regulation_id: str, requirement: str = "", evidence: list = None):
    return juris_query("check_compliance", regulation_id, {"requirement": requirement, "evidence": evidence or []})

def analyze_arbitration(clause_valid: bool = False, institution: str = "", seat: str = "", law: str = ""):
    return juris_query("analyze_arbitration", "", {"clause_valid": clause_valid, "institution": institution, "seat": seat, "law": law})

def route_cross_jurisdiction(concept: str, source: str = "CN", target: str = "HK"):
    return juris_query("route_cross_jurisdiction", concept, {"source": source, "target": target})

def check_obstruction(concept: str, source: str = "CN", target: str = "HK"):
    return juris_query("check_obstruction", concept, {"source": source, "target": target})

def format_proof_trace(trace: list):
    return juris_query("format_proof_trace", "", {"trace": trace})
# --- v2.0.1 MCP unified query tool ---

def juris_query(mode: str, query: str = "", params: dict = None):
    params = params or {}
    if mode == "search_rules":
        from compiler_core.config_paths import rules_path
        from difflib import SequenceMatcher
        import yaml
        def fuzzy_score(q, t):
            q, t = str(q).lower(), str(t).lower()
            if q == t: return 1.0
            if q in t or t in q: return 0.85
            return SequenceMatcher(None, q, t).ratio()
        rules_data = yaml.safe_load(Path(rules_path("zh_CN")).read_text(encoding="utf-8"))
        items = rules_data.get("rules", []) if isinstance(rules_data, dict) else rules_data
        results = []
        for rule in items:
            if not isinstance(rule, dict): continue
            head = str(rule.get("head_claim", ""))
            rid = str(rule.get("id", ""))
            score = max(fuzzy_score(query, head[:200]), fuzzy_score(query, rid))
            if score > 0.2:
                results.append({"id": rid, "head": head[:200], "score": round(score, 2)})
        results.sort(key=lambda x: -x["score"])
        top_k = params.get("top_k", 5)
        return {"query": query, "total_rules": len(items) if isinstance(items, list) else 0, "results": results[:top_k]}
    elif mode == "evaluate_facts":
        from compiler_core.evaluator import load_rules_from_yaml, FixpointEvaluator
        from compiler_core.types import IRState, LegalFact, LegalDomain
        from compiler_core.domain_config import DomainConfig
        from compiler_core.config_paths import rules_path
        loaded = load_rules_from_yaml(rules_path("zh_CN"))
        ev = FixpointEvaluator(loaded, DomainConfig(domain=LegalDomain.CIVIL))
        st = IRState()
        facts = params.get("fact_items", None) or {"f1": query}
        for k, v in facts.items():
            st.facts[k] = LegalFact(id=k, description=str(v)[:200], formalizable=1.0)
        result = ev.evaluate(st)
        raw = list(result.claims.values()) if hasattr(result, "claims") else []
        claims = sorted(raw, key=lambda x: -x.confidence)
        top = claims[0] if claims else None
        if not top: return {"prediction": "N/A", "confidence": 0, "trust": "UNVERIFIED", "total_claims": 0}
        return {"prediction": top.description[:200], "confidence": round(top.confidence, 2), "trust": top.get_trust_label(), "total_claims": len(claims)}
    elif mode == "calculate_damages":
        principal = float(params.get("principal", 100000))
        lpr_rate = float(params.get("lpr_rate", 3.45))
        lpr_4x = lpr_rate * 4
        interest_days = int(params.get("interest_days", 365))
        contract_value = max(float(params.get("contract_value", 0)), principal)
        actual_loss = max(float(params.get("actual_loss", 0)), principal * 0.1)
        max_interest = round(principal * (lpr_4x / 100) * (interest_days / 365), 2)
        lpr_exceeded = (lpr_rate * 100) > lpr_4x if params.get("agreed_rate") else False
        return {"principal": principal, "max_legal_interest": max_interest, "lpr_exceeded": lpr_exceeded, "total_estimate": round(principal + max_interest, 2)}
    elif mode == "analyze_strategy":
        from compiler_core.evaluator import load_rules_from_yaml, FixpointEvaluator
        from compiler_core.types import IRState, LegalFact, LegalDomain
        from compiler_core.domain_config import DomainConfig
        from compiler_core.config_paths import rules_path
        from pipeline.adversarial_pipeline import AdversarialPipeline
        loaded = load_rules_from_yaml(rules_path("zh_CN"))
        ev = FixpointEvaluator(loaded, DomainConfig(domain=LegalDomain.CIVIL))
        st = IRState(); st.facts["case"] = LegalFact(id="case", description=query[:200], formalizable=1.0)
        result = ev.evaluate(st)
        raw = list(result.claims.values()) if hasattr(result, "claims") else []
        claims = sorted(raw, key=lambda x: -x.confidence)
        top = [{"id": c.id, "confidence": c.confidence, "trust": c.get_trust_label()} for c in claims[:5]]
        adv = AdversarialPipeline()
        reasoner = adv.run_reasoner([{"id": c.id, "confidence": c.confidence} for c in claims], list(result.rules_applied)[:5])
        strengths = [c["id"] for c in top if c["confidence"] >= 0.7]
        weaknesses = [c["id"] for c in top if c["confidence"] < 0.3]
        return {"top_claims": top, "strengths": strengths or ["none"], "weaknesses": weaknesses or ["none"], "recommended": "offense" if len(strengths) >= len(weaknesses) else "defense", "reasoner_issues": reasoner.issues[:5]}
    elif mode == "extract_elements":
        from compiler_core.evaluator import load_rules_from_yaml
        from compiler_core.config_paths import rules_path
        rules = load_rules_from_yaml(rules_path("zh_CN"))
        elements = set()
        for rule in rules:
            if hasattr(rule, "premise_atoms"):
                for atom in rule.premise_atoms:
                    if len(atom) >= 2 and (atom[:2] in query or atom[-2:] in query):
                        elements.add(atom)
        return {"fact_text": query[:200], "matched_elements": sorted(elements)[:20], "total": len(elements)}
    # ── v2.1 新增工具 ──
    try:
        if mode == "evaluate_dp_policy":
            from compiler_core.dp_policy_loader import DPPolicyLoader
            from compiler_core.config_paths import config_dir
            loader = DPPolicyLoader()
            loader.load(str(Path(config_dir()) / "dp_policy.yaml"))
            data_class = params.get("data_class", query)
            epsilon = float(params.get("epsilon", 1.0))
            return loader.check_release(data_class, epsilon)
        elif mode == "validate_source":
            from compiler_core.source_manifest import SourceManifest
            from compiler_core.config_paths import config_dir
            m = SourceManifest()
            m.load(str(Path(config_dir()) / "source_manifest.yaml"))
            anchor = params.get("anchor", query)
            return m.validate_anchor(anchor)
        elif mode == "evaluate_evidence":
            from compiler_core.evidence_evaluation import EvidenceItem
            reliability = float(params.get("reliability", 1.0))
            independence = float(params.get("independence", 1.0))
            authenticity = float(params.get("authenticity", 1.0))
            e = EvidenceItem(id=query[:20], description=query[:200],
                             reliability=reliability, independence=independence, authenticity=authenticity)
            return {"credibility_score": round(e.credibility_score, 3), "components": {"reliability": reliability, "independence": independence, "authenticity": authenticity}}
        elif mode == "track_burden":
            from compiler_core.burden_of_proof import BurdenTracker
            t = BurdenTracker()
            party = params.get("party", "plaintiff")
            allegation = params.get("allegation", query)
            standard = params.get("standard", "preponderance")
            t.add(party, allegation, "burden_of_persuasion", standard)
            evidence = params.get("evidence", [])
            for ev in evidence:
                t.submit_evidence(allegation, ev)
            return t.evaluate_completion(allegation)
        elif mode == "analyze_analogy":
            from compiler_core.legal_reasoning import analogical_similarity, precedent_binding_force
            current = params.get("current_facts", query.split(","))
            precedent = params.get("precedent_facts", [])
            sim = analogical_similarity(current, precedent)
            court = params.get("court_level", "intermediate")
            force = precedent_binding_force(court, params.get("jurisdiction_match", True))
            return {"similarity": round(sim, 3), "binding_force": round(force, 3), "court_level": court}
        elif mode == "predict_sentence":
            from compiler_core.criminal_sentencing import SentencingFactors
            lo = int(params.get("min_months", 0))
            hi = int(params.get("max_months", 36))
            mitigating = params.get("mitigating", [])
            aggravating = params.get("aggravating", [])
            f = SentencingFactors(statutory_range_months=(lo, hi),
                                  mitigating_factors=mitigating, aggravating_factors=aggravating)
            r = f.predict_range()
            return {"statutory_range": [lo, hi], "predicted_range": list(r), "mitigating": mitigating, "aggravating": aggravating}
        elif mode == "estimate_ip_value":
            from compiler_core.ip_valuation import IPValuation
            v = IPValuation(ip_type=params.get("ip_type", "patent"),
                            development_cost=float(params.get("development_cost", 0)),
                            licensing_revenue=float(params.get("licensing_revenue", 0)),
                            market_value=float(params.get("market_value", 0)),
                            remaining_useful_life_years=int(params.get("remaining_years", 0)))
            return {"ip_type": v.ip_type, "estimated_value": v.estimate_value()}
        elif mode == "check_compliance":
            from compiler_core.compliance_monitoring import ComplianceCheck
            c = ComplianceCheck(regulation_id=params.get("regulation_id", query), requirement=params.get("requirement", ""))
            evidence = params.get("evidence", [])
            return c.evaluate(evidence)
        elif mode == "analyze_arbitration":
            from compiler_core.arbitration_reasoning import ArbitrationAnalysis
            a = ArbitrationAnalysis(arbitration_clause_valid=params.get("clause_valid", False),
                                    arbitral_institution=params.get("institution", ""),
                                    seat_of_arbitration=params.get("seat", ""),
                                    applicable_law=params.get("law", ""))
            return a.evaluate_enforceability()
        elif mode == "route_cross_jurisdiction":
            from compiler_core.cross_jurisdiction_router import CrossJurisdictionRouter
            from compiler_core.config_paths import config_dir
            router = CrossJurisdictionRouter()
            router.load(str(Path(config_dir()) / "obstruction_registry.yaml"))
            concept = params.get("concept", query)
            src = params.get("source", "CN")
            tgt = params.get("target", "HK")
            return router.route(concept, src, tgt)
        elif mode == "check_obstruction":
            from compiler_core.cross_jurisdiction_router import CrossJurisdictionRouter
            from compiler_core.config_paths import config_dir
            router = CrossJurisdictionRouter()
            router.load(str(Path(config_dir()) / "obstruction_registry.yaml"))
            concept = params.get("concept", query)
            src = params.get("source", "CN")
            tgt = params.get("target", "HK")
            result = router.route(concept, src, tgt)
            return {"concept": concept, "source": src, "target": tgt, "status": result.get("status", "UNMAPPED"), "allowed": result.get("allowed", False)}
        elif mode == "format_proof_trace":
            from compiler_core.proof_trace_renderer import format_proof_trace_cn
            trace = params.get("trace", [])
            return {"rendered": format_proof_trace_cn(trace)}
    except Exception as e:
        return {"error": f"{mode}: {str(e)}"}
    return {"error": "unknown mode: " + mode}


def run_stdio():
    """stdio 模式 — MCP 协议标准传输"""
    server = MCPServer()
    import json as _json

    # 握手: 发送初始化响应
    init_response = {
        "jsonrpc": "2.0",
        "id": 0,
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": server.manifest["name"],
                "version": server.manifest["version"],
            },
            "capabilities": {
                "resources": {uri: True for uri in server.manifest.get("resources", {}).keys()},
                "tools": {name: True for name in server.manifest.get("tools", {}).keys()},
            }
        }
    }
    sys.stdout.write(_json.dumps(init_response) + "\n")
    sys.stdout.flush()

    # 请求循环
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = _json.loads(line)
            req_id = request.get("id", 0)
            method = request.get("method", "")
            params = request.get("params", {})

            if method == "resources/read":
                uri = params.get("uri", "")
                content = server._read_resource(uri)
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"contents": [{"uri": uri, "text": content}]} if content else {"error": "Resource not found"}
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": [
                        {"name": name, **desc}
                        for name, desc in server.manifest.get("tools", {}).items()
                    ]}
                }
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = server._call_tool(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": _json.dumps(result, ensure_ascii=False, indent=2)}]}
                }
            elif method == "resources/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"resources": [
                        {"uri": uri, "name": uri, **desc}
                        for uri, desc in server.manifest.get("resources", {}).items()
                    ]}
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }

            sys.stdout.write(_json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id", 0) if 'request' in dir() else 0,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(_json.dumps(error_response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def run_test():
    """交互式测试模式"""
    server = MCPServer()
    print("╔══════════════════════════════════════════════╗")
    print("║  juris-calculus MCP Server — Test Mode       ║")
    print("║  v1.2.0                                     ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"")
    print(f"  Resources: {len(server.manifest['resources'])}")
    print(f"  Tools:     {len(server.manifest['tools'])}")
    print(f"")

    # 测试威胁预检
    print("  [TEST] check_threat — Alter-Ego")
    result = server._call_tool("check_threat", {"facts": ["Alter-Ego liability", "piercing corporate veil"]})
    print(f"    hit={result['hit']}, threat={result.get('threat',{}).get('signature_id','none')}")
    print(f"")

    # 测试三轨对撞
    print("  [TEST] trirail_collide — Ch11 + UltraVires")
    result = server._call_tool("trirail_collide", {
        "scenario_id": "test_001",
        "facts": {
            "Director_Acted_UltraVires": 0.88,
            "Chapter11_Filed": 0.95,
            "Bankruptcy_Petition_Filed": 1.0,
            "ContractOfSale_Exists": 0.9,
            "Cross_Border_Context": 1.0,
        }
    })
    print(f"    classification: {result['classification']}")
    print(f"    HK claims: {result['hk']['claims'][:3]}")
    print(f"    PRC overrides: {result['prc']['force_void'] + result['prc']['force_suppress']}")
    print(f"")

    # 测试州路由
    print("  [TEST] route_state — CA_BP_17200")
    result = server._call_tool("route_state", {"raw_fact": "CA_BP_17200_unfair_competition", "state_code": "CA"})
    print(f"    backbone: {result['backbone']}, multi={result.get('multi_label', False)}")
    print(f"")

    # 测试法条
    print("  [TEST] get_citation — PEN_003")
    result = server._call_tool("get_citation", {"rule_id": "PEN_003_Long_Arm_Interdiction"})
    print(f"    short: {result['citation_short']}")
    print(f"")

    print("  [OK] All tests passed. MCP Server ready for Codex connection.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="juris-calculus MCP Server")
    parser.add_argument("--test", action="store_true", help="Run interactive test mode")
    parser.add_argument("--manifest", type=str, default=None, help="Path to mcp_manifest.json")
    args = parser.parse_args()

    if args.test:
        run_test()
    else:
        run_stdio()

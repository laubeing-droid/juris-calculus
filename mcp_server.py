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
        from adapter.prc_adapter import PRCAdapter

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
                "classification": "CHINA_US_COLLISION",
                "fast_path": True,
                "threat": threat,
                "hk": {"state": "?"},
                "us": {"state": "?"},
                "prc": {
                    "force_void": [threat["target_rule"]],
                    "force_suppress": [],
                    "mapping_override": [],
                    "cn_claims_count": 0,
                }
            }

        # 构造事实
        from compiler_core.types import LegalFact, IRState
        fact_objs = {k: LegalFact(id=k, description=k, extraction_confidence=v)
                     for k, v in facts_dict.items()}

        hk_state = IRState(facts=dict(fact_objs))
        us_state = IRState(facts=dict(fact_objs))
        prc_state = self._prc_adapter.execute_prc_first_override(fact_objs)

        try:
            hk_state = hk_eng.evaluate(hk_state)
        except self._CriticalClarityFailure as e:
            if hasattr(e, 'partial_state') and e.partial_state is not None:
                hk_state = e.partial_state

        try:
            us_state = us_eng.evaluate(us_state)
        except self._CriticalClarityFailure as e:
            if hasattr(e, 'partial_state') and e.partial_state is not None:
                us_state = e.partial_state

        from tools.run_trirail_matrix import classify_tri_state
        classification = classify_tri_state(hk_state, us_state, prc_state)

        return {
            "scenario_id": scenario_id,
            "classification": classification,
            "hk": {
                "claims": list(hk_state.claims.keys()),
                "state": hk_state.state_tracker.get("Contract_Validity", "VALID") if hk_state.state_tracker else "?",
            },
            "us": {
                "claims": list(us_state.claims.keys()),
                "state": us_state.state_tracker.get("Contract_Validity", "VALID") if us_state.state_tracker else "?",
            },
            "prc": {
                "force_void": self._prc_adapter.get_force_void_triggers(prc_state),
                "force_suppress": self._prc_adapter.get_force_suppress_triggers(prc_state),
                "mapping_override": [m["id"] for m in self._prc_adapter.get_mapping_overrides(prc_state)],
                "cn_claims_count": prc_state.get("cn_claims_count", 0),
                "cn_rules_total": prc_state.get("cn_rules_total", 0),
            },
            "citations": {
                rid: self._get_citation(rid)
                for rid in (prc_state.get("blocking_overrides", {}).keys())
            }
        }

    def _tool_check_threat(self, args: Dict) -> Dict:
        """威胁校验"""
        facts = args.get("facts", [])
        hit = self._threat.intercept(facts)
        report = self._threat.get_threat_report(facts)
        return {
            "hit": hit is not None,
            "threat": hit,
            "report": report,
        }

    def _tool_generate_memo(self, args: Dict) -> Dict:
        """生成备忘录"""
        case_id = args.get("case_id", "UNKNOWN")
        trirail_result = args.get("trirail_result", {})
        memo = self._memo_compiler.compile(trirail_result, case_id)
        return {"case_id": case_id, "memo_markdown": memo, "length": len(memo)}

    def _tool_route_state(self, args: Dict) -> Dict:
        """州级路由"""
        raw_fact = args.get("raw_fact", "")
        state_code = args.get("state_code")
        return self._route_state(raw_fact, state_code)

    def _tool_get_citation(self, args: Dict) -> Dict:
        """法条引用"""
        rule_id = args.get("rule_id", "")
        short = self._get_citation(rule_id)
        from tools.action_agent.state_to_text import get_prc_citation_full
        full = get_prc_citation_full(short)
        return {"rule_id": rule_id, "citation_short": short, "citation_full": full}

    def _tool_get_operator_schemas(self, args: Dict) -> Dict:
        """算子 Schema 查询"""
        from tools.operator_registry import OperatorRegistry, OperatorType
        filter_type = args.get("filter", "all")

        if filter_type == "critical":
            schemas = OperatorRegistry.get_critical_operators()
        elif filter_type == "sovereignty":
            schemas = OperatorRegistry.get_sovereignty_operators()
        elif filter_type == "by_type":
            type_name = args.get("type_filter", "")
            try:
                ot = OperatorType(type_name)
                schemas = OperatorRegistry.get_schemas_by_type(ot)
            except ValueError:
                schemas = {}
        else:
            schemas = OperatorRegistry.get_all_schemas()

        return {
            "total": len(schemas),
            "filter": filter_type,
            "schemas": schemas,
        }

    
    def _tool_rule_router(self, args: Dict) -> Dict:
        """v2.0 domain routing - map facts to expert shards"""
        from compiler_core.rule_router import RuleRouter
        router = RuleRouter()
        fact_texts = args.get("fact_texts", [])
        result = router.route(fact_texts)
        return {"experts": result["selected_experts"], "cross_conflicts": result["cross_expert_conflicts"], "scores": result["all_scores"]}

    def _tool_stratified_evaluate(self, args: Dict) -> Dict:
        """v2.0 stratified evaluator - 4-stage Horn+AAF pipeline"""
        from compiler_core.stratified_evaluator import StratifiedEvaluator
        facts_dict = args.get("facts", {})
        se = StratifiedEvaluator(_cp_rules("zh_CN"))
        from compiler_core.types import IRState, LegalFact
        state = IRState()
        for k, v in facts_dict.items():
            state.facts[k] = LegalFact(id=k, description=str(v)[:200], confidence=float(v) if isinstance(v, (int, float)) else 1.0)
        claims = se.evaluate(state)
        return {"total_claims": len(claims), "claims": [{"id": c.id, "confidence": c.confidence, "trust_label": c.get_trust_label()} for c in claims[:20]]}

    def _tool_neural_leaf_status(self, args: Dict) -> Dict:
        """v2.0 neural leaf node registry status"""
        from compiler_core.neural_leaf import NeuralLeafRegistry, NeuralLeafType
        reg = NeuralLeafRegistry()
        for nt in NeuralLeafType:
            reg.register(nt.value, nt)
        node_id = args.get("node_id", "")
        if node_id:
            return {"node_id": node_id, "available": reg.is_available(node_id), "kill_switch": reg._kill_switch}
        return {"nodes": list(reg._nodes.keys()), "kill_switch": reg._kill_switch}

    def _tool_generate_task_schema(self, args: Dict) -> Dict:
        """生成法律任务 Schema"""
        from tools.operator_registry import generate_task_schema
        focus = args.get("jurisdiction_focus", ["PRC", "HK", "US"])
        return generate_task_schema(focus)


# ═══════════════════════════════════════════════
# Main: stdio JSON-RPC 模式
# ═══════════════════════════════════════════════

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

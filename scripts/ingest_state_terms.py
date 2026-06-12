#!/usr/bin/env python3
# Parse US state statute directories (same format as _usc/uscode) and
# auto-extract terms + L0 primitives + MoE domains into blueprint.
#
# Usage:
#   python scripts/ingest_state_terms.py D:\ca_statutes --state CA
#   python scripts/ingest_state_terms.py --list
import json, os, sys, re, argparse
from collections import defaultdict
from pathlib import Path

BP = Path(__file__).resolve().parent.parent / "configs" / "juris_blueprint.json"

# L0 primitive detection patterns (keyword -> primitive)
L0_PATTERNS = [
    (re.compile(r"shall have (the )?power|authority to|jurisdiction", re.I), "Power"),
    (re.compile(r"is void|voidable|unenforceable|invalid|defect", re.I), "Defect"),
    (re.compile(r"shall file|shall serve|shall notify|shall give notice", re.I), "Act"),
    (re.compile(r"is formed|is established|shall be deemed|status of", re.I), "Status"),
    (re.compile(r"person|individual|entity|party|trustee|debtor", re.I), "Agent"),
]

TITLE_TO_MOE = {
    "civil code": "contract", "civil": "contract", "commercial": "contract",
    "penal": "criminal", "criminal": "criminal",
    "evidence": "procedure", "procedure": "procedure",
    "court": "procedure", "judicial": "procedure",
    "family": "marriage_family", "domestic": "marriage_family",
    "corporations": "corporate", "business": "corporate",
    "labor": "labor", "employment": "labor",
    "tax": "financial", "revenue": "financial",
    "property": "property", "land": "property",
    "tort": "tort", "remedies": "tort",
    "administrative": "admin", "government": "admin",
    "environmental": "environmental", "water": "environmental",
    "intellectual property": "ip", "copyright": "ip", "trademark": "ip",
}

MOE_CN_NAMES = {
    "contract": "合同", "criminal": "刑事", "procedure": "程序",
    "marriage_family": "婚姻家庭", "corporate": "公司", "labor": "劳动",
    "financial": "金融", "property": "房地产", "tort": "侵权",
    "admin": "行政", "environmental": "环境资源", "ip": "知产",
}


def detect_l0(text: str) -> str:
    scores = {}
    for pat, prim in L0_PATTERNS:
        n = len(pat.findall(text[:2000]))
        if n:
            scores[prim] = scores.get(prim, 0) + n
    return max(scores, key=scores.get) if scores else "?"


def detect_moe(title_name: str) -> str:
    tn = title_name.lower().replace("-", " ")
    for kw, domain in TITLE_TO_MOE.items():
        if kw in tn:
            return MOE_CN_NAMES.get(domain, domain)
    return "程序"


def parse_state_dir(root_dir: str, state_code: str) -> list:
    entries = []
    root = Path(root_dir)
    if not root.exists():
        print(f"ERROR: {root_dir} does not exist")
        return entries
    for td in sorted(root.iterdir()):
        if not td.is_dir() or not td.name.startswith("title-"):
            continue
        m = re.match(r"title-\d+-(.+)", td.name)
        title_name = m.group(1).replace("-", " ").title() if m else td.name
        moe = detect_moe(title_name)
        for item in sorted(td.iterdir()):
            if item.name.startswith("chapter-") and item.is_file() and item.suffix == ".md":
                cm = re.match(r"chapter-(\d+[a-z]?)-(.+)\.md$", item.name)
                if cm:
                    try:
                        with open(item, "r", encoding="utf-8") as f:
                            text = f.read(3000)
                        l0 = detect_l0(text)
                        sec = re.search(r"^#+\s*(.+)", text, re.M)
                        stitle = sec.group(1).strip() if sec else cm.group(2)
                        entries.append({"term": stitle, "state_code": state_code,
                                        "l0_primitive": l0, "moe_domain": moe,
                                        "us_domains": [title_name],
                                        "citation": f"{state_code} Stat."})
                    except Exception:
                        pass
            elif item.name.startswith("chapter-") and item.is_dir():
                for sf in sorted(item.glob("*.md"))[:3]:
                    try:
                        with open(sf, "r", encoding="utf-8") as f:
                            text = f.read(3000)
                        l0 = detect_l0(text)
                        entries.append({"term": sf.stem.replace("-", " ").title(),
                                        "state_code": state_code,
                                        "l0_primitive": l0, "moe_domain": moe,
                                        "us_domains": [title_name],
                                        "citation": f"{state_code} Stat."})
                    except Exception:
                        pass
    return entries


def ingest(entries):
    bp = json.loads(BP.read_text(encoding="utf-8"))
    st = bp["domain_assets"]["en_US_state_terms"]
    by_state = st.get("by_state", {})
    by_ms = st.get("by_moe_and_state", {})
    for e in entries:
        sc = e.get("state_code", "XX")
        by_state.setdefault(sc, []).append(e)
        key = f"{e.get('moe_domain','?')}_{sc}"
        by_ms.setdefault(key, []).append({"term": e["term"], "l0": e["l0_primitive"], "state": sc})
    st["by_state"] = by_state
    st["by_moe_and_state"] = by_ms
    st["total_terms"] = sum(len(v) for v in by_state.values())
    BP.write_text(json.dumps(bp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Ingested {len(entries)} terms across {len(by_state)} states")
    for sc in sorted(by_state.keys()):
        print(f"  {sc}: {len(by_state[sc])} terms")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("dirpath", nargs="?")
    p.add_argument("--state", required=False)
    p.add_argument("--list", action="store_true")
    args = p.parse_args()
    if args.list:
        bp = json.loads(BP.read_text(encoding="utf-8"))
        st = bp["domain_assets"]["en_US_state_terms"]
        by_state = st.get("by_state", {})
        print(f"Structured terms: {st['total_terms']} across {len(by_state)} states")
        for s in sorted(by_state.keys()):
            print(f"  {s}: {len(by_state[s])} terms")
    elif args.dirpath and args.state:
        entries = parse_state_dir(args.dirpath, args.state)
        if entries:
            ingest(entries)
        else:
            print(f"No terms from {args.dirpath}")
    else:
        p.print_help()

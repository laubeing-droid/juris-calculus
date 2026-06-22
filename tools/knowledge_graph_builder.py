"""Knowledge graph builder — extract triples from rules."""
import yaml, json


def extract_triples(rules):
    triples = []
    for r in rules:
        rid = r.get('id', '')
        concepts = r.get('concepts', [])
        premises = r.get('premise_atoms', [])
        claim = r.get('head_claim', '')[:60]
        # concept -> rule -> claim
        for c in concepts:
            if isinstance(c, str) and len(c) >= 2:
                triples.append({"subject": c, "relation": "used_in", "object": rid})
        # premise -> rule -> conclusion
        for p in premises:
            if isinstance(p, str) and len(p) >= 2:
                triples.append({"subject": p, "relation": "triggers", "object": rid})
        # rule -> has_claim
        triples.append({"subject": rid, "relation": "has_claim", "object": claim})
        # exception chains
        for exc in r.get('exception_chain', []):
            if exc:
                triples.append({"subject": rid, "relation": "has_exception", "object": str(exc)})
    return triples


with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

triples = extract_triples(rules)
output = {"entity_count": len(set(t["subject"] for t in triples) | set(t["object"] for t in triples)),
          "triple_count": len(triples), "triples": triples[:100]}  # sample

print(f"Triples extracted: {len(triples)}")
print(f"Unique entities: {output['entity_count']}")
print(f"\nSample triples:")
for t in triples[:10]:
    print(f"  {t['subject']} --[{t['relation']}]--> {t['object'][:40]}")

with open('tools/knowledge_graph_sample.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nSample saved to tools/knowledge_graph_sample.json")

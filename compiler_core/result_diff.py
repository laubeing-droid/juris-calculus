"""Result diff — compare two evaluation results."""


def diff(result_a: dict, result_b: dict) -> dict:
    """Diff two evaluation results.

    Args: result_a/result_b with 'claims' dict {id: confidence}
    Returns: {added: [...], removed: [...], changed: [{id, from, to}]}
    """
    claims_a = result_a.get("claims", {})
    claims_b = result_b.get("claims", {})
    ids_a = set(claims_a.keys())
    ids_b = set(claims_b.keys())

    added = sorted(ids_b - ids_a)
    removed = sorted(ids_a - ids_b)
    changed = []
    for cid in sorted(ids_a & ids_b):
        if abs(claims_a[cid] - claims_b[cid]) > 0.01:
            changed.append({"id": cid, "from": round(claims_a[cid], 3), "to": round(claims_b[cid], 3)})

    return {"added": added, "removed": removed, "changed": changed,
            "summary": f"+{len(added)} -{len(removed)} ~{len(changed)}"}

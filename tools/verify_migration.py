#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迁移验证脚本 —— 检查所有 L3 规则 premise_atoms 中是否存在未迁移的旧原子。"""
import sys
from pathlib import Path
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True

EXCLUDE_DIRS = {".git", "backup", "venv", "__pycache__"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="configs")
    parser.add_argument("--old", default="Contract_Existence")
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    issues = 0
    total = 0

    for path in sorted(root.rglob("*.yaml")):
        if any(d in path.parts for d in EXCLUDE_DIRS):
            continue
        total += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = yaml.load(f)
        except:
            continue
        rules = doc.get("rules", []) if isinstance(doc, dict) else []
        for r in rules:
            atoms = r.get("premise_atoms", [])
            if args.old in atoms:
                print(f"  ❌ {path.relative_to(root)} → {r.get('id', '?')}")
                issues += 1

    print(f"\n={'='*60}")
    print(f"检查: {total} 文件  残留: {issues}")
    print("✅ 全部迁移完毕" if issues == 0 else "❌ 存在未迁移规则")
    print(f"={'='*60}")


if __name__ == "__main__":
    import argparse
    main()

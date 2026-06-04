#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Juris-Calculus L3 规则批量迁移脚本 v1.0
适配 juris-calculus 的 premise_atoms [列表] 格式。

功能：将指定原子名在 premise_atoms 中批量替换为新原子名。
特性：
1. 精确匹配列表元素，保留所有注释、缩进、格式不变（ruamel.yaml）
2. 自动备份 (.bak)
3. 试运行模式 (--dry-run)：只统计不修改
4. 生成详细迁移报告
5. 可配置保留名单 (--keep)：指定某些 rule ID 不迁移
"""
import os, re, sys, argparse
from pathlib import Path
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

EXCLUDE_DIRS = {".git", "backup", "venv", "__pycache__"}


def migrate_premise_atoms(doc, old_atom: str, new_atom: str, keep_ids: set) -> tuple:
    """递归遍历 YAML, 仅修改 rules 列表中每条规则的 premise_atoms 字段。"""
    changes = 0
    if not isinstance(doc, dict):
        return doc, 0
    rules = doc.get("rules", [])
    if not isinstance(rules, list):
        return doc, 0
    for rule in rules:
        rid = rule.get("id", "")
        if rid in keep_ids:
            continue
        atoms = rule.get("premise_atoms")
        if not isinstance(atoms, list):
            continue
        new_atoms = []
        modified = False
        for a in atoms:
            if a == old_atom:
                new_atoms.append(new_atom)
                changes += 1
                modified = True
            else:
                new_atoms.append(a)
        if modified:
            rule["premise_atoms"] = new_atoms
    return doc, changes


def process_file(path: Path, old: str, new: str, keep: set, dry: bool) -> tuple:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.load(f)
        if doc is None:
            return 0, False
        modified_doc, count = migrate_premise_atoms(doc, old, new, keep)
        if count == 0:
            return 0, False
        if not dry:
            bak = path.with_suffix(path.suffix + ".bak")
            if not bak.exists():
                os.rename(path, bak)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(modified_doc, f)
        return count, True
    except Exception as e:
        print(f"  ❌ {path}: {e}")
        return 0, False


def main():
    parser = argparse.ArgumentParser(description="juris-calculus L3 规则批量迁移")
    parser.add_argument("--dir", default="configs", help="根目录 (default: configs)")
    parser.add_argument("--old", default="Contract_Existence", help="旧原子名")
    parser.add_argument("--new", default="Contract_Validity", help="新原子名")
    parser.add_argument("--keep", nargs="*", default=[], help="跳过的 rule ID 列表")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不写文件")
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"目录不存在: {root}")
        sys.exit(1)

    keep = set(args.keep)
    total_files = 0
    modified_files = 0
    total_changes = 0

    print(f"迁移: {args.old} → {args.new}")
    print(f"目录: {root}")
    print(f"保留: {keep if keep else '(无)'}")
    print(f"模式: {'试运行(不改文件)' if args.dry_run else '正式迁移'}")
    print()

    for path in sorted(root.rglob("*.yaml")):
        if any(d in path.parts for d in EXCLUDE_DIRS):
            continue
        total_files += 1
        rel = path.relative_to(root)
        cnt, mod = process_file(path, args.old, args.new, keep, args.dry_run)
        if mod:
            modified_files += 1
            total_changes += cnt
            print(f"  ✅ {rel}  ({cnt} 处)")
        else:
            print(f"  ·  {rel}  (无变更)")

    print()
    print("=" * 60)
    print(f"扫描: {total_files}  修改: {modified_files}  替换: {total_changes}")
    if args.dry_run:
        print("试运行完成 —— 未修改任何文件。确认后去掉 --dry-run 执行。")
    else:
        print("迁移完成。备份文件为 .bak 后缀。")
    print("=" * 60)


if __name__ == "__main__":
    main()

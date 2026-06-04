#!/usr/bin/env python3
"""
tools/action_agent/cli.py — Action Agent CLI
══════════════════════════════════════════════════════════════
用法:
  # 批量生成全部12场景备忘录
  python -m tools.action_agent.cli --all

  # 生成单场景备忘录
  python -m tools.action_agent.cli --case TRI_008

  # 指定输出目录
  python -m tools.action_agent.cli --all --output ./my_memos/

  # 从 JSON 文件读取自定义对撞结果
  python -m tools.action_agent.cli --input custom_results.json --all

  # 静默模式 (仅输出文件路径)
  python -m tools.action_agent.cli --all --quiet
══════════════════════════════════════════════════════════════
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(
        prog="juris-calculus memo",
        description="TriRail Action Agent — 生成合伙人可签字的跨境合规备忘录",
    )
    parser.add_argument("--case", "-c", type=str, default=None,
                        help="单场景ID (e.g. TRI_008_VIE_Structure_Review)")
    parser.add_argument("--all", "-a", action="store_true",
                        help="批量生成全部场景备忘录")
    parser.add_argument("--input", "-i", type=str, default=None,
                        help="自定义三轨对撞结果 JSON 路径 (默认使用 trirail_matrix_report.json)")
    parser.add_argument("--output", "-o", type=str, default="reports/memos",
                        help="输出目录 (默认 reports/memos/)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="静默模式")
    parser.add_argument("--list", "-l", action="store_true",
                        help="列出所有可用场景ID")

    args = parser.parse_args()

    # ── 解析输入路径 ──
    base = Path(__file__).resolve().parents[2]  # juris-calculus root
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = base / "configs" / "prc_us_alignment" / "trirail_matrix_report.json"

    if not input_path.exists():
        print(f"[ERROR] 对撞结果文件不存在: {input_path}")
        print(f"  请先运行: python tools/run_trirail_matrix.py")
        sys.exit(1)

    # ── 加载结果 ──
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "TRI_" in list(raw.keys())[0]:
        results = raw  # 直接是 {scenario_id: {...}} 格式
    elif isinstance(raw, dict) and "scenario_id" in raw:
        results = {raw["scenario_id"]: raw}  # 单个结果
    else:
        print(f"[ERROR] 无法解析对撞结果格式。期望 Dict[scenario_id, {...}]")
        sys.exit(1)

    # ── 列出场景 ──
    if args.list:
        print(f"可用场景 ({len(results)}):")
        for sid, r in results.items():
            cls = r.get("classification", "?")
            print(f"  {sid:50s} [{cls}]")
        return

    # ── 确定场景子集 ──
    if args.case:
        if args.case not in results:
            print(f"[ERROR] 场景 '{args.case}' 不存在。可用: {list(results.keys())}")
            sys.exit(1)
        selected = {args.case: results[args.case]}
    elif args.all:
        selected = results
    else:
        parser.print_help()
        print(f"\n提示: 使用 --all 批量生成全部 {len(results)} 场景备忘录")
        sys.exit(0)

    # ── 导入编译器 ──
    sys.path.insert(0, str(base))
    from tools.action_agent.compiler import MemoCompiler

    compiler = MemoCompiler()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 编译 ──
    memos = compiler.compile_all(selected, output_dir=str(output_dir))

    # ── 输出 ──
    if not args.quiet:
        print(f"╔══════════════════════════════════════════════╗")
        print(f"║  Juris-Calculus Action Agent v1.2.0         ║")
        print(f"║  三法域对撞 → 合伙人签字备忘录                ║")
        print(f"╚══════════════════════════════════════════════╝")
        print(f"")
        print(f"  输入: {input_path}")
        print(f"  输出: {output_dir}/")
        print(f"  场景: {len(selected)}")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"")

        for sid, _ in selected.items():
            path = output_dir / f"{sid}_memo.md"
            size = path.stat().st_size if path.exists() else 0
            cls = selected[sid].get("classification", "?")
            tag = {"CHINA_US_COLLISION": "[RED]  ", "HK_CN_ASYMMETRY": "[YEL]  ",
                   "TRI_RESONANCE": "[GRN]  ", "COMPLEX_PARALLAX": "[YEL]  "}.get(cls, "[???]  ")
            print(f"  {tag}{sid}: {size:>5} bytes")

        print(f"")
        print(f"  [OK] {len(selected)} 份备忘录已就绪，可递交合伙人审阅。")

    return 0


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import ast, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
def audit_test_quality(test_dir="tests"):
    findings = []
    test_files = list(Path(test_dir).rglob("test_*.py"))
    for tf in test_files:
        try:
            for node in ast.walk(ast.parse(tf.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant) and node.test.value is False:
                    findings.append({"file":str(tf),"line":node.lineno,"severity":"WARN"})
        except SyntaxError:
            findings.append({"file":str(tf),"issue":"syntax error","severity":"ERROR"})
    return {"status":"PASS" if not any(f["severity"]=="ERROR" for f in findings) else "FAIL","files_checked":len(test_files),"findings":findings}
def main(argv=None):
    r=audit_test_quality()
    print(f"status={r['status']} files={r['files_checked']} findings={len(r['findings'])}")
    return 0 if r["status"]=="PASS" else 1
if __name__=="__main__": sys.exit(main())

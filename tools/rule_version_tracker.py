"""Track rule versions via git blame."""
import subprocess, os
rules_path = 'configs/zh_CN/rules.yaml'
if os.path.exists(rules_path):
    result = subprocess.run(['git', 'log', '--oneline', '-10', rules_path],
                          capture_output=True, text=True, timeout=10)
    print("=== Rule Version History ===")
    print(result.stdout)

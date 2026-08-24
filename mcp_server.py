#!/usr/bin/env python3
"""Installed V4 MCP launcher backed by the sole JCClient facade."""

from compiler_core.client import runtime_client
from compiler_core.mcp import MCPServerV4, run_stdio


def main() -> int:
    try:
        client = runtime_client()
    except Exception:
        return 1
    run_stdio(MCPServerV4(client))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

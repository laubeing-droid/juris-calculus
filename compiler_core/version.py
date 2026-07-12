"""juris-calculus包、CLI和运行时共享的唯一版本源。"""

__version__ = "3.0.2"

# MCP 适配器从包版本模块读取身份和协议版本，避免 manifest、CLI 与审计包各自漂移。
SERVER_NAME = "juris-calculus"
MCP_PROTOCOL_VERSION = "2024-11-05"

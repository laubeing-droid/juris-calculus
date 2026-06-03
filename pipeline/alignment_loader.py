#!/usr/bin/env python3
"""
远程对齐资产自动加载器 v1.0
TTL缓存 + 网络降级 + 支持多法域插槽
"""
import os, time, hashlib
from pathlib import Path
from typing import Dict, Optional
import yaml

CACHE_DIR = Path(os.environ.get("JURIS_CACHE", str(Path.home() / ".cache" / "juris-calculus")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ═══ 全球法域对齐源注册表 ═══
# 开源社区只需在此添加新条目
ALIGNMENT_SOURCES = {
    "prc_us": {
        "url": "https://raw.githubusercontent.com/laubeing-droid/PRC-US-Legal-Semantic-Alignment-Framework/main/ontology_map.yaml",
        "ttl": 86400,          # 24小时
        "description": "中美法律语义对齐框架",
    },
    "prc_eu": {
        "url": "",             # 法国/德国开发者填自己的URL
        "ttl": 86400,
        "description": "PRC-EU alignment (community slot)",
    },
}


class RemoteAlignmentLoader:
    """自动拉取 + 本地缓存 + 优雅降级"""

    def __init__(self, source_name: str = "prc_us"):
        if source_name not in ALIGNMENT_SOURCES:
            raise ValueError(f"Unknown source: {source_name}. Available: {list(ALIGNMENT_SOURCES.keys())}")
        self.source = ALIGNMENT_SOURCES[source_name]
        self.url = self.source["url"]
        self.ttl = self.source.get("ttl", 86400)
        # 缓存文件基于URL哈希，支持多源
        self.cache_file = CACHE_DIR / f"alignment_{source_name}.yaml"

    def _is_cached(self) -> bool:
        if not self.cache_file.exists():
            return False
        age = time.time() - self.cache_file.stat().st_mtime
        return age < self.ttl

    def _fetch_remote(self) -> Optional[dict]:
        try:
            import requests
            resp = requests.get(self.url, timeout=10, headers={"User-Agent": "juris-calculus/1.0"})
            if resp.status_code == 200:
                data = yaml.safe_load(resp.text)
                self.cache_file.write_text(resp.text, encoding="utf-8")
                return data
        except Exception:
            pass
        return None

    def _load_cache(self) -> Optional[dict]:
        if self.cache_file.exists():
            return yaml.safe_load(self.cache_file.read_text(encoding="utf-8"))
        return None

    def get_latest(self) -> dict:
        """获取最新对齐数据。优先级：缓存未过期 > 远程拉取 > 过期缓存 > 报错"""
        if self._is_cached():
            return self._load_cache()

        # 尝试远程拉取
        if self.url:
            remote = self._fetch_remote()
            if remote:
                return remote

        # 降级：用过期缓存
        cached = self._load_cache()
        if cached:
            return cached

        raise RuntimeError(
            f"Cannot load alignment data for '{self.source['description']}'. "
            f"No network and no local cache at {self.cache_file}"
        )


# 全局便捷方法
def load_prc_us_alignment() -> dict:
    loader = RemoteAlignmentLoader("prc_us")
    return loader.get_latest()

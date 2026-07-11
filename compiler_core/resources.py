"""源码树和已安装wheel共用的只读资源定位。"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def configs_root() -> Path:
    """返回已发布configs包的文件系统根目录。"""

    return Path(str(files("configs")))


def schemas_root() -> Path:
    """返回已发布schemas包的文件系统根目录。"""

    return Path(str(files("schemas")))


def neutral_profile_path() -> Path:
    """返回公开中性表达profile；个人profile不得进入该包。"""

    return configs_root() / "render_profiles" / "neutral.yaml"

"""GUI 配置持久化。

所有界面参数写入 ``config/gui_settings.json``，与上游内核的
``upstream/Volume/settings.json`` 相互独立：

    - GUI 配置保存界面的完整状态（含反爬虫增强等 GUI 专有参数）；
    - 每次开始任务时，由引擎把其中需要传递给内核的字段展开写入
      ``Volume/settings.json``，内核逻辑保持原样。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .field_spec import FIELDS, default_config
from .paths import CONFIG_DIR, CONFIG_FILE

__all__ = ["ConfigStore", "config_field_keys"]

#: 需要在界面上呈现的键集合（用于过滤历史遗留键）
config_field_keys: frozenset[str] = frozenset(f.key for f in FIELDS)


class ConfigStore:
    """负责 GUI 配置文件的读写与容错。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else CONFIG_FILE
        self._data: dict[str, Any] = default_config()

    # ------------------------------------------------------------------ #
    # 读取 / 保存
    # ------------------------------------------------------------------ #
    def load(self) -> dict[str, Any]:
        """读取配置；文件不存在或损坏时回退为默认值。"""
        defaults = default_config()
        if not self.path.is_file():
            self._data = defaults
            return dict(self._data)

        try:
            with self.path.open("r", encoding="utf-8") as fp:
                raw = json.load(fp)
            if not isinstance(raw, dict):
                raise ValueError("配置文件根节点必须是对象")
        except Exception:
            # 备份损坏文件后使用默认配置
            try:
                broken = self.path.with_suffix(
                    f".broken-{datetime.now():%Y%m%d%H%M%S}.json"
                )
                shutil.copy2(self.path, broken)
            except Exception:
                pass
            self._data = defaults
            return dict(self._data)

        merged = defaults
        for key, value in raw.items():
            if key in merged:
                merged[key] = _coerce(value, merged[key])
        self._data = merged
        return dict(self._data)

    def save(self, data: dict[str, Any]) -> Path:
        """保存配置，返回写入路径。"""
        payload = {k: data.get(k, v) for k, v in default_config().items()}
        self._data = payload
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=4, ensure_ascii=False)
        tmp.replace(self.path)
        return self.path

    def reset(self) -> dict[str, Any]:
        """恢复默认配置（不落盘，由调用方决定何时保存）。"""
        self._data = default_config()
        return dict(self._data)

    # ------------------------------------------------------------------ #
    def backup(self) -> Path | None:
        """在覆盖前生成一次备份。"""
        if not self.path.is_file():
            return None
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        target = self.path.with_name(
            f"{self.path.stem}.backup-{datetime.now():%Y%m%d%H%M%S}.json"
        )
        shutil.copy2(self.path, target)
        return target

    @property
    def data(self) -> dict[str, Any]:
        return dict(self._data)


def _coerce(value: Any, like: Any) -> Any:
    """尽量把读到的值转换为与默认值一致的类型，避免手工编辑后类型错乱。"""
    if isinstance(like, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "是")
        return bool(value)
    if isinstance(like, int) and not isinstance(like, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return like
    if isinstance(like, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return like
    if isinstance(like, list):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            # 允许手工写成 “a, b” 或 “a b” 两种形式
            normalized = value.replace(",", " ").replace("，", " ")
            return [v.strip() for v in normalized.split() if v.strip()]
        return like
    if isinstance(like, str):
        if value is None:
            return like
        return value if isinstance(value, str) else str(value)
    return value

"""daily 运行配置。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "defaults.yaml"


class Settings:
    """加载默认配置并叠加用户配置。"""

    def __init__(self, config_path: str | None = None):
        self.config_path = Path(config_path).expanduser().resolve() if config_path else None
        self._config = self._load_yaml(DEFAULT_CONFIG_PATH)
        if self.config_path:
            if not self.config_path.exists():
                raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
            user_config = self._load_yaml(self.config_path)
            user_weights = user_config.get("weights", {})
            if "implied_volatility" in user_weights and "volatility" not in user_weights:
                user_weights["volatility"] = user_weights["implied_volatility"]
            self._merge(self._config, user_config)
        self._normalize_compatibility()

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    @classmethod
    def _merge(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                cls._merge(target[key], value)
            else:
                target[key] = deepcopy(value)

    def _normalize_compatibility(self) -> None:
        weights = self._config.setdefault("weights", {})
        if "volatility" not in weights and "implied_volatility" in weights:
            weights["volatility"] = weights["implied_volatility"]

        legacy_cache = self._config.get("cache", {})
        database = self._config.setdefault("database", {})
        if "path" not in database and legacy_cache.get("sqlite_path"):
            database["path"] = legacy_cache["sqlite_path"]

    def section(self, name: str) -> dict[str, Any]:
        return deepcopy(self._config.get(name, {}))

    @property
    def weights(self) -> dict[str, float]:
        return self.section("weights")

    @property
    def thresholds(self) -> dict[str, float]:
        return self.section("thresholds")

    def resolve_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        base = self.config_path.parent if self.config_path else PROJECT_ROOT
        return (base / path).resolve()

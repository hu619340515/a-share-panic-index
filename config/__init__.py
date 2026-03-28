"""
配置管理模块
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any

class Config:
    """配置管理类"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or self._find_config_file()
        self._config = self._load_config()
    
    def _find_config_file(self) -> str:
        """查找配置文件"""
        possible_paths = [
            "./config/settings.yaml",
            "~/.panic_index/config.yaml",
            "/etc/panic_index/config.yaml",
        ]
        for path in possible_paths:
            expanded = Path(path).expanduser()
            if expanded.exists():
                return str(expanded)
        
        # 使用默认配置
        script_dir = Path(__file__).parent
        return str(script_dir / "settings.yaml")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置"""
        if not Path(self.config_path).exists():
            return self._default_config()
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            'weights': {
                'implied_volatility': 0.40,
                'limit_up_down_ratio': 0.30,
                'futures_premium': 0.20,
                'southbound_flow': 0.10
            },
            'thresholds': {
                'greedy': 20,
                'optimistic': 40,
                'neutral': 60,
                'panic': 80,
                'extreme_panic': 100
            },
            'cache': {
                'type': 'sqlite',
                'sqlite_path': './data_cache/panic_index.db',
                'max_age_hours': 6
            },
            'alerts': {'enabled': False}
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号分隔的路径"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value: Any):
        """设置配置项"""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    def save(self):
        """保存配置到文件"""
        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)
    
    @property
    def weights(self) -> Dict[str, float]:
        return self._config.get('weights', {})
    
    @property
    def thresholds(self) -> Dict[str, int]:
        return self._config.get('thresholds', {})
    
    @property
    def cache_config(self) -> Dict[str, Any]:
        return self._config.get('cache', {})
    
    @property
    def alert_config(self) -> Dict[str, Any]:
        return self._config.get('alerts', {})
    
    @property
    def viz_config(self) -> Dict[str, Any]:
        return self._config.get('viz', {})

# 全局配置实例
_config_instance = None

def get_config(config_path: str = None) -> Config:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance

def reload_config(config_path: str = None):
    """重新加载配置"""
    global _config_instance
    _config_instance = Config(config_path)

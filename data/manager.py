"""数据管理中心"""
import pandas as pd
from typing import Dict, Any, Tuple
from data.async_manager import async_data_manager
from data.cache import get_cache_manager, MultiLevelCache
from data.database import Database


class DataManager:
    """数据管理中心"""

    def __init__(self):
        self.cache: MultiLevelCache = get_cache_manager()
        self.database: Database = Database()

    def get_data(
        self, days: int = 730, use_cache: bool = True
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        获取所有数据源

        Args:
            days: 获取天数
            use_cache: 是否使用缓存

        Returns:
            (DataFrame, dict): 数据和原始数据
        """
        # 使用异步数据管理器
        return async_data_manager.get_data_sync(days, use_cache)

    def get_latest_data(self, days: int = 30) -> pd.DataFrame:
        """
        获取最新数据

        Args:
            days: 获取天数

        Returns:
            DataFrame: 最新数据
        """
        return self.database.get_latest(days)

    def get_all_data(self) -> pd.DataFrame:
        """
        获取所有数据

        Returns:
            DataFrame: 所有数据
        """
        return self.database.get_panic_index()

    def refresh_data(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        刷新数据

        Returns:
            (DataFrame, dict): 新数据和原始数据
        """
        return self.get_data(use_cache=False)


# 全局数据管理器实例
data_manager = DataManager()

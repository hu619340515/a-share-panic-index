"""
批量数据获取器
"""
from datetime import datetime, timedelta
from typing import Dict
import pandas as pd
import akshare as ak


class BatchDataFetcher:
    """批量数据获取器"""

    def __init__(self):
        self.cache: Dict[str, Dict] = {}
        self.cache_expiry = timedelta(hours=1)

    def get_index_data(
        self, symbols: list, start_date: datetime, end_date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取指数数据

        Args:
            symbols: 指数代码列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Dict[str, pd.DataFrame]: 指数数据字典
        """
        result = {}

        for symbol in symbols:
            cache_key = f"index:{symbol}:{start_date}:{end_date}"

            # 检查缓存
            if cache_key in self.cache:
                cached_data = self.cache[cache_key]
                if datetime.now() - cached_data["timestamp"] < self.cache_expiry:
                    result[symbol] = cached_data["data"]
                    continue

            # 获取数据
            try:
                df = ak.stock_zh_index_daily(symbol=symbol)
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
                df = df[(df.index >= start_date) & (df.index <= end_date)]
                result[symbol] = df

                # 缓存数据
                self.cache[cache_key] = {"data": df, "timestamp": datetime.now()}
            except Exception as e:
                print(f"获取指数 {symbol} 数据失败: {e}")
                result[symbol] = pd.DataFrame()

        return result

    def get_futures_data(
        self, symbols: list, start_date: datetime, end_date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取期货数据

        Args:
            symbols: 期货代码列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Dict[str, pd.DataFrame]: 期货数据字典
        """
        result = {}

        for symbol in symbols:
            cache_key = f"futures:{symbol}:{start_date}:{end_date}"

            # 检查缓存
            if cache_key in self.cache:
                cached_data = self.cache[cache_key]
                if datetime.now() - cached_data["timestamp"] < self.cache_expiry:
                    result[symbol] = cached_data["data"]
                    continue

            # 获取数据
            try:
                df = ak.futures_zh_daily(symbol=symbol)
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
                df = df[(df.index >= start_date) & (df.index <= end_date)]
                result[symbol] = df

                # 缓存数据
                self.cache[cache_key] = {"data": df, "timestamp": datetime.now()}
            except Exception as e:
                print(f"获取期货 {symbol} 数据失败: {e}")
                result[symbol] = pd.DataFrame()

        return result

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()


# 全局批量数据获取器实例
batch_fetcher = BatchDataFetcher()

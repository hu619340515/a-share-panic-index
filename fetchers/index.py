"""
指数数据获取
"""

from datetime import datetime
from typing import Optional
import pandas as pd
from fetchers.base import DataFetcher
from fetchers.batch_fetcher import batch_fetcher


class IndexFetcher(DataFetcher):
    """指数数据获取器"""

    def fetch(self, start_date: datetime, end_date: datetime) -> Optional[pd.Series]:
        """获取沪深300波动率数据"""
        try:
            print("  - 指数数据...", end="", flush=True)

            # 批量获取指数数据
            symbols = ["sh000300", "sh000001"]  # 沪深300和上证指数
            index_data = batch_fetcher.get_index_data(symbols, start_date, end_date)

            # 获取沪深300数据
            df = index_data.get("sh000300")
            if df is None or df.empty:
                print("⚠️ (无数据)")
                return None

            # 计算对数收益率和波动率
            import numpy as np

            close_prices = df["close"].astype(float)
            returns = np.log(close_prices / close_prices.shift(1)).fillna(0)

            # 20日滚动波动率（年化）
            volatility = returns.rolling(window=20).std() * (252**0.5)

            # 保存原始数据
            self.raw_data["hs300"] = df["close"]
            self.raw_data["hs300_returns"] = returns

            # 获取上证指数
            sh_df = index_data.get("sh000001")
            if sh_df is not None and not sh_df.empty:
                self.raw_data["sh_index"] = sh_df["close"]

            print("✅")
            return volatility

        except Exception as e:
            print(f"⚠️ ({e})")
            return None

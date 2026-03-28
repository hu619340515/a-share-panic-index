"""
指数数据获取
"""
import time
from datetime import datetime
from typing import Optional
import pandas as pd
import akshare as ak
from fetchers.base import DataFetcher

class IndexFetcher(DataFetcher):
    """指数数据获取器"""
    
    def fetch(self, start_date: datetime, end_date: datetime) -> Optional[pd.Series]:
        """获取沪深300波动率数据"""
        try:
            print("  - 指数数据...", end="", flush=True)
            
            # 获取沪深300历史数据
            df = ak.stock_zh_index_daily(symbol='sh000300')
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 筛选日期范围
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if df.empty:
                print("⚠️ (无数据)")
                return None
            
            # 计算对数收益率和波动率
            import numpy as np
            close_prices = df['close'].astype(float)
            returns = np.log(close_prices / close_prices.shift(1)).fillna(0)
            
            # 20日滚动波动率（年化）
            volatility = returns.rolling(window=20).std() * (252 ** 0.5)
            
            # 保存原始数据
            self.raw_data['hs300'] = df['close']
            self.raw_data['hs300_returns'] = returns
            
            # 获取上证指数
            sh_df = ak.stock_zh_index_daily(symbol='sh000001')
            sh_df['date'] = pd.to_datetime(sh_df['date'])
            sh_df.set_index('date', inplace=True)
            sh_df = sh_df[(sh_df.index >= start_date) & (sh_df.index <= end_date)]
            self.raw_data['sh_index'] = sh_df['close']
            
            print("✅")
            return volatility
            
        except Exception as e:
            print(f"⚠️ ({e})")
            return None

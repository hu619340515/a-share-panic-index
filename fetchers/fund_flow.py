"""
资金流向数据获取
"""
from datetime import datetime
from typing import Optional
import pandas as pd
import akshare as ak
from fetchers.base import DataFetcher

class FundFlowFetcher(DataFetcher):
    """资金流向数据获取器"""
    
    def fetch(self, start_date: datetime, end_date: datetime) -> Optional[pd.Series]:
        """抽象方法实现 - 获取南向资金"""
        return self.fetch_southbound(start_date, end_date)
    
    def fetch_northbound(self, start_date: datetime, end_date: datetime) -> Optional[pd.Series]:
        """获取北向资金数据"""
        try:
            print("  - 北向资金...", end="", flush=True)
            
            df = ak.stock_hsgt_hist_em(symbol='北向资金')
            
            if df.empty:
                print("⚠️ (无数据)")
                return None
            
            df['date'] = pd.to_datetime(df['日期'])
            df.set_index('date', inplace=True)
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            self.raw_data['northbound'] = df['当日成交净买额']
            print(f"✅ ({len(df)}天)")
            return df['当日成交净买额']
            
        except Exception as e:
            print(f"⚠️ ({e})")
            return None
    
    def fetch_southbound(self, start_date: datetime, end_date: datetime) -> Optional[pd.Series]:
        """获取南向资金数据"""
        try:
            print("  - 南向资金...", end="", flush=True)
            
            df = ak.stock_hsgt_hist_em(symbol='南向资金')
            
            if df.empty:
                print("⚠️ (无数据)")
                return None
            
            df['date'] = pd.to_datetime(df['日期'])
            df.set_index('date', inplace=True)
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            self.raw_data['southbound'] = df['当日成交净买额']
            print(f"✅ ({len(df)}天)")
            return df['当日成交净买额']
            
        except Exception as e:
            print(f"⚠️ ({e})")
            return None

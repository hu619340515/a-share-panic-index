"""
期货数据获取
"""
from datetime import datetime
from typing import Optional
import pandas as pd
import akshare as ak
from fetchers.base import DataFetcher

class FuturesFetcher(DataFetcher):
    """股指期货数据获取器"""
    
    def fetch(self, start_date: datetime, end_date: datetime, 
              spot_prices: Optional[pd.Series] = None) -> Optional[pd.Series]:
        """获取股指期货贴水数据"""
        try:
            print("  - 股指期货...", end="", flush=True)
            
            # 获取IF主力合约
            futures_df = ak.futures_main_sina(symbol="IF0")
            
            if futures_df.empty:
                print("⚠️ (无数据)")
                return None
            
            futures_df['date'] = pd.to_datetime(futures_df['日期'])
            futures_df.set_index('date', inplace=True)
            futures_df = futures_df[(futures_df.index >= start_date) & 
                                   (futures_df.index <= end_date)]
            
            # 如果有现货价格，计算基差
            if spot_prices is not None:
                combined = pd.concat([spot_prices, futures_df['收盘价']], 
                                   axis=1, join='inner')
                combined.columns = ['spot', 'futures']
                basis = (combined['spot'] - combined['futures']) / combined['spot']
                print("✅")
                return basis
            else:
                # 用期货收益率的负值作为替代
                fut_returns = futures_df['收盘价'].pct_change()
                basis_proxy = -fut_returns.rolling(window=5).mean()
                print("✅")
                return basis_proxy
                
        except Exception as e:
            print(f"⚠️ ({e})")
            return None

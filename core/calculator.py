"""
恐慌指数计算模块
"""
import pandas as pd
import numpy as np
from config import get_config

class PanicIndexCalculator:
    """恐慌指数计算器"""
    
    def __init__(self):
        self.config = get_config()
        self.weights = self.config.weights
        self.thresholds = self.config.thresholds
    
    def standardize(self, series: pd.Series) -> pd.Series:
        """
        标准化时间序列 - 使用全局分位数
        这样即使数据量少也能计算
        """
        valid_data = series.dropna()
        
        if len(valid_data) < 5:
            return pd.Series(0.5, index=series.index)
        
        data_min = valid_data.min()
        data_max = valid_data.max()
        
        if data_max == data_min:
            return pd.Series(0.5, index=series.index)
        
        standardized = (series - data_min) / (data_max - data_min)
        return standardized.clip(0, 1)
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算恐慌指数
        
        Args:
            data: 包含各指标的DataFrame
                - iv: 隐含波动率
                - limit_ratio: 涨跌停比
                - futures_basis: 期货贴水
                - southbound_flow: 南向资金
                
        Returns:
            添加了panic_index和status列的DataFrame
        """
        df = data.copy()
        
        print("\n正在计算恐慌指数...")
        
        # 标准化各分项指标
        df['iv_std'] = self.standardize(df['iv']) if 'iv' in df.columns else 0.5
        df['limit_std'] = self.standardize(df['limit_ratio']) if 'limit_ratio' in df.columns else 0.5
        df['basis_std'] = self.standardize(df['futures_basis']) if 'futures_basis' in df.columns else 0.5
        
        # 南向资金（取负值，因为流出表示恐慌）
        if 'southbound_flow' in df.columns:
            df['south_std'] = self.standardize(-df['southbound_flow'])
        else:
            df['south_std'] = 0.5
        
        # 计算加权恐慌指数 (0-100)
        df['panic_index'] = (
            self.weights.get('implied_volatility', 0.40) * df['iv_std'] +
            self.weights.get('limit_up_down_ratio', 0.30) * df['limit_std'] +
            self.weights.get('futures_premium', 0.20) * df['basis_std'] +
            self.weights.get('southbound_flow', 0.10) * df['south_std']
        ) * 100
        
        # 添加情绪状态
        df['status'] = df['panic_index'].apply(self.get_status)
        
        return df
    
    def get_status(self, value: float) -> str:
        """根据恐慌指数获取情绪状态"""
        if pd.isna(value):
            return '未知'
        
        if value < self.thresholds.get('greedy', 20):
            return '贪婪'
        elif value < self.thresholds.get('optimistic', 40):
            return '乐观'
        elif value < self.thresholds.get('neutral', 60):
            return '中性'
        elif value < self.thresholds.get('panic', 80):
            return '恐慌'
        else:
            return '极度恐慌'
    
    def get_signal(self, panic_index: float) -> dict:
        """根据恐慌指数生成交易信号"""
        if panic_index >= 80:
            return {
                'signal': 'buy',
                'strength': 'strong',
                'reason': '极度恐慌，可能是买入时机'
            }
        elif panic_index >= 60:
            return {
                'signal': 'watch',
                'strength': 'medium',
                'reason': '恐慌情绪，开始关注机会'
            }
        elif panic_index <= 20:
            return {
                'signal': 'sell',
                'strength': 'strong',
                'reason': '极度贪婪，注意风险'
            }
        elif panic_index <= 40:
            return {
                'signal': 'hold',
                'strength': 'weak',
                'reason': '乐观情绪，可持有'
            }
        else:
            return {
                'signal': 'neutral',
                'strength': 'none',
                'reason': '中性情绪，观望为主'
            }

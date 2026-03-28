"""
回测模块
"""
import pandas as pd
import numpy as np
from typing import Dict, List
from core.calculator import PanicIndexCalculator

class Backtester:
    """恐慌指数策略回测器"""
    
    def __init__(self, 
                 initial_capital: float = 100000,
                 commission: float = 0.0003,
                 slippage: float = 0.001):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.calculator = PanicIndexCalculator()
    
    def run(self, 
            panic_index_df: pd.DataFrame,
            price_series: pd.Series,
            strategy: str = 'extreme_panic_buy') -> Dict:
        """
        运行回测
        
        Args:
            panic_index_df: 包含panic_index的DataFrame
            price_series: 价格序列（如沪深300收盘价）
            strategy: 策略名称
                - extreme_panic_buy: 恐慌>80买入，<20卖出
                - panic_buy: 恐慌>60买入，<40卖出
                - contrarian: 反向策略
        
        Returns:
            回测结果字典
        """
        # 合并数据
        df = panic_index_df.join(price_series.rename('price'), how='inner')
        df = df.dropna()
        
        if len(df) < 10:
            return {'error': '数据不足，无法回测'}
        
        # 初始化
        capital = self.initial_capital
        position = 0  # 持仓数量
        trades = []
        equity_curve = []
        
        for date, row in df.iterrows():
            price = row['price']
            panic = row['panic_index']
            
            # 根据策略生成信号
            signal = self._get_signal(panic, strategy)
            
            # 执行交易
            if signal == 'buy' and position == 0:
                # 买入
                cost = price * (1 + self.slippage)
                shares = int(capital * (1 - self.commission) / cost)
                if shares > 0:
                    position = shares
                    capital -= shares * cost * (1 + self.commission)
                    trades.append({
                        'date': date,
                        'action': 'buy',
                        'price': cost,
                        'shares': shares,
                        'panic': panic
                    })
            
            elif signal == 'sell' and position > 0:
                # 卖出
                revenue = position * price * (1 - self.slippage)
                capital += revenue * (1 - self.commission)
                trades.append({
                    'date': date,
                    'action': 'sell',
                    'price': price * (1 - self.slippage),
                    'shares': position,
                    'panic': panic,
                    'pnl': revenue - trades[-1]['price'] * position if trades else 0
                })
                position = 0
            
            # 计算当前权益
            equity = capital + position * price
            equity_curve.append({'date': date, 'equity': equity})
        
        # 最终平仓
        if position > 0:
            revenue = position * df['price'].iloc[-1] * (1 - self.slippage)
            capital += revenue * (1 - self.commission)
        
        # 计算指标
        final_capital = capital
        total_return = (final_capital - self.initial_capital) / self.initial_capital
        
        equity_df = pd.DataFrame(equity_curve).set_index('date')
        max_drawdown = self._calc_max_drawdown(equity_df['equity'])
        sharpe = self._calc_sharpe(equity_df['equity'])
        
        # 统计交易
        buy_trades = [t for t in trades if t['action'] == 'buy']
        sell_trades = [t for t in trades if t['action'] == 'sell']
        
        winning_trades = [t for t in sell_trades if t.get('pnl', 0) > 0]
        win_rate = len(winning_trades) / len(sell_trades) if sell_trades else 0
        
        # 买入持有基准
        buy_hold_return = (df['price'].iloc[-1] - df['price'].iloc[0]) / df['price'].iloc[0]
        
        return {
            'strategy': strategy,
            'start_date': df.index[0].strftime('%Y-%m-%d'),
            'end_date': df.index[-1].strftime('%Y-%m-%d'),
            'initial_capital': self.initial_capital,
            'final_capital': final_capital,
            'total_return': total_return,
            'annual_return': (1 + total_return) ** (252 / len(df)) - 1,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'trade_count': len(sell_trades),
            'win_rate': win_rate,
            'buy_hold_return': buy_hold_return,
            'alpha': total_return - buy_hold_return,
            'trades': trades,
            'equity_curve': equity_curve
        }
    
    def _get_signal(self, panic_index: float, strategy: str) -> str:
        """根据策略生成信号"""
        if strategy == 'extreme_panic_buy':
            if panic_index >= 80:
                return 'buy'
            elif panic_index <= 20:
                return 'sell'
        elif strategy == 'panic_buy':
            if panic_index >= 60:
                return 'buy'
            elif panic_index <= 40:
                return 'sell'
        elif strategy == 'contrarian':
            if panic_index <= 20:
                return 'buy'
            elif panic_index >= 80:
                return 'sell'
        return 'hold'
    
    def _calc_max_drawdown(self, equity: pd.Series) -> float:
        """计算最大回撤"""
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        return drawdown.min()
    
    def _calc_sharpe(self, equity: pd.Series, risk_free_rate: float = 0.03) -> float:
        """计算夏普比率"""
        returns = equity.pct_change().dropna()
        if len(returns) < 2 or returns.std() == 0:
            return 0
        excess_returns = returns.mean() * 252 - risk_free_rate
        return excess_returns / (returns.std() * (252 ** 0.5))

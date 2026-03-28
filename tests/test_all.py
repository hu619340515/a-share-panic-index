"""
测试模块
"""
import unittest
import sys
from pathlib import Path
import pandas as pd
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.calculator import PanicIndexCalculator
from core.backtest import Backtester

class TestPanicIndexCalculator(unittest.TestCase):
    """测试恐慌指数计算器"""
    
    def test_standardize(self):
        """测试标准化函数"""
        calc = PanicIndexCalculator()
        series = pd.Series([0, 0.5, 1.0, 1.5, 2.0])
        result = calc.standardize(series)
        
        self.assertEqual(result.iloc[0], 0.0)
        self.assertEqual(result.iloc[-1], 1.0)
        self.assertTrue((result >= 0).all() and (result <= 1).all())
    
    def test_calculate(self):
        """测试恐慌指数计算"""
        calc = PanicIndexCalculator()
        
        data = pd.DataFrame({
            'iv': [0.2, 0.3, 0.4],
            'limit_ratio': [0.1, 0.5, 0.9],
            'futures_basis': [-0.01, 0, 0.01],
            'southbound_flow': [10, 0, -10]
        })
        
        result = calc.calculate(data)
        
        self.assertIn('panic_index', result.columns)
        self.assertIn('status', result.columns)
        self.assertTrue((result['panic_index'] >= 0).all())
        self.assertTrue((result['panic_index'] <= 100).all())
    
    def test_get_status(self):
        """测试情绪状态判断"""
        calc = PanicIndexCalculator()
        
        self.assertEqual(calc.get_status(15), '贪婪')
        self.assertEqual(calc.get_status(35), '乐观')
        self.assertEqual(calc.get_status(55), '中性')
        self.assertEqual(calc.get_status(75), '恐慌')
        self.assertEqual(calc.get_status(85), '极度恐慌')
    
    def test_get_signal(self):
        """测试交易信号生成"""
        calc = PanicIndexCalculator()
        
        signal = calc.get_signal(85)
        self.assertEqual(signal['signal'], 'buy')
        self.assertEqual(signal['strength'], 'strong')
        
        signal = calc.get_signal(15)
        self.assertEqual(signal['signal'], 'sell')


class TestBacktester(unittest.TestCase):
    """测试回测器"""
    
    def test_max_drawdown(self):
        """测试最大回撤计算"""
        bt = Backtester()
        
        equity = pd.Series([100, 110, 105, 120, 100, 130])
        max_dd = bt._calc_max_drawdown(equity)
        
        # 从120跌到100，回撤-16.67%
        self.assertLess(max_dd, 0)
        self.assertGreater(max_dd, -0.2)
    
    def test_sharpe(self):
        """测试夏普比率计算"""
        bt = Backtester()
        
        # 生成正收益序列
        equity = pd.Series([100 * (1.001 ** i) for i in range(100)])
        sharpe = bt._calc_sharpe(equity)
        
        self.assertGreater(sharpe, 0)
    
    def test_backtest_run(self):
        """测试回测运行"""
        bt = Backtester()
        
        # 创建模拟数据
        dates = pd.date_range('2024-01-01', periods=100, freq='B')
        panic_df = pd.DataFrame({
            'panic_index': [30 + i % 60 for i in range(100)]
        }, index=dates)
        
        price = pd.Series([3000 + i * 5 for i in range(100)], index=dates)
        
        result = bt.run(panic_df, price, 'extreme_panic_buy')
        
        self.assertIn('total_return', result)
        self.assertIn('max_drawdown', result)
        self.assertIn('sharpe_ratio', result)


class TestConfig(unittest.TestCase):
    """测试配置管理"""
    
    def test_config_get_set(self):
        """测试配置读写"""
        from config import Config
        
        config = Config()
        
        # 测试获取
        weights = config.weights
        self.assertIsInstance(weights, dict)
        self.assertIn('implied_volatility', weights)
        
        # 测试设置
        config.set('test.key', 'value')
        self.assertEqual(config.get('test.key'), 'value')


def run_tests():
    """运行所有测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestPanicIndexCalculator))
    suite.addTests(loader.loadTestsFromTestCase(TestBacktester))
    suite.addTests(loader.loadTestsFromTestCase(TestConfig))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)

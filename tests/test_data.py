"""
数据管理模块测试
"""

import unittest
import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.manager import DataManager
from data.cache import MultiLevelCache, get_cache_manager
from data.database import Database


class TestDataManager(unittest.TestCase):
    """测试数据管理中心"""

    def setUp(self):
        """设置测试环境"""
        self.data_manager = DataManager()

    def test_get_data(self):
        """测试获取数据"""
        data, raw_data = self.data_manager.get_data(days=7)
        
        # 检查返回类型
        self.assertIsInstance(data, pd.DataFrame)
        self.assertIsInstance(raw_data, dict)
        
        # 检查数据不为空
        self.assertFalse(data.empty)

    def test_get_latest_data(self):
        """测试获取最新数据"""
        df = self.data_manager.get_latest_data(days=30)
        
        self.assertIsInstance(df, pd.DataFrame)

    def test_refresh_data(self):
        """测试刷新数据"""
        data, raw_data = self.data_manager.refresh_data()
        
        self.assertIsInstance(data, pd.DataFrame)
        self.assertIsInstance(raw_data, dict)


class TestCache(unittest.TestCase):
    """测试缓存系统"""

    def setUp(self):
        """设置测试环境"""
        self.cache = get_cache_manager()

    def test_cache_instance(self):
        """测试缓存实例"""
        self.assertIsInstance(self.cache, MultiLevelCache)

    def test_cache_load(self):
        """测试缓存加载"""
        data = self.cache.load()
        
        # 数据可能为空，但应该返回None或DataFrame
        if data is not None:
            self.assertIsInstance(data, pd.DataFrame)

    def test_cache_save(self):
        """测试缓存保存"""
        test_data = pd.DataFrame({
            'panic_index': [50, 60, 70],
            'status': ['中性', '恐慌', '极度恐慌']
        }, index=pd.date_range('2024-01-01', periods=3))
        
        self.cache.save(test_data)
        
        # 验证保存后可以加载
        loaded_data = self.cache.load()
        if loaded_data is not None:
            self.assertFalse(loaded_data.empty)


class TestDatabase(unittest.TestCase):
    """测试数据库模块"""

    def setUp(self):
        """设置测试环境"""
        self.db = Database(db_path="./test_panic_index.db")

    def test_init_db(self):
        """测试数据库初始化"""
        # 测试是否能正常连接
        self.assertTrue(True)  # 如果初始化失败会抛出异常

    def test_save_and_get_panic_index(self):
        """测试保存和获取恐慌指数"""
        test_data = pd.DataFrame({
            'panic_index': [50, 60, 70],
            'status': ['中性', '恐慌', '极度恐慌'],
            'iv': [0.2, 0.3, 0.4],
            'limit_ratio': [0.5, 0.6, 0.7]
        }, index=pd.date_range('2024-01-01', periods=3))
        
        # 保存数据
        self.db.save_panic_index(test_data)
        
        # 获取数据
        retrieved_data = self.db.get_panic_index()
        
        self.assertIsInstance(retrieved_data, pd.DataFrame)
        self.assertFalse(retrieved_data.empty)

    def test_get_latest(self):
        """测试获取最新数据"""
        df = self.db.get_latest(days=7)
        
        self.assertIsInstance(df, pd.DataFrame)

    def test_save_signal(self):
        """测试保存交易信号"""
        self.db.save_signal(
            date="2024-01-01",
            signal_type="buy",
            panic_index=85.0,
            reason="极度恐慌，买入时机"
        )
        
        # 验证信号已保存
        signals = self.db.get_signals(limit=1)
        self.assertFalse(signals.empty)


def run_tests():
    """运行数据模块测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDataManager))
    suite.addTests(loader.loadTestsFromTestCase(TestCache))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

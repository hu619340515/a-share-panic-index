"""
CLI命令模块测试
"""

import unittest
import sys
from pathlib import Path
import argparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cli.commands.current import cmd_current
from cli.commands.history import cmd_history
from cli.commands.chart import cmd_chart
from cli.commands.backtest import cmd_backtest
from cli.commands.alert import cmd_alert
from cli.commands.config import cmd_config
from cli.commands.monitor import cmd_monitor


class TestCLICommands(unittest.TestCase):
    """测试CLI命令"""

    def setUp(self):
        """设置测试环境"""
        # 创建模拟参数对象
        class MockArgs:
            def __init__(self):
                self.days = 7
                self.output = "test_chart.png"
                self.type = "simple"
                self.action = "list"
                self.key = "weights.implied_volatility"
                self.value = "0.4"
        
        self.args = MockArgs()

    def test_cmd_current(self):
        """测试获取当前恐慌指数命令"""
        try:
            cmd_current(self.args)
            # 如果执行成功，测试通过
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"cmd_current 执行失败: {e}")

    def test_cmd_history(self):
        """测试查看历史数据命令"""
        try:
            cmd_history(self.args)
            # 如果执行成功，测试通过
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"cmd_history 执行失败: {e}")

    def test_cmd_chart(self):
        """测试生成图表命令"""
        try:
            cmd_chart(self.args)
            # 如果执行成功，测试通过
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"cmd_chart 执行失败: {e}")

    def test_cmd_alert(self):
        """测试告警命令"""
        try:
            cmd_alert(self.args)
            # 如果执行成功，测试通过
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"cmd_alert 执行失败: {e}")

    def test_cmd_config(self):
        """测试配置命令"""
        try:
            # 测试列出配置
            self.args.action = "list"
            cmd_config(self.args)
            
            # 测试获取配置
            self.args.action = "get"
            cmd_config(self.args)
            
            # 测试设置配置
            self.args.action = "set"
            cmd_config(self.args)
            
            # 如果执行成功，测试通过
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"cmd_config 执行失败: {e}")


def run_tests():
    """运行CLI命令测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCLICommands))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
A股恐慌指数 - CLI工具

Usage:
    panic-index current          # 获取当前恐慌指数
    panic-index history          # 查看历史数据
    panic-index chart            # 生成图表
    panic-index backtest         # 运行回测
    panic-index alert            # 测试告警
    panic-index config get KEY   # 获取配置
    panic-index config set KEY VALUE  # 设置配置
    panic-index monitor          # 启动监控模式
"""

import sys
import argparse
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入命令模块
from cli.commands.current import cmd_current
from cli.commands.history import cmd_history
from cli.commands.chart import cmd_chart
from cli.commands.backtest import cmd_backtest
from cli.commands.alert import cmd_alert
from cli.commands.config import cmd_config
from cli.commands.monitor import cmd_monitor


def main():
    parser = argparse.ArgumentParser(
        description="A股恐慌指数监控工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # current 命令
    current_parser = subparsers.add_parser("current", help="获取当前恐慌指数")

    # history 命令
    history_parser = subparsers.add_parser("history", help="查看历史数据")
    history_parser.add_argument("--days", "-d", type=int, default=30, help="查看天数")

    # chart 命令
    chart_parser = subparsers.add_parser("chart", help="生成图表")
    chart_parser.add_argument("--days", "-d", type=int, default=730, help="天数")
    chart_parser.add_argument(
        "--type",
        "-t",
        choices=["simple", "comprehensive", "comparison"],
        default="comprehensive",
        help="图表类型 (simple:简化, comprehensive:综合面板, comparison:双轴对比)",
    )
    chart_parser.add_argument(
        "--output", "-o", default="panic_chart.png", help="输出文件"
    )

    # backtest 命令
    backtest_parser = subparsers.add_parser("backtest", help="运行回测")

    # alert 命令
    alert_parser = subparsers.add_parser("alert", help="测试告警")

    # config 命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument("action", choices=["get", "set", "list"])
    config_parser.add_argument("key", nargs="?", help="配置键")
    config_parser.add_argument("value", nargs="?", help="配置值")

    # monitor 命令
    monitor_parser = subparsers.add_parser("monitor", help="监控模式")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # 执行命令
    commands = {
        "current": cmd_current,
        "history": cmd_history,
        "chart": cmd_chart,
        "backtest": cmd_backtest,
        "alert": cmd_alert,
        "config": cmd_config,
        "monitor": cmd_monitor,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

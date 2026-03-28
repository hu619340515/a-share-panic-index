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
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import get_config, reload_config
from data.cache import get_cache_manager
from data.database import Database
from core.calculator import PanicIndexCalculator
from core.backtest import Backtester
from viz.charts import Visualizer
from alerts.notifier import AlertManager
from fetchers.index import IndexFetcher
from fetchers.limit_up import LimitUpDownFetcher
from fetchers.futures import FuturesFetcher
from fetchers.fund_flow import FundFlowFetcher

import pandas as pd
import akshare as ak

def fetch_all_data(days: int = 730):
    """获取所有数据源"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print(f"正在获取数据 ({start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')})...")
    
    result = pd.DataFrame()
    raw_data = {}
    
    # 1. 指数数据（波动率）
    index_fetcher = IndexFetcher()
    iv = index_fetcher.fetch(start_date, end_date)
    if iv is not None:
        result['iv'] = iv
        raw_data.update(index_fetcher.get_raw_data())
    
    # 2. 涨跌停数据
    limit_fetcher = LimitUpDownFetcher()
    limit_df = limit_fetcher.fetch(start_date, end_date)
    if limit_df is not None:
        result = result.join(limit_df[['limit_ratio', 'limit_up', 'limit_down']], how='outer')
        raw_data.update(limit_fetcher.get_raw_data())
    
    # 3. 期货数据
    futures_fetcher = FuturesFetcher()
    basis = futures_fetcher.fetch(start_date, end_date, raw_data.get('hs300'))
    if basis is not None:
        result['futures_basis'] = basis
    
    # 4. 南向资金
    flow_fetcher = FundFlowFetcher()
    southbound = flow_fetcher.fetch_southbound(start_date, end_date)
    if southbound is not None:
        result['southbound_flow'] = southbound
        raw_data.update(flow_fetcher.get_raw_data())
    
    # 归一化索引
    result.index = pd.to_datetime(result.index).normalize()
    result = result[~result.index.duplicated(keep='last')]
    result.sort_index(inplace=True)
    
    return result, raw_data

def cmd_current(args):
    """获取当前恐慌指数"""
    config = get_config()
    cache = get_cache_manager()
    
    # 尝试从缓存加载
    df = cache.load()
    
    if df is None:
        print("缓存无效，正在从API获取数据...")
        data, raw_data = fetch_all_data()
        
        # 计算恐慌指数
        calculator = PanicIndexCalculator()
        df = calculator.calculate(data)
        
        # 保存到缓存
        cache.save(df)
        
        # 保存到数据库
        db = Database()
        db.save_panic_index(df)
    else:
        print("✅ 使用缓存数据")
    
    # 显示结果
    latest = df.iloc[-1]
    print("\n" + "="*50)
    print("📊 A股恐慌指数")
    print("="*50)
    print(f"日期: {latest.name.strftime('%Y-%m-%d')}")
    print(f"恐慌指数: {latest['panic_index']:.2f} ({latest['status']})")
    print(f"波动率: {latest.get('iv', 0)*100:.2f}%")
    print(f"涨跌停比: {latest.get('limit_ratio', 0)*100:.1f}%")
    
    # 生成信号
    calculator = PanicIndexCalculator()
    signal = calculator.get_signal(latest['panic_index'])
    print(f"\n💡 操作建议: {signal['reason']}")
    
    # 检查告警
    alert = AlertManager()
    alerted = alert.check_and_send(latest['panic_index'], latest['status'], 
                                   latest.name.strftime('%Y-%m-%d'))
    if alerted:
        print("🚨 已触发告警")
    
    print("="*50)

def cmd_history(args):
    """查看历史数据"""
    db = Database()
    days = args.days if hasattr(args, 'days') else 30
    df = db.get_latest(days)
    
    if df.empty:
        print("数据库中没有数据，请先运行 'panic-index current'")
        return
    
    print(f"\n最近{days}天恐慌指数历史:")
    print("-" * 50)
    print(f"{'日期':<12} {'指数':<8} {'状态':<8}")
    print("-" * 50)
    
    for date, row in df.iterrows():
        print(f"{date.strftime('%Y-%m-%d'):<12} {row['panic_index']:<8.2f} {row['status']:<8}")
    
    print("-" * 50)
    print(f"平均: {df['panic_index'].mean():.2f}")
    print(f"最高: {df['panic_index'].max():.2f} ({df['panic_index'].idxmax().strftime('%Y-%m-%d')})")
    print(f"最低: {df['panic_index'].min():.2f} ({df['panic_index'].idxmin().strftime('%Y-%m-%d')})")

def cmd_chart(args):
    """生成图表"""
    days = args.days if hasattr(args, 'days') else 90
    output = args.output if hasattr(args, 'output') else 'panic_chart.png'
    chart_type = args.type if hasattr(args, 'type') else 'comprehensive'
    
    viz = Visualizer()
    
    if chart_type == 'simple':
        # 简化图表 - 使用数据库数据
        db = Database()
        df = db.get_latest(days)
        
        if df.empty:
            print("数据库中没有数据，请先运行 'panic-index current'")
            return
        
        viz.plot_simple(df, output)
    else:
        # 需要完整数据的图表
        print(f"正在获取完整数据生成{chart_type}图表...")
        data, raw_data = fetch_all_data(days)
        
        if data.empty:
            print("获取数据失败")
            return
        
        # 计算恐慌指数
        calculator = PanicIndexCalculator()
        df = calculator.calculate(data)
        
        if chart_type == 'comparison':
            viz.plot_comparison(df, raw_data, output)
        else:
            viz.plot_comprehensive(df, raw_data, output)
    
    print(f"✅ 图表已保存: {output}")

def cmd_backtest(args):
    """运行回测"""
    db = Database()
    df = db.get_panic_index()
    
    if df.empty:
        print("数据库中没有数据，请先运行 'panic-index current'")
        return
    
    # 获取价格数据
    try:
        price_df = ak.stock_zh_index_daily(symbol='sh000300')
        price_df['date'] = pd.to_datetime(price_df['date'])
        price_df.set_index('date', inplace=True)
        price_series = price_df['close']
    except Exception as e:
        print(f"获取价格数据失败: {e}")
        return
    
    # 运行回测
    backtester = Backtester()
    
    strategies = ['extreme_panic_buy', 'panic_buy', 'contrarian']
    
    print("\n" + "="*60)
    print("📊 策略回测结果")
    print("="*60)
    
    for strategy in strategies:
        result = backtester.run(df, price_series, strategy)
        
        if 'error' in result:
            print(f"\n{strategy}: {result['error']}")
            continue
        
        print(f"\n📈 策略: {strategy}")
        print(f"  期间: {result['start_date']} ~ {result['end_date']}")
        print(f"  总收益: {result['total_return']*100:.2f}%")
        print(f"  年化收益: {result['annual_return']*100:.2f}%")
        print(f"  最大回撤: {result['max_drawdown']*100:.2f}%")
        print(f"  夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"  交易次数: {result['trade_count']}")
        print(f"  胜率: {result['win_rate']*100:.1f}%")
        print(f"  相对买入持有: {result['alpha']*100:.2f}%")
    
    print("="*60)

def cmd_alert(args):
    """测试告警"""
    alert = AlertManager()
    
    # 模拟各种情况
    test_cases = [
        (15, '贪婪', '2024-01-01'),
        (35, '乐观', '2024-01-02'),
        (65, '恐慌', '2024-01-03'),
        (85, '极度恐慌', '2024-01-04'),
    ]
    
    print("测试告警系统...")
    for panic, status, date in test_cases:
        print(f"\n测试: 恐慌指数={panic} ({status})")
        alerted = alert.check_and_send(panic, status, date)
        print(f"  结果: {'✅ 已触发' if alerted else '⏭️ 未触发'}")

def cmd_config(args):
    """配置管理"""
    config = get_config()
    
    if args.action == 'get':
        value = config.get(args.key)
        print(f"{args.key} = {value}")
    
    elif args.action == 'set':
        # 尝试转换类型
        try:
            value = float(args.value)
        except ValueError:
            try:
                value = int(args.value)
            except ValueError:
                value = args.value
        
        config.set(args.key, value)
        config.save()
        print(f"✅ 已设置: {args.key} = {value}")
    
    elif args.action == 'list':
        import yaml
        print(yaml.dump(config._config, allow_unicode=True))

def cmd_monitor(args):
    """监控模式"""
    import time
    
    print("启动监控模式...")
    print("按 Ctrl+C 停止")
    
    try:
        while True:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查数据...")
            cmd_current(args)
            
            # 每30分钟检查一次
            time.sleep(1800)
    
    except KeyboardInterrupt:
        print("\n监控已停止")

def main():
    parser = argparse.ArgumentParser(
        description='A股恐慌指数监控工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # current 命令
    current_parser = subparsers.add_parser('current', help='获取当前恐慌指数')
    
    # history 命令
    history_parser = subparsers.add_parser('history', help='查看历史数据')
    history_parser.add_argument('--days', '-d', type=int, default=30, help='查看天数')
    
    # chart 命令
    chart_parser = subparsers.add_parser('chart', help='生成图表')
    chart_parser.add_argument('--days', '-d', type=int, default=90, help='天数')
    chart_parser.add_argument('--type', '-t', choices=['simple', 'comprehensive', 'comparison'], 
                             default='comprehensive', help='图表类型 (simple:简化, comprehensive:综合面板, comparison:双轴对比)')
    chart_parser.add_argument('--output', '-o', default='panic_chart.png', help='输出文件')
    
    # backtest 命令
    backtest_parser = subparsers.add_parser('backtest', help='运行回测')
    
    # alert 命令
    alert_parser = subparsers.add_parser('alert', help='测试告警')
    
    # config 命令
    config_parser = subparsers.add_parser('config', help='配置管理')
    config_parser.add_argument('action', choices=['get', 'set', 'list'])
    config_parser.add_argument('key', nargs='?', help='配置键')
    config_parser.add_argument('value', nargs='?', help='配置值')
    
    # monitor 命令
    monitor_parser = subparsers.add_parser('monitor', help='监控模式')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    # 执行命令
    commands = {
        'current': cmd_current,
        'history': cmd_history,
        'chart': cmd_chart,
        'backtest': cmd_backtest,
        'alert': cmd_alert,
        'config': cmd_config,
        'monitor': cmd_monitor,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

"""运行回测命令"""

import akshare as ak
import pandas as pd
from typing import Any
from data import data_manager
from core.backtest import Backtester
from utils import error_handler


@error_handler(retry=2, delay=1)
def cmd_backtest(args: Any) -> None:
    """运行回测"""
    df = data_manager.get_all_data()

    if df.empty:
        print("数据库中没有数据，请先运行 'panic-index current'")
        return

    # 获取价格数据
    try:
        price_df = ak.stock_zh_index_daily(symbol="sh000300")
        price_df["date"] = pd.to_datetime(price_df["date"])
        price_df.set_index("date", inplace=True)
        price_series = price_df["close"]
    except Exception as e:
        print(f"获取价格数据失败: {e}")
        return

    # 运行回测
    backtester = Backtester()

    strategies = ["extreme_panic_buy", "panic_buy", "contrarian"]

    print("\n" + "=" * 60)
    print("📊 策略回测结果")
    print("=" * 60)

    for strategy in strategies:
        result = backtester.run(df, price_series, strategy)

        if "error" in result:
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

    print("=" * 60)

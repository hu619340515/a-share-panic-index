"""查看历史数据命令"""

from typing import Any
import pandas as pd
from data import data_manager
from utils import error_handler


@error_handler(retry=2, delay=1)
def cmd_history(args: Any) -> None:
    """查看历史数据"""
    days = args.days if hasattr(args, "days") else 30
    df = data_manager.get_latest_data(days)

    if df.empty:
        print("数据库中没有数据，请先运行 'panic-index current'")
        return

    print(f"\n最近{days}天恐慌指数历史:")
    print("-" * 50)
    print(f"{'日期':<12} {'指数':<8} {'状态':<8}")
    print("-" * 50)

    for date, row in df.iterrows():
        panic_index = row['panic_index']
        status = row['status']
        panic_str = f"{panic_index:.2f}" if panic_index is not None else "N/A"
        status_str = status if status is not None else "未知"
        print(
            f"{date.strftime('%Y-%m-%d'):<12} {panic_str:<8} {status_str:<8}"
        )

    print("-" * 50)
    
    # 计算统计值并处理空数据
    mean_val = df['panic_index'].mean()
    max_val = df['panic_index'].max()
    min_val = df['panic_index'].min()
    
    mean_str = f"{mean_val:.2f}" if pd.notna(mean_val) else "N/A"
    print(f"平均: {mean_str}")
    
    if pd.notna(max_val):
        max_date = df['panic_index'].idxmax()
        max_date_str = max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else "未知"
        print(f"最高: {max_val:.2f} ({max_date_str})")
    else:
        print("最高: N/A")
    
    if pd.notna(min_val):
        min_date = df['panic_index'].idxmin()
        min_date_str = min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else "未知"
        print(f"最低: {min_val:.2f} ({min_date_str})")
    else:
        print("最低: N/A")

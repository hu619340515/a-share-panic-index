"""生成图表命令"""

from typing import Any
from viz.charts import Visualizer
from data import data_manager
from core.calculator import PanicIndexCalculator
from utils import error_handler


@error_handler(retry=2, delay=1)
def cmd_chart(args: Any) -> None:
    """生成恐慌指数图表"""
    days = args.days if hasattr(args, "days") else 730
    output = args.output if hasattr(args, "output") else "panic_chart.png"
    chart_type = args.type if hasattr(args, "type") else "comprehensive"

    viz = Visualizer()

    if chart_type == "simple":
        # 简化图表 - 使用数据库数据
        df = data_manager.get_latest_data(days)

        if df.empty:
            print("数据库中没有数据，请先运行 'panic-index current'")
            return

        viz.plot_simple(df, output)
    else:
        # 需要完整数据的图表
        print(f"正在获取完整数据生成{chart_type}图表...")
        # 强制重新获取数据，不使用缓存，以获取近2年的数据
        data, raw_data = data_manager.get_data(days, use_cache=False)

        if data.empty:
            print("获取数据失败")
            return

        # 计算恐慌指数
        calculator = PanicIndexCalculator()
        df = calculator.calculate(data)

        if chart_type == "comparison":
            viz.plot_comparison(df, raw_data, output)
        else:
            viz.plot_comprehensive(df, raw_data, output)

    print(f"✅ 图表已保存: {output}")

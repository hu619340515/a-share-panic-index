"""获取当前恐慌指数命令"""

from typing import Any
from data import data_manager
from core.calculator import PanicIndexCalculator
from alerts.notifier import AlertManager
from utils import error_handler


@error_handler(retry=3, delay=1)
def cmd_current(args: Any) -> None:
    """获取当前恐慌指数"""
    # 获取数据
    data, raw_data = data_manager.get_data()

    # 计算恐慌指数
    calculator = PanicIndexCalculator()
    df = calculator.calculate(data)

    # 显示结果
    latest = df.iloc[-1]
    print("\n" + "=" * 50)
    print("📊 A股恐慌指数")
    print("=" * 50)
    print(f"日期: {latest.name.strftime('%Y-%m-%d')}")
    print(f"恐慌指数: {latest['panic_index']:.2f} ({latest['status']})")
    print(f"波动率: {latest.get('iv', 0)*100:.2f}%")
    print(f"涨跌停比: {latest.get('limit_ratio', 0)*100:.1f}%")

    # 生成信号
    signal = calculator.get_signal(latest["panic_index"])
    print(f"\n💡 操作建议: {signal['reason']}")

    # 检查告警
    alert = AlertManager()
    alerted = alert.check_and_send(
        latest["panic_index"], latest["status"], latest.name.strftime("%Y-%m-%d")
    )
    if alerted:
        print("🚨 已触发告警")

    print("=" * 50)

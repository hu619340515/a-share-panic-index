"""测试告警命令"""

from typing import Any
from alerts.notifier import AlertManager
from utils import error_handler


@error_handler(retry=2, delay=1)
def cmd_alert(args: Any) -> None:
    """测试告警"""
    alert = AlertManager()

    # 模拟各种情况
    test_cases = [
        (15, "贪婪", "2024-01-01"),
        (35, "乐观", "2024-01-02"),
        (65, "恐慌", "2024-01-03"),
        (85, "极度恐慌", "2024-01-04"),
    ]

    print("测试告警系统...")
    for panic, status, date in test_cases:
        print(f"\n测试: 恐慌指数={panic} ({status})")
        alerted = alert.check_and_send(panic, status, date)
        print(f"  结果: {'✅ 已触发' if alerted else '⏭️ 未触发'}")

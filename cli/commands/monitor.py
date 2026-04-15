"""监控模式命令"""

import time
from datetime import datetime
from typing import Any
from utils import error_handler


def cmd_monitor(args: Any) -> None:
    """监控模式"""
    from cli.commands.current import cmd_current

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

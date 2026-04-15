"""配置管理命令"""

import yaml
from typing import Any
from config import get_config
from utils import error_handler


@error_handler(retry=1, delay=0)
def cmd_config(args: Any) -> None:
    """配置管理"""
    config = get_config()

    if args.action == "get":
        value = config.get(args.key)
        print(f"{args.key} = {value}")

    elif args.action == "set":
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

    elif args.action == "list":
        print(yaml.dump(config._config, allow_unicode=True))

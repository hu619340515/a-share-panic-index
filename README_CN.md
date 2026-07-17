# A股恐慌指数监控

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

```bash
python3 scripts/cli.py daily
```

该命令适合 Hermes 和定时任务调用：标准输出为单个JSON对象，日志写入
标准错误和 `logs/daily.log`。兼容的人类可读命令仍为：

```bash
python3 cli.py current
```

## 配置

复制 `config/settings.yaml` 并根据需要修改。

## 更多信息

参见 [README.md](README.md)

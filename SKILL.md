---
name: a-share-panic-index
description: 生成A股市场压力指数结构化日报和当前动态阈值图表，执行交易日判断、增量取数、多数据源回退、数据新鲜度校验与SQLite持久化。用户询问A股市场压力、恐慌程度、当日风险观察信号、自动化日报或需要压力指数图表时使用。
---

# A股市场压力指数

## 固定入口

只调用 `scripts/cli.py`。项目只有动态模型 `2.0`，不要查找、选择或调用其他版本，也不要传入旧参数 `--type`。

在技能目录安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

## 生成日报

```bash
python3 scripts/cli.py daily
```

最长等待 300 秒。标准输出只解析为一个 UTF-8 JSON 对象；标准错误是日志，不要与 JSON 拼接。

可选参数：

```bash
python3 scripts/cli.py daily \
  --date 2026-07-17 \
  --config /path/to/settings.yaml \
  --database /path/to/panic_index.db \
  --force-refresh
```

向用户展示 `result.panic_index`、`result.status`、`result.emotion.percentile`、`result.emotion.trend`、`result.signal.reason`、`as_of_date` 和 `quality_status`。

## 生成图表

画图前先执行一次 `daily`，并使用同一个数据库路径。只有当 `daily` 返回退出码 `0` 且存在可用快照时才继续：

```bash
python3 scripts/cli.py chart \
  --database /path/to/panic_index.db \
  --output reports/panic_index.png \
  --days 252 \
  --dpi 160
```

标准输出仍是单个 JSON 对象。成功时读取 `chart.output` 作为要发送的 PNG；`chart.model_version` 必须为 `2.0`。图表直接读取当前 V4 数据库，不会重新运行旧计算器。

禁止调用已删除的 `cli.commands.chart`、`viz.charts`、`core.calculator`、`history`、`backtest`、`alert` 或 `monitor`。

## 处理退出码

- `0`：成功、非交易日跳过或盘前返回上一交易日快照。
- `2`：参数或配置错误，不要使用旧命令或旧图表参数重试。
- `3`：目标交易日数据过期，等待 `retry.after_seconds` 后重试。
- `4`：四项指标不完整，或图表数据库不是当前模型；先重新运行 `daily`。
- `5`：计算、存储或图表生成失败。
- `6`：未预期错误。

`quality_status=provisional` 表示使用当日备选数据源，可以展示，但要提示后续会自动复核。`result.signal` 只提供风险观察提示，不是买卖建议。

## 数据约定

- 波动率内部单位为年化小数；展示使用 `result.components.volatility_percent`。
- 四项必需指标为波动率、涨跌停比、期货基差和南向资金，缺一项不生成当日指数。
- 情绪等级使用 P05/P25/P75/P95 动态阈值，不使用固定 20/40/60/80 阈值，也不使用滞回机制。
- 日志写入 `logs/daily.log`，按天轮转并默认保留 30 天。

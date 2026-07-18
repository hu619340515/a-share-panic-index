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
  --dpi 160
```

标准输出仍是单个 JSON 对象。只有同时满足以下条件时才发送 `chart.output` 指向的 PNG：

- `status=chart_success`
- `chart.model_version=2.0`
- `chart.layout_version=2-panel-trading-sessions-v1`
- `chart.is_fresh=true`
- 本次命令退出码为 `0`

任一条件不满足时都不要发送目录中已有的旧图片。新版命令会在失败或数据过期时主动删除目标 PNG，避免缓存图被误发。图表直接读取当前 V4 数据库，不会重新运行旧计算器。

非交易日的 `requested_date` 可以晚于 `as_of_date`：例如 2026-07-18 是周六，正确结果应显示运行日为 2026-07-18、数据截至最近交易日 2026-07-17，同时 `chart.is_fresh=true`。这不是数据过期。

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
- 图表固定为两个面板，横轴按实际交易记录等距排列，不为周末和休市日预留空白日期。
- 图表默认显示预期交易日向前一整年的实际交易记录，交易日数量由上交所日历和数据库真实记录决定，不固定为 252、243 或其他常数。
- 动态模型中的 252/756 是阈值计算历史窗口，不是出图天数，不得据此修改图表周期。
- 数据库不足近1年覆盖时返回错误，不补齐、不插值，也不生成虚构记录。
- 日志写入 `logs/daily.log`，按天轮转并默认保留 30 天。

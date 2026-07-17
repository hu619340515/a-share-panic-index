---
name: a-share-panic-index
description: 生成A股市场压力指数结构化日报，执行交易日判断、增量取数、多数据源回退、动态分位情绪分级、数据新鲜度校验和SQLite持久化。用户询问A股市场压力、恐慌程度、当日风险观察信号或需要自动化日报时使用此技能。
---

# A股恐慌指数

## 准备环境

在技能目录执行：

```bash
python3 -m pip install -r scripts/requirements.txt
```

## 生成日报

执行：

```bash
python3 scripts/cli.py daily
```

命令最长允许运行300秒。标准输出只有一个UTF-8 JSON对象；将标准错误视为运行日志，不要与JSON拼接解析。
当前日报JSON的 `schema_version` 为 `2.0`。

可选参数：

```bash
python3 scripts/cli.py daily \
  --date 2026-07-17 \
  --config /path/to/settings.yaml \
  --database /path/to/panic_index.db \
  --force-refresh
```

## 处理结果

- `exit_code=0`：成功、非交易日跳过或盘前返回上一交易日快照。
- `exit_code=2`：参数或配置错误。
- `exit_code=3`：目标交易日数据过期；读取 `retry.after_seconds` 后重试。
- `exit_code=4`：四项必需指标没有完整对齐，不要把结果当作有效日报。
- `exit_code=5`：计算或数据库事务失败。
- `exit_code=6`：未预期错误。
- `quality_status=provisional`：使用了当日备选数据源；可以展示，但需要提示后续会自动复核。
- `result.emotion.classification_quality=warming_up`：历史不足252个交易日，分级使用扩展窗口，可信度低于正式模型。
- `result=null`：没有可展示的有效快照。

向用户展示 `result.panic_index`、`result.status`、`result.emotion.percentile`、`result.emotion.trend`、`result.signal.reason`、`as_of_date` 和 `quality_status`。`result.signal` 只提供观察提示，不是买卖建议。如果 `ok=false` 但 `result` 不为空，可将其作为上一交易日备选快照，同时明确说明数据未更新。

## 数据约定

- 波动率内部单位为年化小数；展示百分比时使用 `result.components.volatility_percent`。
- 四项必需指标为波动率、涨跌停比、期货基差和南向资金。
- 四项指标使用此前最多504个交易日计算历史分位；当天数据不参与当天标准化和阈值。
- 情绪阈值由252日和756日历史分位按30%和70%混合，再使用EMA20平滑。
- 情绪等级为极度平静、偏平静、中性、偏恐慌和极度恐慌，不使用滞回机制。
- `result.emotion.event` 只描述等级变化，消息去重和重复提醒由 Hermes 工作流处理。
- 默认数据库位于 `data_cache/panic_index.db`，首次升级会先备份旧库再重建。
- 日志写入 `logs/daily.log`，按天轮转并保留30天。

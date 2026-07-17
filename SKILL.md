---
name: a-share-panic-index
description: 生成A股恐慌指数120交易日综合PNG图，包含沪深300对比、动态情绪阈值、波动率、涨跌停家数和南向资金。Hermes在用户询问A股市场压力、恐慌程度、近期情绪走势或要求生成恐慌指数图时使用。
---

# A股恐慌指数图

## 安装

在技能目录执行：

```bash
python3 -m pip install -r requirements.txt
```

## 生成图表

执行唯一支持的命令：

```bash
python3 scripts/cli.py chart --output reports/panic_index.png
```

命令最长允许运行300秒。标准输出只有一个UTF-8 JSON对象；标准错误是运行日志，
不要与JSON拼接解析。

可选参数：

```bash
python3 scripts/cli.py chart \
  --days 120 \
  --date 2026-07-17 \
  --config config/settings.yaml \
  --database data_cache/panic_index.db \
  --output reports/panic_index.png \
  --force-refresh
```

## 处理结果

- `exit_code=0` 且 `ok=true`：读取 `chart_path` 并将PNG展示给用户。
- `is_fresh=false`：仍可展示最近有效快照，但必须说明数据未更新到目标交易日。
- `quality_status=provisional`：必须说明当日使用临时数据源，后续运行会复核。
- `trading_days < requested_trading_days`：必须说明历史数据不足，不要声称已有完整120日。
- `exit_code=2`：参数或配置错误。
- `exit_code=3/4`：没有足够的完整指标生成任何图表；根据 `errors` 说明缺失项。
- `exit_code=5`：图表生成或存储失败。

向用户展示图表，并简要说明 `as_of_date`、`panic_index`、`emotion`、
`trading_days` 和数据质量。该图只描述市场压力，不提供买卖建议。

## 图表约定

- 默认展示最近120个上交所交易日。
- 周末和交易所休市日不进入横轴，但每个子图保留真实日期标签。
- 五个面板依次为恐慌指数与沪深300、动态分位阈值、20日年化波动率、
  涨跌停家数、南向资金。
- 四项指标使用此前最多504个交易日计算历史分位；当天数据不参与当天标准化。
- 动态阈值由252日和756日历史分位按30%/70%混合，并使用EMA20平滑。

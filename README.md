# A股恐慌指数图

面向 Hermes 的单用途技能：抓取A股市场数据，计算动态恐慌指数，并生成最近120个
交易日的综合PNG图。

![A股恐慌指数图](docs/images/panic_index_demo.png)

## Hermes 使用

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

生成图表：

```bash
python3 scripts/cli.py chart --output reports/panic_index.png
```

标准输出是单个JSON对象，运行日志写入标准错误和 `logs/chart.log`：

```json
{
  "schema_version": "1.0",
  "ok": true,
  "status": "chart_generated",
  "exit_code": 0,
  "chart_path": ".../reports/panic_index.png",
  "requested_trading_days": 120,
  "trading_days": 120,
  "as_of_date": "2026-07-17",
  "panic_index": 78.6,
  "emotion": "偏恐慌",
  "quality_status": "final",
  "is_fresh": true,
  "refresh_status": "success",
  "errors": []
}
```

Hermes 应解析JSON，在 `ok=true` 时展示 `chart_path`。完整执行规则见
[SKILL.md](SKILL.md)。

## 图表规则

- 默认显示最近120个上交所交易日，`--days` 可调整数量。
- 周末和休市日不会占用横轴，每个子图仍显示真实日期。
- 图表固定包含恐慌指数与沪深300、动态分位阈值、20日年化波动率、
  涨跌停家数和南向资金五个面板。
- 数据库历史不足时自动重建；当日主数据源未更新时使用临时源并标记
  `quality_status=provisional`。
- 中文字体优先读取 `viz.font_path` 或 `PANIC_INDEX_FONT_PATH`，随后自动探测
  微软雅黑、Noto CJK、黑体等系统字体。

## 参数

```bash
python3 scripts/cli.py chart \
  --days 120 \
  --date 2026-07-17 \
  --config config/settings.yaml \
  --database data_cache/panic_index.db \
  --output reports/panic_index.png \
  --force-refresh
```

## 项目结构

```text
├── SKILL.md                         # Hermes 执行说明
├── scripts/cli.py                   # 唯一CLI入口
├── scripts/a_share_panic_index/     # 数据、计算、存储与绘图管线
├── config/settings.yaml             # 可选配置模板
├── tests/                           # 离线测试与数据夹具
└── docs/images/panic_index_demo.png # 示例图
```

## 验证

```bash
python -m unittest discover -s tests -v
```

本项目仅供学习研究，不构成投资建议。

# A股市场压力指数

面向自动化和 Hermes 技能调用的 A 股市场压力指数工具。它不是对海外 VIX 的简单复刻，而是将 A 股波动率、涨跌停结构、股指期货基差和南向资金统一转换为历史分位，形成可持续更新的综合市场压力指标。

项目只保留当前动态模型 **2.0**，提供结构化日报、交易日与数据新鲜度判断、增量多源取数、SQLite 持久化和 PNG 图表。旧固定阈值图表、回测、告警、监控和多套 CLI 版本均已移除，避免自动化工具调用错误版本。

## 适用场景

- Hermes 定时执行并发送 A 股市场压力日报。
- 观察当前压力指数、历史分位、动态等级和变化趋势。
- 生成包含 P05/P25/P75/P95 动态阈值的历史图表。
- 在主数据源延迟时使用备选源生成 provisional 快照，并在后续自动复核。
- 为其他自动化工作流提供稳定的 JSON、退出码和 SQLite 数据接口。

该指数用于描述市场压力状态，不预测指数涨跌，也不直接输出买卖信号。

## 自动化流程

```mermaid
flowchart LR
    A["Hermes 定时调用 daily"] --> B["交易日与新鲜度判断"]
    B --> C["主数据源与备选源增量取数"]
    C --> D["四项指标完整性校验"]
    D --> E["动态分位模型 2.0"]
    E --> F["事务写入 SQLite V4"]
    F --> G["stdout 输出单个 JSON"]
    G --> H["Hermes 解析并发送日报"]
    F --> I["chart 读取数据库生成 PNG"]
```

## 唯一模型

- 四项指标：波动率、涨跌停比、股指期货基差、南向资金。
- 四项指标使用此前最多 504 个交易日计算历史经验分位，当天数据不参与当天标准化。
- 动态阈值由 252 日和 756 日窗口按 30%/70% 混合，并使用 EMA20 平滑。
- 情绪等级固定为：极度平静、偏平静、中性、偏恐慌、极度恐慌。
- 应用版本固定为 `2.0`，数据库结构版本 `4` 仅用于内部迁移，不是可选模型版本。

### 指标含义

| 指标 | 默认权重 | 压力方向 |
|---|---:|---|
| 沪深300年化波动率 | 40% | 波动率越高，市场压力越高 |
| 涨跌停比 | 30% | 跌停占比越高，市场压力越高 |
| 股指期货基差 | 20% | 按历史分位识别期货市场压力 |
| 南向资金 | 10% | 流出越明显，市场压力越高 |

## 安装

需要 Python 3.10 或更高版本：

```bash
python3 -m pip install -r requirements.txt
```

## 命令

项目只支持以下三个命令。

### 1. 生成结构化日报

```bash
python3 scripts/cli.py daily
```

兼容入口：

```bash
python3 cli.py daily
```

可选参数：

```text
--date YYYY-MM-DD
--force-refresh
--config PATH
--database PATH
```

`daily` 的标准输出只有一个 UTF-8 JSON 对象，日志写入标准错误和 `logs/daily.log`。默认总超时为 300 秒。

最小返回示例：

```json
{
  "schema_version": "2.0",
  "ok": true,
  "status": "success",
  "exit_code": 0,
  "as_of_date": "2026-07-17",
  "is_fresh": true,
  "quality_status": "final",
  "result": {
    "panic_index": 49.92,
    "status": "中性",
    "components": {
      "volatility": 0.2805,
      "volatility_percent": 28.05
    }
  },
  "retry": {
    "recommended": false,
    "after_seconds": null
  },
  "errors": []
}
```

### 自动化状态

| 状态 | 行为 |
|---|---|
| `success` / `success_provisional` | 返回目标交易日完整结果 |
| `skipped_non_trading_day` | 非交易日返回最近有效快照，退出码为 `0` |
| `market_not_ready` | 交易日 15:30 前允许返回上一交易日快照 |
| `stale` | 15:30 后当日数据仍不完整，返回旧快照并建议 900 秒后重试 |

### 2. 生成当前动态图表

先运行 `daily` 更新数据库，再执行：

```bash
python3 scripts/cli.py chart --output reports/panic_index.png
```

可选参数：

```text
--database PATH
--config PATH
--output PATH
--days 252
--dpi 160
```

图表直接读取新版 SQLite V4 的 `panic_index` 表，展示市场压力指数、P05/P25/P75/P95 每日动态阈值、历史分位、当前等级和 provisional 标记。命令返回单个 JSON 对象，图片路径位于 `chart.output`。

新版图表固定为两个面板，横轴按实际交易记录等距排列，不会为周末和休市日留下空白位置。非交易日运行时会同时标注运行日和最近交易日，例如在 2026-07-18（周六）运行时，数据截至日期应为 2026-07-17，这是正常的新鲜快照。

自动化程序发送图片前必须检查 `chart.layout_version=2-panel-trading-sessions-v1`、`chart.model_version=2.0` 和 `chart.is_fresh=true`。命令失败或数据过期时不会保留目标路径中的旧 PNG。

不存在 `--type`、`simple`、`comprehensive` 或 `comparison` 等旧版选择；传入旧参数会返回退出码 `2`。

### 3. 人工查看当前值

```bash
python3 scripts/cli.py current
```

该命令用于终端人工查看。Hermes 和其他自动化程序应使用 `daily` 的 JSON。

## 退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 成功、非交易日跳过或盘前返回上一交易日快照 |
| 2 | 参数或配置错误 |
| 3 | 当日数据过期，按 `retry.after_seconds` 重试 |
| 4 | 必需指标不完整，或图表数据库不是当前模型 |
| 5 | 计算、存储或图表生成失败 |
| 6 | 未预期错误 |

## 数据与配置

- 默认数据库：`data_cache/panic_index.db`
- 默认日志：`logs/daily.log`
- 示例配置：`config/settings.yaml`
- 波动率内部保存为年化小数，例如 `0.2805`；展示百分比使用 `28.05%`。
- 备选数据源生成 `provisional` 记录，后续主历史源返回同日期数据时自动覆盖并重新计算。
- `weights.implied_volatility` 仅作为旧配置兼容别名，新配置统一使用 `weights.volatility`。
- 首次运行建立新版数据库；发现旧数据库时会先创建带时间戳的备份，再重建当前结构。
- 正常运行使用 40 个自然日重叠窗口进行增量更新，同时使用完整本地历史计算动态模型。
- 单个数据源最多重试 3 次、默认硬超时 30 秒，整次 `daily` 默认总超时 300 秒。

## 项目结构

```text
cli.py                              兼容包装
scripts/cli.py                      唯一 CLI 实现
scripts/a_share_panic_index/        当前运行包
config/settings.yaml                精简配置示例
SKILL.md                            Hermes 技能说明
tests/                              离线单元与端到端测试
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```

默认测试不访问公网。真实数据源测试仅在设置 `RUN_LIVE_TESTS=1` 时运行。

> 本项目仅供研究和风险观察，不构成投资建议。

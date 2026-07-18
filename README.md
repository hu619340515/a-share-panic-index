# A股市场压力指数

面向自动化和 Hermes 技能调用的 A 股市场压力指数工具。项目只保留当前动态模型 **2.0**，不再提供固定阈值旧图表、回测、告警、监控或多套 CLI 版本。

## 唯一模型

- 四项指标：波动率、涨跌停比、股指期货基差、南向资金。
- 四项指标使用此前最多 504 个交易日计算历史经验分位，当天数据不参与当天标准化。
- 动态阈值由 252 日和 756 日窗口按 30%/70% 混合，并使用 EMA20 平滑。
- 情绪等级固定为：极度平静、偏平静、中性、偏恐慌、极度恐慌。
- 应用版本固定为 `2.0`，数据库结构版本 `4` 仅用于内部迁移，不是可选模型版本。

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

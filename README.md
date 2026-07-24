# A股实时恐慌指数 V3

面向自动化、Hermes 技能和本地 Dashboard 的 A 股市场压力工具。项目只保留 **V3 实时模型**，不再包含旧版计算器、旧版图表或多套命令入口。

V3 同时提供两类结果：

- **盘中实时估计**：交易时段按 1 分钟采集，核心特征按 5 分钟桶计算，始终标记为 `provisional`。
- **收盘正式指数**：只在目标交易日存在完整的 15:00 收盘桶后生成，标记为 `final`。

指数用于市场压力研究，不预测涨跌，也不构成投资建议。

## 模型结构

| 一级组件 | 权重 | 主要信息 |
|---|---:|---|
| 波动与跳跃 | 30% | 跳空、相对昨收跌幅、盘中实现波动、下行波动、振幅、5分钟冲击 |
| 市场宽度 | 30% | 上涨/下跌家数、跌幅超过3%/5%/7%的比例、中位数收益、涨跌停结构 |
| 衍生品 | 25% | IF近月和次月年化基差、期限结构、基差扩张、QVIX |
| 流动性 | 15% | 预计全天成交额缺口、5分钟非流动性、下跌放量和成交加速压力 |

四组件使用广义均值 `p=1.5` 合成。等级固定为：极度平静、偏平静、中性、偏恐慌、极度恐慌。

### 三种参考模式

- `structural_bootstrap`：同时间桶历史不足 20 个交易日，使用固定金融锚点。
- `self_calibrating`：20～59 日，逐步加入自采同时间历史。
- `same_time_history`：60 日起以自采同时间历史为主要参考。

成交额日内曲线优先使用 510300、159919、510050、510500 等真实 5 分钟数据的中位数组合。取不到真实代理曲线时才使用结构化 bootstrap，并在 `provisional_reasons` 中明确标记；不会把 bootstrap 冒充市场实测数据。自采全市场曲线在 20 日后开始混合，60 日权重达到 50%，120 日达到 75%。

## 数据与可靠性

实时主备源按配置依次切换：

| 语义 | 默认顺序 |
|---|---|
| 沪深300实时行情 | mootdx → 腾讯 → 东方财富 → 新浪 |
| 全市场宽度 | 东方财富 → 新浪 → mootdx → 腾讯 |
| 涨跌停 | 东方财富 → 选股宝 → 全市场涨跌幅显式估算 |
| IF明确合约 | 新浪 → AKShare中金所数据；mootdx扩展市场仅保留能力探测 |
| QVIX | 300股指QVIX → 300ETF QVIX |
| ETF代理曲线 | BaoStock → mootdx → 新浪 → 腾讯 → 东方财富 |

所有实时值都保存来源、来源时间、接收时间、质量标记和交叉来源比较。连接错误、超时和可恢复 HTTP 错误最多重试 3 次；空数组、缺字段、单位错误和语义错误立即切换备选源。单来源硬超时和整轮总超时同时生效，失败事件会独立写入 Provider 健康表，不会产生残缺指数记录。

免费网页接口可能限频、变更或暂时不可用。运行 `sources probe` 查看本机和当前网络环境的实际能力，不要把测试夹具结果当成真实网络验证。

## 安装

需要 Python 3.10 或更高版本：

```bash
python -m pip install -r requirements.txt
```

## CLI

唯一实现入口位于 `scripts/cli.py`，根目录 `cli.py` 只是兼容包装。

```bash
python scripts/cli.py realtime
python scripts/cli.py realtime --watch --interval 60
python scripts/cli.py current
python scripts/cli.py daily
python scripts/cli.py finalize
python scripts/cli.py chart --type intraday --output reports/intraday.png
python scripts/cli.py chart --type daily --output reports/daily.png
python scripts/cli.py rebuild
python scripts/cli.py validate --mode realtime --output reports/validation
python scripts/cli.py replay --date 2026-07-24 --speed 20
python scripts/cli.py sources probe --output reports/source_probe.json
python scripts/cli.py sources status
python scripts/cli.py serve --host 127.0.0.1 --port 8000
```

常用公共参数：

```text
--config PATH
--database PATH
```

`realtime`、`daily` 和 `finalize` 还支持 `--date YYYY-MM-DD`；测试时可通过 `--fixture` 使用本地固定数据，生产运行不要传该参数。

### JSON 和退出码

单次命令的 stdout 只输出一个 UTF-8 JSON 对象，日志进入 stderr 和 `logs/daily.log`。watch 模式每轮输出一行 JSON。

| 退出码 | 含义 |
|---:|---|
| 0 | 成功、非交易日跳过、盘前或午休冻结 |
| 2 | 参数或配置错误 |
| 3 | 核心来源过期或时间偏差过大 |
| 4 | 必需字段、完整收盘桶或可用特征权重不足 |
| 5 | 计算、存储、验证或图表失败 |
| 6 | 未预期错误 |

关键输出字段包括 `realtime_panic_index_raw`、`realtime_panic_index`、四组件、底层特征、`confidence`、`coverage`、`reference_mode`、`stale_sources` 和 `provisional_reasons`。

## 图表规则

- 盘中图只读取数据库中目标交易日的真实快照。
- 日线图使用最近一个自然年的窗口，只绘制窗口内实际存在的正式记录。
- 不为周末、休市日或缺失日期补点，不插值，不制造 252 条或任何固定数量的数据。
- 若数据库实际历史不足一年，仍绘制已有真实记录和可见数据点，并在图内及 JSON 中标明实际覆盖范围；JSON 返回 `coverage_complete=false`、实际起止日期和 `missing_dates_filled=false`。
- 命令开始时会删除同名旧输出；失败时不会把历史缓存图片当作本次结果。

V3 不迁移旧模型指数，因此首次上线时日线历史可能只有当天。`rebuild` 只会使用数据库已保存的真实收盘快照，或调用者明确提供且可审计的真实历史夹具；它不会联网拼凑缺失指标，也不会合成一年的指数。随着每日收盘固化，图表会自然积累到近一年覆盖。

## 数据库

SQLite V5 使用 WAL、`synchronous=NORMAL` 和 5 秒 busy timeout。旧结构首次打开时先复制到带时间戳的备份目录，再创建 V5 数据库；旧指数不会复制进 V3。

主要表：

```text
daily_raw_metrics
daily_features
daily_panic_index
realtime_raw_metrics
realtime_features
realtime_panic_index
intraday_aggregate_snapshots
intraday_reference_curves
provider_health
provider_probe_results
metadata
```

实时原始聚合、特征、指数和 Provider 健康成功事件在同一事务写入。任一步骤失败都会回滚；失败的数据源健康事件单独记录。

## Dashboard 和 API

启动：

```bash
python scripts/cli.py serve --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。页面展示实时值、raw 值、上一正式收盘、5/15/30 分钟变化、四组件、QVIX、IF合约和基差、上涨/下跌家数、涨跌停、累计成交额、预计全天成交额、来源与质量状态。

API：

```text
GET /api/v1/realtime
GET /api/v1/realtime/history
GET /api/v1/daily/latest
GET /api/v1/daily/history
GET /api/v1/sources
GET /api/v1/reference
GET /healthz
```

## 验证与测试

默认测试完全离线：

```bash
python -m unittest discover -s tests -v
```

真实网络测试仅在显式设置 `RUN_LIVE_TESTS=1` 时运行。数据源探测会生成中文表头的：

```text
reports/source_probe.json
reports/source_coverage.csv
reports/source_disagreements.csv
```

`replay` 和图表命令只读取已保存的真实记录，不访问公网。

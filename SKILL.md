---
name: a-share-panic-index
description: 采集A股盘中实时恐慌指数、生成收盘正式指数与近一年真实记录图表，并返回适合Hermes解析的单个JSON结果。用户询问A股恐慌程度、市场压力、实时风险、日报、图表或数据源状态时使用。
---

# A股实时恐慌指数 V3

## 唯一入口

始终调用：

```bash
python3 scripts/cli.py <command>
```

根目录 `cli.py` 仅是兼容包装。不要搜索、选择或执行其他版本，不要调用已删除的旧模块。Hermes 运行超时设置为 300 秒。

## 输出处理

- 单次命令只把 stdout 解析为一个 UTF-8 JSON 对象。
- stderr 和 `logs/daily.log` 是日志，不要与 stdout 拼接。
- 只有进程退出码为 `0` 且 JSON 的 `ok=true` 时才视为命令成功。
- `realtime` 结果始终是盘中估计：`snapshot_type=realtime`、`finality=provisional`。
- `daily` 或 `finalize` 只有在完整收盘桶存在时才返回：`snapshot_type=daily`、`finality=final`。

## 实时结果

单次采集：

```bash
python3 scripts/cli.py realtime
```

持续采集：

```bash
python3 scripts/cli.py realtime --watch --interval 60
```

向用户展示：

- `result.realtime_panic_index`
- `result.realtime_panic_index_raw`
- `result.level`
- `result.components`
- `result.confidence`
- `result.coverage`
- `result.reference_mode`
- `result.provisional_reasons`
- `as_of_date` 和 `generated_at`

明确说明“盘中实时估计，不是收盘正式值”。

## 收盘日报

15:10 后执行：

```bash
python3 scripts/cli.py daily
```

也可使用同义命令：

```bash
python3 scripts/cli.py finalize
```

指定日期：

```bash
python3 scripts/cli.py daily --date 2026-07-24
```

如果返回 `market_not_ready`、`skipped_non_trading_day` 或非零退出码，不得把上一交易日结果描述成当天正式值。

## 生成图表

盘中图：

```bash
python3 scripts/cli.py chart --type intraday --output reports/intraday.png
```

近一年收盘图：

```bash
python3 scripts/cli.py chart --type daily --output reports/daily.png
```

只发送本次 JSON 的 `result.output` 指向的图片，并同时检查：

- `status=chart_success`
- 进程退出码为 `0`
- 输出文件本次确实存在
- `result.type` 与请求类型一致

不得扫描目录后发送旧图片。日线图采用最近一个自然年窗口，但只绘制数据库真实正式记录；不补周末、休市日或缺失日期，不插值，不制造固定 252 条数据。历史不足一年时查看 `result.coverage_complete`、`result.start_date` 和 `result.end_date`，并向用户说明实际覆盖较短；不得把“近一年窗口”描述成“已经拥有一年数据”。

## Dashboard

```bash
python3 scripts/cli.py serve --host 127.0.0.1 --port 8000
```

本机地址：`http://127.0.0.1:8000`。

## 数据源诊断

真实探测：

```bash
python3 scripts/cli.py sources probe --output reports/source_probe.json
python3 scripts/cli.py sources status
```

只有未传 `--fixture` 的结果才能称为真实网络探测。免费接口可能变化，失败时根据 `errors`、Provider 健康状态和退出码说明，不得虚构行情数据。

## 回放与验证

```bash
python3 scripts/cli.py replay --date 2026-07-24 --speed 20
python3 scripts/cli.py validate --mode realtime --output reports/validation
python3 scripts/cli.py validate --mode daily --output reports/validation
```

`replay`、`chart` 和 `current` 只读取数据库，不访问公网。

## 退出码

- `0`：成功、非交易日跳过、盘前或午休冻结。
- `2`：参数或配置错误；修正命令，不要改用旧入口。
- `3`：核心数据过期；根据 `retry.after_seconds` 重试。
- `4`：必需数据、收盘桶或特征覆盖不足；不要生成正式结论。
- `5`：计算、存储、验证或图表失败。
- `6`：未预期错误。

## 数据原则

- 不使用 0、50、上一值或随机数填补失败来源。
- QVIX 缺失时保留 IF 组件并降低置信度，不填假 QVIX。
- ETF 代理曲线取不到时明确进入 `structural_bootstrap`。
- `confidence` 表示结果可信度，`coverage` 表示可用底层特征权重，两者不可互换。
- 结果只用于市场压力观察，不构成买卖建议。

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

## 动态情绪模型

- 四项指标分别使用此前最多504个交易日计算经验分位，禁止使用当天和未来数据。
- 恐慌指数继续使用40%波动率、30%涨跌停比、20%期货基差和10%南向资金权重。
- 情绪阈值由252日短周期和756日长周期按30%/70%混合，并使用EMA20平滑。
- 分级采用P05/P25/P75/P95，对应极度平静、偏平静、中性、偏恐慌和极度恐慌。
- 分级无滞回；等级变化通过 `result.emotion.event` 输出，通知频率由Hermes处理。
- `result.signal` 只输出观察信号，不直接输出买入或卖出建议。

首次V2运行会备份旧数据库，并重建约1100个自然日数据。历史不足252个交易日时，`classification_quality` 为 `warming_up`。

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 更多信息

参见 [README.md](README.md)

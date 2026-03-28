---
name: a-share-panic-index
description: A股恐慌指数监控技能（重构版）。模块化架构，支持SQLite数据库、配置管理、CLI工具、回测功能、告警推送。
read_when:
  - 用户需要A股恐慌指数
  - 用户需要市场情绪监控
  - 用户需要量化分析工具
metadata:
  version: 2.0.0
  author: 旺大神
  requires:
    - python3
    - akshare
    - pandas
    - numpy
    - matplotlib
    - pyyaml
    - requests
---

# A股恐慌指数监控技能 v2.0

模块化重构版本，支持完整的数据获取、计算、存储、可视化、告警和回测功能。

## 项目结构

```
a-share-panic-index/
├── config/                 # 配置管理
│   ├── settings.yaml       # 配置文件
│   └── __init__.py         # Config类
├── core/                   # 核心算法
│   ├── calculator.py       # 恐慌指数计算
│   └── backtest.py         # 回测引擎
├── data/                   # 数据层
│   ├── cache.py            # 缓存管理（SQLite/Pickle）
│   └── database.py         # SQLite数据库
├── fetchers/               # 数据获取
│   ├── base.py             # 获取器基类
│   ├── index.py            # 指数数据
│   ├── limit_up.py         # 涨跌停数据
│   ├── futures.py          # 期货数据
│   └── fund_flow.py        # 资金流向
├── viz/                    # 可视化
│   └── charts.py           # 图表生成
├── alerts/                 # 告警推送
│   └── notifier.py         # 告警管理
├── tests/                  # 测试
│   └── test_all.py         # 单元测试
├── cli.py                  # CLI主入口
└── SKILL.md                # 本文档
```

## 快速开始

### 1. 安装依赖

```bash
pip install akshare pandas numpy matplotlib pyyaml requests
```

### 2. CLI工具使用

```bash
# 查看当前恐慌指数
cd ~/.openclaw/workspace/skills/a-share-panic-index
python3 cli.py current

# 查看历史数据
python3 cli.py history --days 30

# 生成图表
python3 cli.py chart --type comprehensive --output chart.png

# 运行回测
python3 cli.py backtest

# 配置管理
python3 cli.py config get weights.implied_volatility
python3 cli.py config set weights.implied_volatility 0.45

# 监控模式（每30分钟自动检查）
python3 cli.py monitor
```

### 3. Python API 使用

```python
from core.calculator import PanicIndexCalculator
from data.database import Database
from viz.charts import Visualizer

# 获取最新数据
db = Database()
df = db.get_latest(30)

# 计算恐慌指数
calc = PanicIndexCalculator()
latest = df.iloc[-1]
signal = calc.get_signal(latest['panic_index'])

# 生成图表
viz = Visualizer()
viz.plot_simple(df, 'output.png')
```

## 配置说明

编辑 `config/settings.yaml`:

```yaml
# 权重配置
weights:
  implied_volatility: 0.40      # 波动率权重
  limit_up_down_ratio: 0.30     # 涨跌停比权重
  futures_premium: 0.20         # 期货贴水权重
  southbound_flow: 0.10         # 南向资金权重

# 情绪阈值
thresholds:
  greedy: 20           # 贪婪
  optimistic: 40       # 乐观
  neutral: 60          # 中性
  panic: 80            # 恐慌
  extreme_panic: 100   # 极度恐慌

# 缓存配置
cache:
  type: "sqlite"       # sqlite / pickle
  sqlite_path: "./data_cache/panic_index.db"
  max_age_hours: 6

# 告警配置
alerts:
  enabled: true
  feishu:
    enabled: false
    webhook_url: "your-webhook-url"
  rules:
    extreme_panic:
      condition: ">= 80"
      message: "极度恐慌！可能是买入时机"
```

## 数据存储

支持两种存储方式：

### SQLite（推荐）
- 数据库文件: `./data_cache/panic_index.db`
- 表结构:
  - `panic_index`: 恐慌指数历史数据
  - `signals`: 交易信号记录
  - `backtest_results`: 回测结果

### Pickle（向后兼容）
- 缓存文件: `./data_cache/panic_index_cache.pkl`

## 回测策略

支持多种回测策略：

- `extreme_panic_buy`: 恐慌>80买入，<20卖出
- `panic_buy`: 恐慌>60买入，<40卖出
- `contrarian`: 反向策略（贪婪买入，恐慌卖出）

回测指标包括：总收益、年化收益、最大回撤、夏普比率、胜率等。

## 告警推送

支持飞书机器人推送，可配置告警规则：

- 极度恐慌告警（>=80）
- 恐慌告警（>=60）
- 贪婪告警（<=20）

## 测试

```bash
# 运行单元测试
python3 tests/test_all.py
```

## 更新日志

### v2.0.0 (2026-03-28)
- ✅ 模块化架构重构
- ✅ SQLite数据库支持
- ✅ YAML配置文件
- ✅ CLI命令行工具
- ✅ 回测功能
- ✅ 告警推送
- ✅ 单元测试

### v1.0.0 (2026-03-26)
- 初始版本
- 单文件实现

## 许可证

MIT License

## 作者

旺大神

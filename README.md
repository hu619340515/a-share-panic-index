# A股恐慌指数监控 (A-Share Panic Index)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> 专业的A股市场恐慌/贪婪指数计算与监控工具，支持多维度数据分析、历史回测和告警推送。

![Panic Index Chart](docs/images/panic_index_demo.png)

## ✨ 功能特性

### 核心功能
- 📊 **恐慌指数计算** - 基于波动率、涨跌停比、期货贴水、南向资金的多维度指数
- 📈 **实时监控** - 支持盘中数据获取和历史趋势分析
- 🧪 **策略回测** - 验证恐慌指数对投资决策的有效性
- 🚨 **智能告警** - 飞书/微信推送，关键点位自动提醒
- 💾 **数据存储** - SQLite数据库，支持增量更新和历史查询

### 技术指标
| 指标 | 权重 | 说明 |
|-----|-----|-----|
| 隐含波动率 | 40% | 沪深300指数20日历史波动率 |
| 涨跌停比 | 30% | 跌停家数/涨跌停总数 |
| 期货贴水 | 20% | 股指期货与现货基差 |
| 南向资金 | 10% | 港股通资金流向 |

### 情绪分级
```
0-20 分: 🟢 贪婪 (极度乐观，注意风险)
20-40分: 🟡 乐观 (积极情绪，可持有)
40-60分: ⚪ 中性 (观望为主)
60-80分: 🟠 恐慌 (开始关注机会)
80-100分: 🔴 极度恐慌 (可能是买入时机)
```

## 🚀 快速开始

### 安装依赖

```bash
pip install akshare pandas numpy matplotlib pyyaml requests
```

### 使用CLI工具

```bash
# 进入项目目录
cd a-share-panic-index

# 获取当前恐慌指数
python3 cli.py current

# 查看历史数据
python3 cli.py history --days 30

# 生成图表
python3 cli.py chart --type comprehensive --output chart.png

# 运行回测
python3 cli.py backtest

# 监控模式
python3 cli.py monitor
```

### Python API

```python
from core.calculator import PanicIndexCalculator
from data.database import Database
from viz.charts import Visualizer

# 获取数据
db = Database()
df = db.get_latest(30)

# 计算恐慌指数
calc = PanicIndexCalculator()
latest = df.iloc[-1]
signal = calc.get_signal(latest['panic_index'])

# 生成图表
viz = Visualizer()
viz.plot_comprehensive(df, raw_data, 'output.png')
```

## 📁 项目结构

```
a-share-panic-index/
├── config/                 # 配置管理
│   ├── settings.yaml       # 配置文件
│   └── __init__.py         # Config类
├── core/                   # 核心算法
│   ├── calculator.py       # 恐慌指数计算
│   └── backtest.py         # 回测引擎
├── data/                   # 数据层
│   ├── cache.py            # 缓存管理
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
├── tests/                  # 单元测试
│   └── test_all.py
├── cli.py                  # CLI主入口
├── README.md               # 本文档
└── LICENSE                 # MIT许可证
```

## ⚙️ 配置说明

编辑 `config/settings.yaml`:

```yaml
# 权重配置
weights:
  implied_volatility: 0.40
  limit_up_down_ratio: 0.30
  futures_premium: 0.20
  southbound_flow: 0.10

# 情绪阈值
thresholds:
  greedy: 20
  optimistic: 40
  neutral: 60
  panic: 80

# 告警配置
alerts:
  enabled: true
  feishu:
    enabled: false
    webhook_url: "your-webhook-url"
```

## 📊 数据源

- **指数数据**: [akshare](https://www.akshare.xyz/) (新浪财经)
- **涨跌停数据**: 金融界API
- **期货数据**: 新浪财经
- **资金流向**: 东方财富

## 🧪 测试

```bash
# 运行单元测试
python3 tests/test_all.py
```

测试覆盖:
- 恐慌指数计算
- 标准化函数
- 情绪状态判断
- 回测引擎
- 配置管理

## 📈 回测策略

支持策略:
- `extreme_panic_buy`: 恐慌>80买入，<20卖出
- `panic_buy`: 恐慌>60买入，<40卖出  
- `contrarian`: 反向策略

回测指标:
- 总收益率 / 年化收益率
- 最大回撤
- 夏普比率
- 胜率

## 🔔 告警规则

```yaml
alerts:
  rules:
    extreme_panic:
      condition: ">= 80"
      message: "🔴 极度恐慌！可能是买入时机"
    
    panic:
      condition: ">= 60"
      message: "🟠 恐慌情绪，开始关注机会"
    
    greedy:
      condition: "<= 20"
      message: "🟢 极度贪婪，注意风险"
```

## 📝 更新日志

### v2.0.0 (2026-03-28)
- ✅ 模块化架构重构
- ✅ SQLite数据库支持
- ✅ YAML配置管理
- ✅ CLI命令行工具
- ✅ 策略回测功能
- ✅ 告警推送系统
- ✅ 单元测试覆盖

### v1.0.0 (2026-03-26)
- 初始版本
- 基础恐慌指数计算

## 🤝 贡献指南

欢迎提交Issue和PR！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'Add amazing'`)
4. 推送分支 (`git push origin feature/amazing`)
5. 创建 Pull Request

## 📄 许可证

[MIT License](LICENSE)

## 👤 作者

**旺大神** - [GitHub](https://github.com/yourname)

---

> ⚠️ **免责声明**: 本工具仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。

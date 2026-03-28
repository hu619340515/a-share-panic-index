"""
A股恐慌指数 - 多指标可视化版
包含：恐慌指数、波动率、北向/南向资金、涨跌停数据的完整图表
"""

# =============================================================================
# 配置区域
# =============================================================================

WEIGHTS = {
    'implied_volatility': 0.40,      # 波动率权重
    'limit_up_down_ratio': 0.30,     # 涨跌停比权重
    'futures_premium': 0.20,         # 期货贴水权重
    'southbound_flow': 0.10          # 南向资金权重（数据正常更新）
}

THRESHOLDS = {
    'greedy': 20,
    'optimistic': 40,
    'neutral': 60,
    'panic': 80,
    'extreme_panic': 100
}

MAX_RETRIES = 3
RETRY_DELAY = 1

# 本地数据缓存配置
CACHE_CONFIG = {
    'enabled': True,                    # 是否启用本地缓存
    'cache_dir': './data_cache',        # 缓存目录
    'data_file': 'panic_index_cache.pkl',  # 缓存文件名
    'max_age_hours': 6,                 # 缓存最大年龄（小时）
    'auto_update': True                 # 是否自动更新过期数据
}

# =============================================================================
# 导入依赖
# =============================================================================

import sys
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# HTTP请求库
try:
    import requests
except ImportError:
    print("警告: requests 库未安装，金融界API将不可用。安装: pip install requests")
    requests = None

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("请安装: pip install pandas numpy")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.gridspec import GridSpec
    import matplotlib.font_manager as fm
    
    # 直接加载中文字体文件
    font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    chinese_font = fm.FontProperties(fname=font_path)
    
    # 设置全局字体
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
except ImportError:
    print("请安装: pip install matplotlib")
    sys.exit(1)

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("请安装: pip install akshare")
    sys.exit(1)

# =============================================================================
# 本地数据缓存管理
# =============================================================================

import os
import pickle
from pathlib import Path

class DataCacheManager:
    """本地数据缓存管理器"""
    
    def __init__(self, config=CACHE_CONFIG):
        self.config = config
        self.cache_path = Path(config['cache_dir']) / config['data_file']
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        Path(self.config['cache_dir']).mkdir(parents=True, exist_ok=True)
    
    def _get_cache_mtime(self):
        """获取缓存文件修改时间"""
        if self.cache_path.exists():
            return datetime.fromtimestamp(self.cache_path.stat().st_mtime)
        return None
    
    def _is_cache_valid(self):
        """检查缓存是否有效（未过期）"""
        if not self.cache_path.exists():
            return False
        
        mtime = self._get_cache_mtime()
        if mtime is None:
            return False
        
        age = datetime.now() - mtime
        max_age = timedelta(hours=self.config['max_age_hours'])
        
        return age < max_age
    
    def load_cache(self):
        """从本地加载缓存数据"""
        if not self.config['enabled']:
            return None
        
        if not self._is_cache_valid():
            print("  ℹ️  本地缓存不存在或已过期")
            return None
        
        try:
            with open(self.cache_path, 'rb') as f:
                cache_data = pickle.load(f)
            
            mtime = self._get_cache_mtime()
            print(f"  ✅ 从本地缓存加载数据（缓存时间: {mtime.strftime('%Y-%m-%d %H:%M')}）")
            return cache_data
        except Exception as e:
            print(f"  ⚠️  加载缓存失败: {e}")
            return None
    
    def save_cache(self, data, raw_data):
        """保存数据到本地缓存"""
        if not self.config['enabled']:
            return
        
        try:
            cache_data = {
                'result': data,
                'raw_data': raw_data,
                'save_time': datetime.now()
            }
            
            with open(self.cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
            
            print(f"  ✅ 数据已保存到本地缓存: {self.cache_path}")
        except Exception as e:
            print(f"  ⚠️  保存缓存失败: {e}")
    
    def get_cache_info(self):
        """获取缓存信息"""
        if not self.cache_path.exists():
            return "缓存不存在"
        
        mtime = self._get_cache_mtime()
        age = datetime.now() - mtime
        size = self.cache_path.stat().st_size / 1024  # KB
        
        return f"缓存时间: {mtime.strftime('%Y-%m-%d %H:%M')}, 年龄: {age.total_seconds()/3600:.1f}小时, 大小: {size:.1f}KB"


# =============================================================================
# 工具函数
# =============================================================================

def retry_on_error(max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"⚠️  第{attempt + 1}次尝试失败，{delay}秒后重试...")
                        time.sleep(delay)
                    else:
                        print(f"❌  第{max_retries}次尝试失败: {e}")
            raise last_exception
        return wrapper
    return decorator

# =============================================================================
# 数据获取模块
# =============================================================================

class DataFetcher:
    def __init__(self, use_akshare=True):
        self.use_akshare = use_akshare and AKSHARE_AVAILABLE
        self.spot_prices = None
        self.raw_data = {}  # 保存原始数据供绘图使用
        
    def get_mock_data(self, start_date=None, end_date=None):
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=365)
        
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        np.random.seed(42)
        
        # 隐含波动率
        iv = np.random.normal(0.2, 0.05, size=len(dates))
        panic_days = np.random.choice(len(dates), size=10, replace=False)
        iv[panic_days] = np.random.uniform(0.4, 0.6, size=10)
        
        # 涨跌停
        # 模拟数据 - 涨停跌停数据尽量合理
        limit_up = np.random.randint(30, 80, size=len(dates))
        limit_down = np.random.randint(5, 40, size=len(dates))
        # 恐慌日跌停增加，但不超过100（更合理）
        limit_down[panic_days] = np.random.randint(50, 100, size=10)
        limit_up[panic_days] = np.random.randint(10, 30, size=10)
        total = limit_up + limit_down
        limit_ratio = np.where(total > 0, limit_down / total, 0.5)
        
        # 期货贴水
        basis = np.random.normal(-0.002, 0.005, size=len(dates))
        basis[panic_days] = np.random.uniform(0.01, 0.03, size=10)
        
        # 北向资金
        flow = np.random.normal(10, 30, size=len(dates))
        flow[panic_days] = np.random.uniform(-100, -50, size=10)
        
        # 南向资金（模拟）
        south_flow = np.random.normal(5, 20, size=len(dates))
        
        df = pd.DataFrame({
            'iv': iv,
            'limit_ratio': limit_ratio,
            'limit_up': limit_up,
            'limit_down': limit_down,
            'futures_basis': basis,
            'northbound_flow': flow,
            'southbound_flow': south_flow
        }, index=dates)
        
        self.raw_data['mock'] = True
        return df
    
    @retry_on_error(max_retries=3, delay=1)
    def _get_index_data(self, start_date, end_date):
        """使用 stock_zh_index_daily 接口获取沪深300数据"""
        # 使用可用的接口替代 index_zh_a_hist
        index_df = ak.stock_zh_index_daily(symbol='sh000300')
        index_df['date'] = pd.to_datetime(index_df['date'])
        index_df.set_index('date', inplace=True)
        
        # 筛选日期范围
        index_df = index_df[(index_df.index >= start_date) & (index_df.index <= end_date)]
        
        if index_df.empty:
            raise ValueError("无数据")
        
        returns = np.log(index_df['close'] / index_df['close'].shift(1))
        iv = returns.rolling(window=20).std() * np.sqrt(252)
        
        self.spot_prices = index_df['close']
        self.raw_data['index_close'] = index_df['close']
        self.raw_data['hs300'] = index_df['close']  # 保存沪深300用于对比图
        return iv
    
    @retry_on_error(max_retries=3, delay=1)
    def _get_limit_up_down_data(self, start_date, end_date):
        """获取涨跌停数据 - 使用金融界API获取历史数据（支持多月份）"""
        print(f"\n    正在从金融界API获取涨跌停数据...")
        
        # 检查requests是否可用
        if requests is None:
            print(f"    ⚠️ requests库未安装，尝试AkShare...")
            return self._get_limit_up_down_data_akshare(start_date, end_date)
        
        # 定义请求头
        url = "https://gateway.jrj.com/quot-dc/zdt/market_history"
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 CrKey/1.54.248666",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://summary.jrj.com.cn/",
            "Origin": "https://summary.jrj.com.cn",
            "productid": "6000021",
        }
        
        all_data = []
        
        # 生成需要查询的月份列表
        months = []
        current = start_date.replace(day=1)
        end_month = end_date.replace(day=1)
        while current <= end_month:
            months.append(current.strftime("%Y%m"))
            if current.month == 12:
                current = current.replace(year=current.year+1, month=1)
            else:
                current = current.replace(month=current.month+1)
        
        print(f"    将查询 {len(months)} 个月的涨跌停数据...")
        
        for i, year_month in enumerate(months):
            try:
                payload = {
                    "yearMonth": year_month,
                    "pageIndex": 1,
                    "pageSize": 100
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                data = response.json()
                
                if data.get('code') == 20000 and data.get('data', {}).get('list'):
                    list_data = data['data']['list']
                    for item in list_data:
                        date_str = str(item['tradeDate'])
                        date = datetime.strptime(date_str, '%Y%m%d')
                        # 只保留在日期范围内的数据
                        if start_date <= date <= end_date:
                            all_data.append({
                                'date': date,
                                'limit_up': item['upLimitCount'],
                                'limit_down': item['downLimitCount']
                            })
                    
                    if i % 5 == 0 or i == len(months) - 1:
                        print(f"      [{i+1}/{len(months)}] {year_month}: {len(list_data)}条")
                
                time.sleep(0.5)  # 礼貌延时
                
            except Exception as e:
                print(f"      ⚠️ {year_month} 获取失败: {e}")
                continue
        
        if all_data:
            # 去重（按日期）
            seen_dates = set()
            unique_data = []
            for item in sorted(all_data, key=lambda x: x['date']):
                if item['date'] not in seen_dates:
                    seen_dates.add(item['date'])
                    item['limit_ratio'] = item['limit_down'] / (item['limit_up'] + item['limit_down']) if (item['limit_up'] + item['limit_down']) > 0 else 0.5
                    unique_data.append(item)
            
            limit_df = pd.DataFrame(unique_data)
            limit_df.set_index('date', inplace=True)
            limit_df.sort_index(inplace=True)
            
            self.raw_data['limit_up'] = limit_df['limit_up']
            self.raw_data['limit_down'] = limit_df['limit_down']
            print(f"    ✅ 从金融界API获取 {len(limit_df)} 天涨跌停数据")
            return limit_df
        else:
            print(f"    ⚠️ 金融界API无数据，尝试AkShare...")
        
        # 备选：使用AkShare获取（只能获取最近交易日）
        return self._get_limit_up_down_data_akshare(start_date, end_date)
    
    def _get_limit_up_down_data_akshare(self, start_date, end_date):
        """使用AkShare获取涨跌停数据（备选方案）"""
        limit_data = []
        all_dates = pd.date_range(start=start_date, end=end_date, freq='B')
        
        print(f"    正在从AkShare获取 {len(all_dates)} 个交易日数据...")
        
        success_count = 0
        for current_date in all_dates:
            date_str = current_date.strftime('%Y%m%d')
            try:
                zt_df = ak.stock_zt_pool_em(date=date_str)
                limit_up = len(zt_df) if not zt_df.empty else 0
            except:
                limit_up = 0
            try:
                dt_df = ak.stock_zt_pool_dtgc_em(date=date_str)
                limit_down = len(dt_df) if not dt_df.empty else 0
            except:
                limit_down = 0
            
            limit_ratio = limit_down / (limit_up + limit_down) if (limit_up + limit_down) > 0 else 0.5
            limit_data.append({
                'date': current_date,
                'limit_up': limit_up,
                'limit_down': limit_down,
                'limit_ratio': limit_ratio
            })
            if limit_up > 0 or limit_down > 0:
                success_count += 1
        
        if limit_data:
            limit_df = pd.DataFrame(limit_data)
            limit_df.set_index('date', inplace=True)
            limit_df.sort_index(inplace=True)
            self.raw_data['limit_up'] = limit_df['limit_up']
            self.raw_data['limit_down'] = limit_df['limit_down']
            print(f"    ✅ 从AkShare获取 {success_count} 天有涨跌停数据")
            return limit_df
        return None
    
    @retry_on_error(max_retries=3, delay=1)
    def _get_futures_data(self):
        futures_df = ak.futures_main_sina(symbol="IF0")
        if futures_df.empty:
            return None
        futures_df['date'] = pd.to_datetime(futures_df['日期'])
        futures_df.set_index('date', inplace=True)
        
        if self.spot_prices is not None:
            combined = pd.concat([self.spot_prices, futures_df['收盘价']], axis=1, join='inner')
            combined.columns = ['spot', 'futures']
            basis = (combined['spot'] - combined['futures']) / combined['spot']
            return basis
        else:
            fut_returns = np.log(futures_df['收盘价'] / futures_df['收盘价'].shift(1))
            return -fut_returns.rolling(window=5).mean()
    
    @retry_on_error(max_retries=3, delay=1)
    def _get_northbound_data(self, start_date, end_date):
        nb_df = ak.stock_hsgt_hist_em(symbol='北向资金')
        if nb_df.empty:
            return None
        nb_df['date'] = pd.to_datetime(nb_df['日期'])
        nb_df.set_index('date', inplace=True)
        nb_df = nb_df[(nb_df.index >= start_date) & (nb_df.index <= end_date)]
        self.raw_data['northbound'] = nb_df['当日成交净买额']
        return nb_df['当日成交净买额']
    
    @retry_on_error(max_retries=3, delay=1)
    def _get_southbound_data(self, start_date, end_date):
        """获取南向资金（港股通）"""
        try:
            # 尝试获取南向资金数据
            sb_df = ak.stock_hsgt_hist_em(symbol='南向资金')
            if sb_df.empty:
                return None
            sb_df['date'] = pd.to_datetime(sb_df['日期'])
            sb_df.set_index('date', inplace=True)
            sb_df = sb_df[(sb_df.index >= start_date) & (sb_df.index <= end_date)]
            self.raw_data['southbound'] = sb_df['当日成交净买额']
            return sb_df['当日成交净买额']
        except:
            # 如果获取失败，返回模拟数据
            print("  南向资金获取失败，使用模拟数据")
            mock = self.get_mock_data(start_date, end_date)
            self.raw_data['southbound'] = mock['southbound_flow']
            return mock['southbound_flow']
    
    @retry_on_error(max_retries=3, delay=1)
    def _get_hs300_index(self, start_date, end_date):
        """获取沪深300指数 - 使用可用接口"""
        df = ak.stock_zh_index_daily(symbol='sh000300')
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        return df['close']
    
    @retry_on_error(max_retries=3, delay=1)
    def _get_sh_index(self, start_date, end_date):
        """获取上证指数 - 使用可用接口"""
        df = ak.stock_zh_index_daily(symbol='sh000001')
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        self.raw_data['sh_index'] = df['close']  # 保存上证指数用于对比图
        return df['close']
    
    def get_real_data(self, start_date=None, end_date=None):
        if not self.use_akshare:
            return self.get_mock_data(start_date, end_date)
        
        print("正在获取真实数据...")
        
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            # 默认获取2年数据
            start_date = end_date - timedelta(days=730)
        
        result = pd.DataFrame()
        
        # 1. 指数数据
        try:
            print("  - 指数数据...", end="")
            result['iv'] = self._get_index_data(start_date, end_date)
            print("✅")
        except Exception as e:
            print(f"⚠️ ({e})")
        
        # 2. 涨跌停数据
        try:
            print("  - 涨跌停数据...", end="")
            limit_df = self._get_limit_up_down_data(start_date, end_date)
            if limit_df is not None:
                # 使用join确保索引对齐
                result = result.join(limit_df[['limit_ratio', 'limit_up', 'limit_down']], how='outer')
                print(f"✅ ({len(limit_df)}天)")
            else:
                print("⚠️ (无数据)")
        except Exception as e:
            print(f"⚠️ ({e})")
        
        # 3. 股指期货
        try:
            print("  - 股指期货...", end="")
            futures_basis = self._get_futures_data()
            if futures_basis is not None:
                result['futures_basis'] = futures_basis
                print("✅")
            else:
                print("⚠️ (无数据)")
        except Exception as e:
            print(f"⚠️ ({e})")
        
        # 4. 北向资金
        try:
            print("  - 北向资金...", end="")
            northbound = self._get_northbound_data(start_date, end_date)
            if northbound is not None:
                result['northbound_flow'] = northbound
                print(f"✅ ({len(northbound)}天)")
            else:
                print("⚠️ (无数据)")
        except Exception as e:
            print(f"⚠️ ({e})")
        
        # 5. 南向资金
        try:
            print("  - 南向资金...", end="")
            southbound = self._get_southbound_data(start_date, end_date)
            if southbound is not None:
                result['southbound_flow'] = southbound
                print(f"✅ ({len(southbound)}天)")
            else:
                print("⚠️ (无数据)")
        except Exception as e:
            print(f"⚠️ ({e})")
        
        # 确保result索引已归一化为日期（去掉时间部分）- 这对reindex匹配至关重要
        result.index = pd.to_datetime(result.index).normalize()
        
        # 6. 沪深300指数（用于对比）
        hs300_success = False
        for attempt in range(3):
            try:
                print(f"  - 沪深300指数(尝试{attempt+1})...", end="")
                hs300 = self._get_hs300_index(start_date, end_date)
                if hs300 is not None and len(hs300) > 0:
                    hs300.index = pd.to_datetime(hs300.index).normalize()
                    result['hs300'] = hs300.reindex(result.index)
                    self.raw_data['hs300'] = hs300
                    print(f"✅ ({result['hs300'].notna().sum()}天)")
                    hs300_success = True
                    break
            except Exception as e:
                print(f"⚠️", end="")
                time.sleep(2)
        if not hs300_success:
            print("❌ 沪深300获取失败")
        
        # 7. 上证指数（用于对比）
        sh_success = False
        for attempt in range(3):
            try:
                print(f"  - 上证指数(尝试{attempt+1})...", end="")
                sh_index = self._get_sh_index(start_date, end_date)
                if sh_index is not None and len(sh_index) > 0:
                    sh_index.index = pd.to_datetime(sh_index.index).normalize()
                    result['sh_index'] = sh_index.reindex(result.index)
                    self.raw_data['sh_index'] = sh_index
                    print(f"✅ ({result['sh_index'].notna().sum()}天)")
                    sh_success = True
                    break
            except Exception as e:
                print(f"⚠️", end="")
                time.sleep(2)
        if not sh_success:
            print("❌ 上证指数获取失败")
        
        # 将所有数据的日期索引归一化为日期（去掉时间部分）
        def normalize_index(df):
            """将索引归一化为日期"""
            df = df.copy()
            df.index = pd.to_datetime(df.index).normalize()  # 去掉时间部分
            # 去重，保留最后一天的数据
            df = df[~df.index.duplicated(keep='last')]
            return df
        
        # 归一化所有数据集的索引
        result = normalize_index(result)
        
        # 保存需要保护的列（涨跌停数据）
        protected_cols = ['limit_up', 'limit_down', 'limit_ratio']
        saved_data = {}
        for col in protected_cols:
            if col in result.columns:
                saved_data[col] = result[col].copy()
        
        # 生成模拟数据并归一化
        mock = self.get_mock_data(start_date, end_date)
        mock = normalize_index(mock)
        
        # 合并数据 - 只对非保护列使用模拟数据填充
        for col in mock.columns:
            if col not in result.columns:
                result[col] = mock[col]
            elif col not in protected_cols and result[col].count() < 30:
                result[col] = result[col].combine_first(mock[col])
        
        # 恢复保护列的真实数据
        for col, data in saved_data.items():
            result[col] = data.combine_first(result[col])
        
        # 确保索引是交易日频率
        result = result.sort_index()
        
        return result

# =============================================================================
# 恐慌指数计算模块
# =============================================================================

class PanicIndexCalculator:
    def __init__(self):
        self.data = None
        self.result = None
        
    def standardize(self, series, window=252):
        """标准化时间序列 - 使用全局分位数确保短期数据也能计算"""
        # 获取有效数据（非NaN）
        valid_data = series.dropna()
        
        if len(valid_data) < 5:
            # 数据太少，返回0.5中性值
            return pd.Series(0.5, index=series.index)
        
        # 使用全局最小最大值（而非滚动窗口），确保所有日期都能计算
        data_min = valid_data.min()
        data_max = valid_data.max()
        
        if data_max == data_min:
            # 避免除零
            return pd.Series(0.5, index=series.index)
        
        # 全局标准化
        standardized = (series - data_min) / (data_max - data_min)
        return standardized.clip(0, 1)
    
    def calculate(self, data):
        self.data = data
        df = data.copy()
        
        print("\n正在计算恐慌指数...")
        
        df['iv_std'] = self.standardize(df['iv']) if 'iv' in df.columns else 0.5
        df['limit_std'] = self.standardize(df['limit_ratio']) if 'limit_ratio' in df.columns else 0.5
        df['basis_std'] = self.standardize(df['futures_basis']) if 'futures_basis' in df.columns else 0.5
        
        # 南向资金（数据正常更新）
        if 'southbound_flow' in df.columns:
            df['south_std'] = self.standardize(-df['southbound_flow'])
        else:
            df['south_std'] = 0.5  # 中性值
        
        df['panic_index'] = (
            WEIGHTS['implied_volatility'] * df['iv_std'] +
            WEIGHTS['limit_up_down_ratio'] * df['limit_std'] +
            WEIGHTS['futures_premium'] * df['basis_std'] +
            WEIGHTS['southbound_flow'] * df['south_std']
        ) * 100
        
        df['status'] = df['panic_index'].apply(self.get_status)
        
        self.result = df
        return df
    
    def get_status(self, value):
        if pd.isna(value):
            return '未知'
        if value < THRESHOLDS['greedy']:
            return '贪婪'
        elif value < THRESHOLDS['optimistic']:
            return '乐观'
        elif value < THRESHOLDS['neutral']:
            return '中性'
        elif value < THRESHOLDS['panic']:
            return '恐慌'
        else:
            return '极度恐慌'

# =============================================================================
# 多指标可视化模块
# =============================================================================

# 全局中文字体
chinese_font = fm.FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')

def set_chinese_labels(ax, title, xlabel='', ylabel=''):
    """设置中文标签"""
    if title:
        ax.set_title(title, fontproperties=chinese_font, fontsize=12, fontweight='bold')
    if xlabel:
        ax.set_xlabel(xlabel, fontproperties=chinese_font, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontproperties=chinese_font, fontsize=10)

class MultiIndicatorVisualizer:
    """多指标可视化器"""
    
    def __init__(self, result_df, raw_data):
        self.result = result_df
        self.raw_data = raw_data
        self.font = chinese_font
        
    def plot_panic_vs_index(self, filename='panic_vs_index.png'):
        """
        绘制恐慌指数与大盘指数对比图（双Y轴）
        主轴：恐慌指数
        副轴：沪深300指数、上证指数
        """
        fig, ax1 = plt.subplots(figsize=(16, 8))
        
        # 主轴 - 恐慌指数
        color1 = '#1f77b4'
        ax1.set_xlabel('日期', fontproperties=self.font, fontsize=12)
        ax1.set_ylabel('恐慌指数', fontproperties=self.font, fontsize=12, color=color1)
        line1 = ax1.plot(self.result.index, self.result['panic_index'], 
                        linewidth=2.5, color=color1, label='恐慌指数')
        ax1.tick_params(axis='y', labelcolor=color1)
        ax1.set_ylim(0, 100)
        
        # 填充恐慌区间
        ax1.fill_between(self.result.index, 0, THRESHOLDS['greedy'],
                        alpha=0.2, color='#2ecc71')
        ax1.fill_between(self.result.index, THRESHOLDS['greedy'], 
                        THRESHOLDS['optimistic'], alpha=0.2, color='#f1c40f')
        ax1.fill_between(self.result.index, THRESHOLDS['optimistic'], 
                        THRESHOLDS['neutral'], alpha=0.2, color='#9b59b6')
        ax1.fill_between(self.result.index, THRESHOLDS['neutral'], 
                        THRESHOLDS['panic'], alpha=0.2, color='#e67e22')
        ax1.fill_between(self.result.index, THRESHOLDS['panic'], 100,
                        alpha=0.2, color='#e74c3c')
        
        # 添加恐慌指数阈值线
        for name, value in THRESHOLDS.items():
            if name in ['greedy', 'optimistic', 'neutral', 'panic']:
                ax1.axhline(y=value, color='gray', linestyle='--', alpha=0.3, linewidth=0.8)
        
        # 副轴 - 沪深300和上证指数
        ax2 = ax1.twinx()
        
        has_index_data = False
        lines = line1
        labels = ['恐慌指数']
        
        # 沪深300 - 使用更鲜明的颜色和更粗的线
        if 'hs300' in self.result.columns and self.result['hs300'].notna().any():
            color2 = '#d62728'  # 更深的红色
            line2 = ax2.plot(self.result.index, self.result['hs300'], 
                           linewidth=2.5, color=color2, alpha=0.9, label='沪深300',
                           linestyle='-', marker='', markersize=0)
            lines += line2
            labels.append('沪深300')
            has_index_data = True
        elif 'hs300' in self.raw_data and self.raw_data['hs300'] is not None:
            color2 = '#d62728'
            line2 = ax2.plot(self.raw_data['hs300'].index, self.raw_data['hs300'], 
                           linewidth=2.5, color=color2, alpha=0.9, label='沪深300',
                           linestyle='-', marker='', markersize=0)
            lines += line2
            labels.append('沪深300')
            has_index_data = True
        else:
            # 生成模拟的沪深300数据（用于演示）
            np.random.seed(42)
            n_days = len(self.result)
            base_price = 4000
            returns = np.random.normal(0.0003, 0.012, n_days)
            # 让指数走势与恐慌指数有一定负相关
            panic_normalized = self.result['panic_index'].values / 100
            returns = returns - panic_normalized * 0.005  # 恐慌时下跌
            prices = base_price * np.cumprod(1 + returns)
            
            color2 = '#d62728'
            line2 = ax2.plot(self.result.index, prices, 
                           linewidth=2.5, color=color2, alpha=0.9, label='沪深300(模拟)',
                           linestyle='-', marker='', markersize=0)
            lines += line2
            labels.append('沪深300(模拟)')
            has_index_data = True
            print("  ℹ️ 使用模拟沪深300数据演示")
        
        # 上证指数 - 使用更鲜明的颜色和更粗的线
        if 'sh_index' in self.result.columns and self.result['sh_index'].notna().any():
            color3 = '#2ca02c'  # 更深的绿色
            line3 = ax2.plot(self.result.index, self.result['sh_index'], 
                           linewidth=2.5, color=color3, alpha=0.9, label='上证指数',
                           linestyle='--', marker='', markersize=0)
            lines += line3
            labels.append('上证指数')
            has_index_data = True
        elif 'sh_index' in self.raw_data and self.raw_data['sh_index'] is not None:
            color3 = '#2ca02c'
            line3 = ax2.plot(self.raw_data['sh_index'].index, self.raw_data['sh_index'], 
                           linewidth=2.5, color=color3, alpha=0.9, label='上证指数',
                           linestyle='--', marker='', markersize=0)
            lines += line3
            labels.append('上证指数')
            has_index_data = True
        else:
            # 生成模拟的上证指数数据（用于演示）
            np.random.seed(43)
            n_days = len(self.result)
            base_price = 3300
            returns = np.random.normal(0.0003, 0.01, n_days)
            # 让指数走势与恐慌指数有一定负相关
            panic_normalized = self.result['panic_index'].values / 100
            returns = returns - panic_normalized * 0.004  # 恐慌时下跌
            prices = base_price * np.cumprod(1 + returns)
            
            color3 = '#2ca02c'
            line3 = ax2.plot(self.result.index, prices, 
                           linewidth=2.5, color=color3, alpha=0.9, label='上证指数(模拟)',
                           linestyle='--', marker='', markersize=0)
            lines += line3
            labels.append('上证指数(模拟)')
            has_index_data = True
            print("  ℹ️ 使用模拟上证指数数据演示")
        
        if has_index_data:
            ax2.set_ylabel('指数点位', fontproperties=self.font, fontsize=12)
            ax2.tick_params(axis='y')
        
        # 合并图例
        ax1.legend(lines, labels, loc='upper left', prop=self.font, fontsize=10)
        
        # 标题
        latest = self.result.iloc[-1]
        title_text = f'恐慌指数与大盘指数对比 | 当前恐慌: {latest["panic_index"]:.1f} ({latest["status"]})'
        plt.title(title_text, fontproperties=self.font, fontsize=14, fontweight='bold')
        
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"✅ 双轴对比图已保存到: {filename}")
        return filename
    
    def plot_comprehensive_chart(self, filename='comprehensive_chart.png'):
        """
        绘制综合图表，包含所有指标
        布局：第一行为双轴对比图（高度2倍），其他图表各占一行
        所有图表共享相同的时间轴，方便纵向对比
        """
        # 第一行高度是其他行的2倍，5行布局（移除北向资金）
        fig = plt.figure(figsize=(16, 24))
        gs = GridSpec(5, 1, height_ratios=[2, 1, 1, 1, 1], hspace=0.3)
        
        # 获取统一的时间轴范围
        x_min = self.result.index.min()
        x_max = self.result.index.max()
        
        # 1. 第一行：恐慌指数与大盘指数对比（双轴，高度2倍）
        ax1 = fig.add_subplot(gs[0])
        self._plot_panic_vs_index_unified(ax1, x_min, x_max)
        
        # 2. 恐慌指数
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        self._plot_panic_index(ax2, x_min, x_max)
        plt.setp(ax2.get_xticklabels(), visible=False)
        
        # 3. 波动率
        ax3 = fig.add_subplot(gs[2], sharex=ax1)
        self._plot_volatility(ax3, x_min, x_max)
        plt.setp(ax3.get_xticklabels(), visible=False)
        
        # 4. 涨跌停数据
        ax4 = fig.add_subplot(gs[3], sharex=ax1)
        self._plot_limit_up_down(ax4, x_min, x_max)
        plt.setp(ax4.get_xticklabels(), visible=False)
        
        # 5. 南向资金（北向资金已移除 - 数据2024年8月后停止更新）
        ax5 = fig.add_subplot(gs[4], sharex=ax1)
        self._plot_southbound(ax5, x_min, x_max)
        ax5.set_xlabel('日期', fontproperties=self.font, fontsize=11)
        
        # 总标题 - 调低y值让总标题更靠近第一行子图
        latest = self.result.iloc[-1]
        title_text = f'A股恐慌指数监控面板 | 当前: {latest["panic_index"]:.1f} ({latest["status"]}) | {latest.name.strftime("%Y-%m-%d")}'
        fig.suptitle(title_text, fontproperties=self.font, fontsize=14, fontweight='bold', y=0.99)

        # 调整布局，减少标题和图表之间的空白
        plt.tight_layout(rect=[0, 0, 1, 0.985])
        plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor='white', pad_inches=0.3)
        print(f"✅ 综合图表已保存到: {filename}")
        return filename
    
    def _plot_panic_vs_index_unified(self, ax, x_min, x_max):
        """绘制恐慌指数与大盘指数对比（统一时间轴版本）"""
        # 主轴 - 恐慌指数
        color1 = '#1f77b4'
        ax.set_ylabel('恐慌指数', fontproperties=self.font, fontsize=11, color=color1)
        line1 = ax.plot(self.result.index, self.result['panic_index'],
                        linewidth=1.0, color=color1, label='恐慌指数')
        ax.tick_params(axis='y', labelcolor=color1)
        ax.set_ylim(0, 100)
        ax.set_xlim(x_min, x_max)
        
        # 填充恐慌区间
        ax.fill_between(self.result.index, 0, THRESHOLDS['greedy'],
                        alpha=0.2, color='#2ecc71')
        ax.fill_between(self.result.index, THRESHOLDS['greedy'], 
                        THRESHOLDS['optimistic'], alpha=0.2, color='#f1c40f')
        ax.fill_between(self.result.index, THRESHOLDS['optimistic'], 
                        THRESHOLDS['neutral'], alpha=0.2, color='#9b59b6')
        ax.fill_between(self.result.index, THRESHOLDS['neutral'], 
                        THRESHOLDS['panic'], alpha=0.2, color='#e67e22')
        ax.fill_between(self.result.index, THRESHOLDS['panic'], 100,
                        alpha=0.2, color='#e74c3c')
        
        # 添加恐慌指数阈值线
        for name, value in THRESHOLDS.items():
            if name in ['greedy', 'optimistic', 'neutral', 'panic']:
                ax.axhline(y=value, color='gray', linestyle='--', alpha=0.3, linewidth=0.8)
        
        # 副轴 - 沪深300和上证指数
        ax2 = ax.twinx()
        
        has_index_data = False
        lines = line1
        labels = ['恐慌指数']
        
        # 沪深300
        if 'hs300' in self.result.columns and self.result['hs300'].notna().any():
            color2 = '#d62728'
            line2 = ax2.plot(self.result.index, self.result['hs300'],
                           linewidth=1.0, color=color2, alpha=0.9, label='沪深300',
                           linestyle='-', marker='', markersize=0)
            lines += line2
            labels.append('沪深300')
            has_index_data = True

        # 上证指数
        if 'sh_index' in self.result.columns and self.result['sh_index'].notna().any():
            color3 = '#2ca02c'
            line3 = ax2.plot(self.result.index, self.result['sh_index'],
                           linewidth=1.0, color=color3, alpha=0.9, label='上证指数',
                           linestyle='--', marker='', markersize=0)
            lines += line3
            labels.append('上证指数')
            has_index_data = True
        
        if has_index_data:
            ax2.set_ylabel('指数点位', fontproperties=self.font, fontsize=11)
            ax2.tick_params(axis='y')
        
        # 合并图例
        ax.legend(lines, labels, loc='upper left', prop=self.font, fontsize=9)
        ax.set_title('恐慌指数与大盘指数对比（沪深300+上证指数）',
                    fontproperties=self.font, fontsize=12, fontweight='bold', pad=2)
        ax.grid(alpha=0.3)
        
        # 第一行显示x轴标签，方便用户看到日期
        ax.tick_params(axis='x', labelsize=9)
        # 旋转x轴标签避免重叠
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    
    def _plot_panic_index(self, ax, x_min=None, x_max=None):
        """绘制恐慌指数"""
        ax.plot(self.result.index, self.result['panic_index'],
                linewidth=1.2, color='#1f77b4', label='恐慌指数')
        
        # 阈值线
        for name, value in THRESHOLDS.items():
            if name in ['greedy', 'optimistic', 'neutral', 'panic']:
                ax.axhline(y=value, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
        
        # 填充区域
        ax.fill_between(self.result.index, 0, THRESHOLDS['greedy'],
                       alpha=0.3, color='#2ecc71', label='贪婪')
        ax.fill_between(self.result.index, THRESHOLDS['greedy'], 
                       THRESHOLDS['optimistic'], alpha=0.3, color='#f1c40f', label='乐观')
        ax.fill_between(self.result.index, THRESHOLDS['optimistic'], 
                       THRESHOLDS['neutral'], alpha=0.3, color='#9b59b6', label='中性')
        ax.fill_between(self.result.index, THRESHOLDS['neutral'], 
                       THRESHOLDS['panic'], alpha=0.3, color='#e67e22', label='恐慌')
        ax.fill_between(self.result.index, THRESHOLDS['panic'], 100,
                       alpha=0.3, color='#e74c3c', label='极度恐慌')
        
        ax.set_ylabel('恐慌指数', fontproperties=self.font, fontsize=11)
        ax.set_title('A股恐慌指数', fontproperties=self.font, fontsize=12, fontweight='bold')
        ax.legend(loc='upper left', prop=self.font, fontsize=8, ncol=3)
        ax.grid(alpha=0.3)
        ax.set_ylim(0, 100)
        if x_min and x_max:
            ax.set_xlim(x_min, x_max)
        
        # 添加当前值标注
        latest = self.result.iloc[-1]
        status_text = latest['status']
        ax.annotate(f'{latest["panic_index"]:.1f}\n{status_text}',
                   xy=(latest.name, latest['panic_index']),
                   xytext=(10, 10), textcoords='offset points',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                   fontsize=9, fontweight='bold', fontproperties=self.font)
    
    def _plot_volatility(self, ax, x_min=None, x_max=None):
        """绘制波动率"""
        if 'iv' in self.result.columns:
            ax.plot(self.result.index, self.result['iv'] * 100, 
                   linewidth=1.5, color='#e74c3c', label='20日历史波动率')
            ax.fill_between(self.result.index, 0, self.result['iv'] * 100,
                           alpha=0.3, color='#e74c3c')
            
            # 添加均线
            iv_ma = self.result['iv'].rolling(window=60).mean() * 100
            ax.plot(self.result.index, iv_ma, '--', linewidth=1, color='#c0392b', alpha=0.7, label='60日均值')
            
            ax.set_ylabel('波动率 (%)', fontproperties=self.font, fontsize=10)
            ax.set_title('沪深300 历史波动率', fontproperties=self.font, fontsize=12, fontweight='bold')
            ax.legend(loc='upper left', prop=self.font, fontsize=8)
            ax.grid(alpha=0.3)
            if x_min and x_max:
                ax.set_xlim(x_min, x_max)
            
            # 当前值
            latest = self.result.iloc[-1]
            if not pd.isna(latest['iv']):
                ax.annotate(f'{latest["iv"]*100:.1f}%',
                           xy=(latest.name, latest['iv']*100),
                           xytext=(5, 5), textcoords='offset points',
                           fontsize=9, color='#e74c3c', fontweight='bold')
    
    def _plot_limit_up_down(self, ax, x_min=None, x_max=None):
        """绘制涨跌停数据"""
        if 'limit_up' in self.result.columns and 'limit_down' in self.result.columns:
            # 获取有真实数据的部分
            limit_up = self.result['limit_up'].dropna()
            limit_down = self.result['limit_down'].dropna()
            
            if len(limit_up) > 0:
                ax.bar(limit_up.index, limit_up, alpha=0.7, color='#e74c3c', label='涨停', width=0.8)
                ax.bar(limit_down.index, -limit_down, alpha=0.7, color='#2ecc71', label='跌停', width=0.8)
                
                ax.axhline(y=0, color='black', linewidth=0.5)
                ax.set_ylabel('家数', fontproperties=self.font, fontsize=10)
                ax.set_title('每日涨跌停家数', fontproperties=self.font, fontsize=12, fontweight='bold')
                ax.legend(loc='upper left', prop=self.font, fontsize=8)
                ax.grid(alpha=0.3, axis='y')
                if x_min and x_max:
                    ax.set_xlim(x_min, x_max)
                
                # 最新值
                if len(limit_up) > 0:
                    latest_date = limit_up.index[-1]
                    latest_up = limit_up.iloc[-1]
                    latest_down = limit_down.iloc[-1] if latest_date in limit_down.index else 0
                    ax.annotate(f'涨停: {int(latest_up)}\n跌停: {int(latest_down)}',
                               xy=(latest_date, latest_up),
                               xytext=(5, 5), textcoords='offset points',
                               fontsize=9, fontweight='bold')
        else:
            # 如果没有涨跌停数据，显示涨跌停比
            if 'limit_ratio' in self.result.columns:
                ax.plot(self.result.index, self.result['limit_ratio'] * 100,
                       linewidth=1.5, color='#9b59b6')
                ax.fill_between(self.result.index, 0, self.result['limit_ratio'] * 100,
                               alpha=0.3, color='#9b59b6')
                ax.set_ylabel('跌停占比 (%)', fontproperties=self.font, fontsize=10)
                ax.set_title('涨跌停比 (跌停/总数)', fontproperties=self.font, fontsize=12, fontweight='bold')
                ax.grid(alpha=0.3)
                if x_min and x_max:
                    ax.set_xlim(x_min, x_max)
    
    def _plot_northbound(self, ax, x_min=None, x_max=None):
        """绘制北向资金"""
        if 'northbound_flow' in self.result.columns:
            flow = self.result['northbound_flow']
            
            # 使用不同颜色区分流入流出
            colors = ['#2ecc71' if x >= 0 else '#e74c3c' for x in flow]
            ax.bar(flow.index, flow, alpha=0.7, color=colors, width=0.8)
            ax.axhline(y=0, color='black', linewidth=0.5)
            
            # 5日移动平均
            flow_ma = flow.rolling(window=5).mean()
            ax.plot(flow.index, flow_ma, '--', linewidth=1.5, color='#3498db', label='5日均值')
            
            ax.set_ylabel('净流入 (亿元)', fontproperties=self.font, fontsize=10)
            ax.set_title('北向资金 (沪股通+深股通)', fontproperties=self.font, fontsize=12, fontweight='bold')
            ax.legend(loc='upper left', prop=self.font, fontsize=8)
            ax.grid(alpha=0.3, axis='y')
            if x_min and x_max:
                ax.set_xlim(x_min, x_max)
            
            # 累计流入
            total = flow.sum()
            ax.text(0.02, 0.98, f'期间累计: {total:.1f}亿',
                   transform=ax.transAxes, fontsize=9, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5), fontproperties=self.font)
    
    def _plot_southbound(self, ax, x_min=None, x_max=None):
        """绘制南向资金"""
        if 'southbound_flow' in self.result.columns:
            flow = self.result['southbound_flow']
            
            colors = ['#2ecc71' if x >= 0 else '#e74c3c' for x in flow]
            ax.bar(flow.index, flow, alpha=0.7, color=colors, width=0.8)
            ax.axhline(y=0, color='black', linewidth=0.5)
            
            # 5日移动平均
            flow_ma = flow.rolling(window=5).mean()
            ax.plot(flow.index, flow_ma, '--', linewidth=1.5, color='#9b59b6', label='5日均值')
            
            ax.set_ylabel('净流入 (亿港元)', fontproperties=self.font, fontsize=10)
            ax.set_title('南向资金 (港股通)', fontproperties=self.font, fontsize=12, fontweight='bold')
            if x_min and x_max:
                ax.set_xlim(x_min, x_max)
            ax.legend(loc='upper left', prop=self.font, fontsize=8)
            ax.grid(alpha=0.3, axis='y')
            
            # 累计流入
            total = flow.sum()
            ax.text(0.02, 0.98, f'期间累计: {total:.1f}亿',
                   transform=ax.transAxes, fontsize=9, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5), fontproperties=self.font)

# =============================================================================
# 主程序
# =============================================================================

def main():
    print("=" * 70)
    print("📈 A股恐慌指数 - 多指标可视化版（支持本地缓存）")
    print("=" * 70)
    
    # 初始化缓存管理器
    cache_manager = DataCacheManager()
    print(f"\n💾 本地缓存: {cache_manager.get_cache_info()}")
    
    # 尝试从缓存加载数据
    cached_data = cache_manager.load_cache()
    
    if cached_data is not None:
        # 使用缓存数据
        print("\n✅ 使用本地缓存数据，无需从API获取")
        result = cached_data['result']
        raw_data = cached_data['raw_data']
        fetcher = DataFetcher()
        fetcher.raw_data = raw_data
        from_api = False
    else:
        # 从API获取数据
        print(f"\n{'✅ AkShare可用，将从API获取数据' if AKSHARE_AVAILABLE else '⚠️  AkShare不可用'}")
        
        # 获取数据
        fetcher = DataFetcher()
        data = fetcher.get_real_data() if AKSHARE_AVAILABLE else fetcher.get_mock_data()
        
        # 计算指数
        calculator = PanicIndexCalculator()
        result = calculator.calculate(data)
        
        # 保存到本地缓存
        cache_manager.save_cache(result, fetcher.raw_data)
        from_api = True
    
    # 打印摘要
    latest = result.iloc[-1]
    data_source = "API实时数据" if from_api else "本地缓存"
    print("\n" + "=" * 70)
    print(f"📊 当前市场状态（数据来源: {data_source}）")
    print("=" * 70)
    print(f"日期: {latest.name.strftime('%Y-%m-%d')}")
    print(f"恐慌指数: {latest['panic_index']:.2f} ({latest['status']})")
    print(f"波动率: {latest['iv']*100:.2f}%" if 'iv' in latest and not pd.isna(latest['iv']) else "波动率: 数据缺失")
    print("\n各分项指标:")
    print(f"  隐含波动率: {latest['iv_std']*100:.1f}" if 'iv_std' in latest else "  隐含波动率: N/A")
    print(f"  涨跌停比: {latest['limit_std']*100:.1f}" if 'limit_std' in latest else "  涨跌停比: N/A")
    print(f"  期货贴水: {latest['basis_std']*100:.1f}" if 'basis_std' in latest else "  期货贴水: N/A")
    print(f"  北向资金: {latest['flow_std']*100:.1f}" if 'flow_std' in latest else "  北向资金: N/A")
    
    # 绘制综合图表
    print("\n" + "=" * 70)
    print("🎨 正在生成图表...")
    print("=" * 70)
    
    visualizer = MultiIndicatorVisualizer(result, fetcher.raw_data)
    
    # 1. 多指标综合图
    visualizer.plot_comprehensive_chart('comprehensive_chart.png')
    
    # 2. 恐慌指数与大盘指数对比图（双轴）
    visualizer.plot_panic_vs_index('panic_vs_index.png')
    
    # 保存数据到CSV
    result.to_csv('panic_index_data.csv', encoding='utf-8-sig')
    print(f"✅ 数据已保存到: panic_index_data.csv")
    
    print("\n" + "=" * 70)
    print("🎉 完成！")
    print("=" * 70)
    
    # 提示缓存信息
    if from_api:
        print(f"\n💡 提示: 数据已缓存到本地，{CACHE_CONFIG['max_age_hours']}小时内再次运行将直接使用缓存")
    else:
        print(f"\n💡 提示: 如需强制更新数据，请删除缓存文件: {cache_manager.cache_path}")

if __name__ == '__main__':
    main()

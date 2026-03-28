"""
可视化模块
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.gridspec import GridSpec
import pandas as pd
from config import get_config

class Visualizer:
    """恐慌指数可视化器"""
    
    def __init__(self):
        self.config = get_config()
        self.viz_config = self.config.viz_config
        self.thresholds = self.config.thresholds
        
        # 设置中文字体
        font_path = self.viz_config.get('font_path', 
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
        self.chinese_font = fm.FontProperties(fname=font_path)
        
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
    
    def plot_comparison(self, df: pd.DataFrame, raw_data: dict,
                       output_path: str = 'panic_vs_index.png'):
        """绘制恐慌指数与大盘指数对比图（双轴）"""
        fig, ax1 = plt.subplots(figsize=(16, 8))
        
        # 主轴 - 恐慌指数
        color1 = '#1f77b4'
        ax1.set_xlabel('日期', fontproperties=self.chinese_font, fontsize=12)
        ax1.set_ylabel('恐慌指数', fontproperties=self.chinese_font, fontsize=12, color=color1)
        line1 = ax1.plot(df.index, df['panic_index'], 
                        linewidth=2.5, color=color1, label='恐慌指数')
        ax1.tick_params(axis='y', labelcolor=color1)
        ax1.set_ylim(0, 100)
        
        # 填充恐慌区间
        ax1.fill_between(df.index, 0, self.thresholds.get('greedy', 20),
                        alpha=0.2, color='#2ecc71')
        ax1.fill_between(df.index, self.thresholds.get('greedy', 20), 
                        self.thresholds.get('optimistic', 40), alpha=0.2, color='#f1c40f')
        ax1.fill_between(df.index, self.thresholds.get('optimistic', 40), 
                        self.thresholds.get('neutral', 60), alpha=0.2, color='#9b59b6')
        ax1.fill_between(df.index, self.thresholds.get('neutral', 60), 
                        self.thresholds.get('panic', 80), alpha=0.2, color='#e67e22')
        ax1.fill_between(df.index, self.thresholds.get('panic', 80), 100,
                        alpha=0.2, color='#e74c3c')
        
        # 添加恐慌指数阈值线
        for name, value in self.thresholds.items():
            if name in ['greedy', 'optimistic', 'neutral', 'panic']:
                ax1.axhline(y=value, color='gray', linestyle='--', alpha=0.3, linewidth=0.8)
        
        # 副轴 - 沪深300和上证指数
        ax2 = ax1.twinx()
        
        has_index_data = False
        lines = line1
        labels = ['恐慌指数']
        
        # 沪深300
        if 'hs300' in df.columns and df['hs300'].notna().any():
            color2 = '#d62728'
            line2 = ax2.plot(df.index, df['hs300'], 
                           linewidth=2.5, color=color2, alpha=0.9, label='沪深300',
                           linestyle='-', marker='', markersize=0)
            lines += line2
            labels.append('沪深300')
            has_index_data = True
        elif 'hs300' in raw_data and raw_data['hs300'] is not None:
            color2 = '#d62728'
            line2 = ax2.plot(raw_data['hs300'].index, raw_data['hs300'], 
                           linewidth=2.5, color=color2, alpha=0.9, label='沪深300',
                           linestyle='-', marker='', markersize=0)
            lines += line2
            labels.append('沪深300')
            has_index_data = True
        
        # 上证指数
        if 'sh_index' in df.columns and df['sh_index'].notna().any():
            color3 = '#2ca02c'
            line3 = ax2.plot(df.index, df['sh_index'], 
                           linewidth=2.5, color=color3, alpha=0.9, label='上证指数',
                           linestyle='--', marker='', markersize=0)
            lines += line3
            labels.append('上证指数')
            has_index_data = True
        elif 'sh_index' in raw_data and raw_data['sh_index'] is not None:
            color3 = '#2ca02c'
            line3 = ax2.plot(raw_data['sh_index'].index, raw_data['sh_index'], 
                           linewidth=2.5, color=color3, alpha=0.9, label='上证指数',
                           linestyle='--', marker='', markersize=0)
            lines += line3
            labels.append('上证指数')
            has_index_data = True
        
        if has_index_data:
            ax2.set_ylabel('指数点位', fontproperties=self.chinese_font, fontsize=12)
            ax2.tick_params(axis='y')
        
        # 合并图例
        ax1.legend(lines, labels, loc='upper left', prop=self.chinese_font, fontsize=10)
        
        # 标题
        latest = df.iloc[-1]
        title_text = f'恐慌指数与大盘指数对比 | 当前恐慌: {latest["panic_index"]:.1f} ({latest["status"]})'
        plt.title(title_text, fontproperties=self.chinese_font, fontsize=14, fontweight='bold')
        
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"✅ 双轴对比图已保存: {output_path}")
        plt.close()
    
    def plot_comprehensive(self, df: pd.DataFrame, raw_data: dict, 
                          output_path: str = 'comprehensive_chart.png'):
        """绘制综合图表"""
        fig = plt.figure(figsize=(16, 24))
        gs = GridSpec(5, 1, height_ratios=[2, 1, 1, 1, 1], hspace=0.3)
        
        x_min = df.index.min()
        x_max = df.index.max()
        
        # 1. 恐慌指数与大盘对比
        ax1 = fig.add_subplot(gs[0])
        self._plot_panic_vs_index(ax1, df, x_min, x_max, raw_data)
        
        # 2. 恐慌指数
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        self._plot_panic_index(ax2, df, x_min, x_max)
        plt.setp(ax2.get_xticklabels(), visible=False)
        
        # 3. 波动率
        ax3 = fig.add_subplot(gs[2], sharex=ax1)
        self._plot_volatility(ax3, df, x_min, x_max)
        plt.setp(ax3.get_xticklabels(), visible=False)
        
        # 4. 涨跌停
        ax4 = fig.add_subplot(gs[3], sharex=ax1)
        self._plot_limit_up_down(ax4, df, x_min, x_max, raw_data)
        plt.setp(ax4.get_xticklabels(), visible=False)
        
        # 5. 南向资金
        ax5 = fig.add_subplot(gs[4], sharex=ax1)
        self._plot_southbound(ax5, df, x_min, x_max)
        ax5.set_xlabel('日期', fontproperties=self.chinese_font, fontsize=11)
        
        # 总标题
        latest = df.iloc[-1]
        title = f'A股恐慌指数监控面板 | 当前: {latest["panic_index"]:.1f} ({latest["status"]}) | {latest.name.strftime("%Y-%m-%d")}'
        fig.suptitle(title, fontproperties=self.chinese_font, fontsize=14, fontweight='bold', y=0.99)
        
        plt.tight_layout(rect=[0, 0, 1, 0.985])
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white', pad_inches=0.3)
        print(f"✅ 综合图表已保存: {output_path}")
        plt.close()
    
    def plot_simple(self, df: pd.DataFrame, output_path: str = 'panic_chart.png'):
        """绘制简化图表"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # 绘制恐慌指数
        ax.plot(df.index, df['panic_index'], linewidth=2, color='#1f77b4', label='恐慌指数')
        
        # 填充区域
        ax.fill_between(df.index, 0, self.thresholds.get('greedy', 20),
                       alpha=0.3, color='#2ecc71', label='贪婪')
        ax.fill_between(df.index, self.thresholds.get('greedy', 20), 
                       self.thresholds.get('optimistic', 40), 
                       alpha=0.3, color='#f1c40f', label='乐观')
        ax.fill_between(df.index, self.thresholds.get('optimistic', 40),
                       self.thresholds.get('neutral', 60),
                       alpha=0.3, color='#9b59b6', label='中性')
        ax.fill_between(df.index, self.thresholds.get('neutral', 60),
                       self.thresholds.get('panic', 80),
                       alpha=0.3, color='#e67e22', label='恐慌')
        ax.fill_between(df.index, self.thresholds.get('panic', 80), 100,
                       alpha=0.3, color='#e74c3c', label='极度恐慌')
        
        # 阈值线
        for name, value in self.thresholds.items():
            if name != 'extreme_panic':
                ax.axhline(y=value, color='gray', linestyle='--', alpha=0.5)
        
        # 当前值标注
        latest = df.iloc[-1]
        ax.annotate(f'{latest["panic_index"]:.1f}\n{latest["status"]}',
                   xy=(latest.name, latest['panic_index']),
                   xytext=(10, 10), textcoords='offset points',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                   fontsize=10, fontweight='bold', fontproperties=self.chinese_font)
        
        ax.set_ylabel('恐慌指数', fontproperties=self.chinese_font, fontsize=12)
        ax.set_title('A股恐慌指数', fontproperties=self.chinese_font, fontsize=14, fontweight='bold')
        ax.legend(loc='upper left', prop=self.chinese_font, fontsize=9)
        ax.grid(alpha=0.3)
        ax.set_ylim(0, 100)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"✅ 简化图表已保存: {output_path}")
        plt.close()
    
    def _plot_panic_vs_index(self, ax, df, x_min, x_max, raw_data=None):
        """恐慌指数与大盘对比"""
        raw_data = raw_data or {}
        
        # 主轴 - 恐慌指数
        ax.set_ylabel('恐慌指数', fontproperties=self.chinese_font, fontsize=11, color='#1f77b4')
        line1 = ax.plot(df.index, df['panic_index'], linewidth=1.5, color='#1f77b4')
        ax.tick_params(axis='y', labelcolor='#1f77b4')
        ax.set_ylim(0, 100)
        ax.set_xlim(x_min, x_max)
        
        # 填充区域
        for i, (label, color) in enumerate([
            ('greedy', '#2ecc71'), ('optimistic', '#f1c40f'),
            ('neutral', '#9b59b6'), ('panic', '#e67e22'), ('extreme_panic', '#e74c3c')
        ]):
            lower = list(self.thresholds.values())[i-1] if i > 0 else 0
            upper = list(self.thresholds.values())[i] if i < len(self.thresholds) else 100
            ax.fill_between(df.index, lower, upper, alpha=0.2, color=color)
        
        # 副轴 - 指数
        ax2 = ax.twinx()
        lines = line1
        labels = ['恐慌指数']
        
        # 沪深300 - 优先使用raw_data
        hs300_data = raw_data.get('hs300') if 'hs300' in raw_data else df.get('hs300')
        if hs300_data is not None and len(hs300_data) > 0:
            line2 = ax2.plot(hs300_data.index, hs300_data.values, 
                           linewidth=1.5, color='#d62728', alpha=0.9, label='沪深300')
            lines += line2
            labels.append('沪深300')
        
        # 上证指数 - 优先使用raw_data
        sh_data = raw_data.get('sh_index') if 'sh_index' in raw_data else df.get('sh_index')
        if sh_data is not None and len(sh_data) > 0:
            line3 = ax2.plot(sh_data.index, sh_data.values, 
                           linewidth=1.5, color='#2ca02c', alpha=0.9,
                           linestyle='--', label='上证指数')
            lines += line3
            labels.append('上证指数')
        
        ax2.set_ylabel('指数点位', fontproperties=self.chinese_font, fontsize=11)
        ax.legend(lines, labels, loc='upper left', prop=self.chinese_font, fontsize=9)
        ax.set_title('恐慌指数与大盘指数对比', fontproperties=self.chinese_font, fontsize=12, fontweight='bold')
        ax.grid(alpha=0.3)
    
    def _plot_panic_index(self, ax, df, x_min, x_max):
        """单独恐慌指数"""
        ax.plot(df.index, df['panic_index'], linewidth=1.2, color='#1f77b4')
        
        for name, value in self.thresholds.items():
            if name != 'extreme_panic':
                ax.axhline(y=value, color='gray', linestyle='--', alpha=0.5)
        
        colors = ['#2ecc71', '#f1c40f', '#9b59b6', '#e67e22', '#e74c3c']
        for i, color in enumerate(colors):
            lower = list(self.thresholds.values())[i-1] if i > 0 else 0
            upper = list(self.thresholds.values())[i] if i < len(self.thresholds) - 1 else 100
            ax.fill_between(df.index, lower, upper, alpha=0.3, color=color)
        
        ax.set_ylabel('恐慌指数', fontproperties=self.chinese_font, fontsize=11)
        ax.set_title('A股恐慌指数', fontproperties=self.chinese_font, fontsize=12, fontweight='bold')
        ax.set_ylim(0, 100)
        ax.set_xlim(x_min, x_max)
        ax.grid(alpha=0.3)
        
        latest = df.iloc[-1]
        ax.annotate(f'{latest["panic_index"]:.1f}\n{latest["status"]}',
                   xy=(latest.name, latest['panic_index']),
                   xytext=(10, 10), textcoords='offset points',
                   bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7),
                   fontsize=9, fontweight='bold', fontproperties=self.chinese_font)
    
    def _plot_volatility(self, ax, df, x_min, x_max):
        """波动率"""
        if 'iv' in df.columns:
            ax.plot(df.index, df['iv'] * 100, linewidth=1.5, color='#e74c3c')
            ax.fill_between(df.index, 0, df['iv'] * 100, alpha=0.3, color='#e74c3c')
            ax.set_ylabel('波动率 (%)', fontproperties=self.chinese_font, fontsize=10)
            ax.set_title('沪深300 历史波动率', fontproperties=self.chinese_font, fontsize=12)
            ax.set_xlim(x_min, x_max)
            ax.grid(alpha=0.3)
    
    def _plot_limit_up_down(self, ax, df, x_min, x_max, raw_data=None):
        """涨跌停"""
        raw_data = raw_data or {}
        
        # 优先从raw_data获取涨跌停数据
        limit_up = raw_data.get('limit_up') if 'limit_up' in raw_data else df.get('limit_up')
        limit_down = raw_data.get('limit_down') if 'limit_down' in raw_data else df.get('limit_down')
        
        if limit_up is not None and limit_down is not None and len(limit_up) > 0:
            ax.bar(limit_up.index, limit_up.values, alpha=0.7, color='#e74c3c', label='涨停', width=0.8)
            ax.bar(limit_down.index, -limit_down.values, alpha=0.7, color='#2ecc71', label='跌停', width=0.8)
            ax.axhline(y=0, color='black', linewidth=0.5)
            ax.set_ylabel('家数', fontproperties=self.chinese_font, fontsize=10)
            ax.set_title('每日涨跌停家数', fontproperties=self.chinese_font, fontsize=12)
            ax.legend(loc='upper left', prop=self.chinese_font, fontsize=8)
            ax.set_xlim(x_min, x_max)
            ax.grid(alpha=0.3, axis='y')
            
            # 显示最新值
            if len(limit_up) > 0:
                latest_date = limit_up.index[-1]
                latest_up = limit_up.iloc[-1]
                latest_down = limit_down.iloc[-1] if latest_date in limit_down.index else 0
                ax.annotate(f'涨停: {int(latest_up)}\n跌停: {int(latest_down)}',
                           xy=(latest_date, latest_up),
                           xytext=(5, 5), textcoords='offset points',
                           fontsize=9, fontweight='bold')
    
    def _plot_southbound(self, ax, df, x_min, x_max):
        """南向资金"""
        if 'southbound_flow' in df.columns:
            flow = df['southbound_flow']
            colors = ['#2ecc71' if x >= 0 else '#e74c3c' for x in flow]
            ax.bar(flow.index, flow, alpha=0.7, color=colors, width=0.8)
            ax.axhline(y=0, color='black', linewidth=0.5)
            ax.set_ylabel('净流入 (亿港元)', fontproperties=self.chinese_font, fontsize=10)
            ax.set_title('南向资金 (港股通)', fontproperties=self.chinese_font, fontsize=12)
            ax.set_xlim(x_min, x_max)
            ax.grid(alpha=0.3, axis='y')
            
            total = flow.sum()
            ax.text(0.02, 0.98, f'累计: {total:.1f}亿',
                   transform=ax.transAxes, fontsize=9, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                   fontproperties=self.chinese_font)

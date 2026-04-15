"""
Baostock指数数据获取器
"""

from datetime import datetime
from typing import Optional
import pandas as pd
import baostock as bs
from fetchers.base import DataFetcher


class BaostockIndexFetcher(DataFetcher):
    """Baostock指数数据获取器"""

    def fetch(self, start_date: datetime, end_date: datetime) -> Optional[pd.Series]:
        """获取指数数据"""
        try:
            print("  - 指数数据(Baostock)...", end="", flush=True)

            # 登录Baostock
            lg = bs.login()
            if lg.error_code != '0':
                print(f"⚠️ (登录失败: {lg.error_msg})")
                return None

            # 为了计算20日波动率，需要往前推20天获取数据
            import datetime
            adjusted_start_date = start_date - datetime.timedelta(days=20)
            
            # 转换日期格式
            start_str = adjusted_start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            # 获取沪深300指数数据
            rs = bs.query_history_k_data_plus(
                "sh.000300",
                "date,close",
                start_date=start_str,
                end_date=end_str,
                frequency="d",
                adjustflag="3"  # 复权类型：3-不复权
            )

            if rs.error_code != '0':
                print(f"⚠️ (获取失败: {rs.error_msg})")
                bs.logout()
                return None

            # 处理数据
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                print("⚠️ (无数据)")
                bs.logout()
                return None

            df = pd.DataFrame(data_list, columns=rs.fields)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df['close'] = pd.to_numeric(df['close'], errors='coerce')

            # 计算20日历史波动率
            df['returns'] = df['close'].pct_change()
            # 确保计算的是百分比变化的标准差，而不是价格的标准差
            df['iv'] = df['returns'].rolling(window=20).std() * (252 ** 0.5) * 100

            # 保存原始数据
            self.raw_data['hs300'] = df['close']

            # 退出登录
            bs.logout()

            # 只返回用户请求的日期范围内的数据
            result = df['iv'][start_date:end_date]
            
            print(f"✅ ({len(result)}天)")
            return result

        except Exception as e:
            print(f"⚠️ ({e})")
            try:
                bs.logout()
            except:
                pass
            return None

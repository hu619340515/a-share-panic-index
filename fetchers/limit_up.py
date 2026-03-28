"""
涨跌停数据获取 - 使用金融界API
"""
import time
import requests
from datetime import datetime
from typing import Optional
import pandas as pd
from fetchers.base import DataFetcher

class LimitUpDownFetcher(DataFetcher):
    """涨跌停数据获取器"""
    
    def fetch(self, start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """获取历史涨跌停数据"""
        try:
            print("  - 涨跌停数据...")
            print(f"    正在从金融界API获取涨跌停数据...")
            
            url = "https://gateway.jrj.com/quot-dc/zdt/market_history"
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://summary.jrj.com.cn/",
                "Origin": "https://summary.jrj.com.cn",
                "productid": "6000021",
            }
            
            all_data = []
            
            # 生成月份列表
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
                            if start_date <= date <= end_date:
                                all_data.append({
                                    'date': date,
                                    'limit_up': item['upLimitCount'],
                                    'limit_down': item['downLimitCount']
                                })
                        
                        if i % 5 == 0 or i == len(months) - 1:
                            print(f"      [{i+1}/{len(months)}] {year_month}: {len(list_data)}条")
                    
                    time.sleep(0.3)
                    
                except Exception as e:
                    print(f"      ⚠️ {year_month} 获取失败: {e}")
                    continue
            
            if not all_data:
                print("    ⚠️ 无数据")
                return None
            
            # 去重并计算比例
            seen = set()
            unique_data = []
            for item in sorted(all_data, key=lambda x: x['date']):
                if item['date'] not in seen:
                    seen.add(item['date'])
                    total = item['limit_up'] + item['limit_down']
                    item['limit_ratio'] = item['limit_down'] / total if total > 0 else 0.5
                    unique_data.append(item)
            
            df = pd.DataFrame(unique_data)
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            
            self.raw_data['limit_up'] = df['limit_up']
            self.raw_data['limit_down'] = df['limit_down']
            
            print(f"    ✅ 从金融界API获取 {len(df)} 天涨跌停数据")
            return df
            
        except Exception as e:
            print(f"⚠️ ({e})")
            return None

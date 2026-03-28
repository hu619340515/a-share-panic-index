"""
数据缓存模块 - 支持SQLite和Pickle
"""
import os
import pickle
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd
from config import get_config

class CacheManager:
    """缓存管理基类"""
    
    def __init__(self):
        self.config = get_config().cache_config
    
    def is_valid(self) -> bool:
        """检查缓存是否有效"""
        raise NotImplementedError
    
    def load(self) -> Optional[pd.DataFrame]:
        """加载缓存数据"""
        raise NotImplementedError
    
    def save(self, df: pd.DataFrame):
        """保存数据到缓存"""
        raise NotImplementedError
    
    def clear(self):
        """清除缓存"""
        raise NotImplementedError


class SQLiteCache(CacheManager):
    """SQLite缓存实现"""
    
    def __init__(self):
        super().__init__()
        self.db_path = Path(self.config.get('sqlite_path', './data_cache/panic_index.db'))
        self._ensure_db()
    
    def _ensure_db(self):
        """确保数据库和表存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建恐慌指数表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS panic_index (
                date TEXT PRIMARY KEY,
                panic_index REAL,
                volatility REAL,
                limit_ratio REAL,
                limit_up INTEGER,
                limit_down INTEGER,
                futures_basis REAL,
                northbound_flow REAL,
                southbound_flow REAL,
                hs300_close REAL,
                sh_index_close REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建元数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def is_valid(self) -> bool:
        """检查缓存是否在有效期内"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT updated_at FROM metadata 
            WHERE key = 'last_update' 
            ORDER BY updated_at DESC LIMIT 1
        ''')
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            return False
        
        last_update = datetime.fromisoformat(result[0])
        max_age = timedelta(hours=self.config.get('max_age_hours', 6))
        
        return datetime.now() - last_update < max_age
    
    def load(self) -> Optional[pd.DataFrame]:
        """从SQLite加载数据"""
        if not self.is_valid():
            return None
        
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query('''
            SELECT date, panic_index, volatility, limit_ratio, 
                   limit_up, limit_down, futures_basis,
                   northbound_flow, southbound_flow,
                   hs300_close, sh_index_close, status
            FROM panic_index
            ORDER BY date
        ''', conn, parse_dates=['date'], index_col='date')
        conn.close()
        
        return df if not df.empty else None
    
    def save(self, df: pd.DataFrame):
        """保存数据到SQLite"""
        conn = sqlite3.connect(self.db_path)
        
        # 准备数据
        save_df = df.copy()
        save_df.reset_index(inplace=True)
        save_df['date'] = save_df['date'].dt.strftime('%Y-%m-%d')
        
        # 列名映射
        column_map = {
            'panic_index': 'panic_index',
            'iv': 'volatility',
            'limit_ratio': 'limit_ratio',
            'limit_up': 'limit_up',
            'limit_down': 'limit_down',
            'futures_basis': 'futures_basis',
            'northbound_flow': 'northbound_flow',
            'southbound_flow': 'southbound_flow',
            'hs300': 'hs300_close',
            'sh_index': 'sh_index_close',
            'status': 'status'
        }
        
        # 重命名列
        for old, new in column_map.items():
            if old in save_df.columns:
                save_df.rename(columns={old: new}, inplace=True)
        
        # 只保留存在的列
        existing_cols = ['date', 'panic_index', 'volatility', 'limit_ratio',
                        'limit_up', 'limit_down', 'futures_basis',
                        'northbound_flow', 'southbound_flow',
                        'hs300_close', 'sh_index_close', 'status']
        save_cols = [c for c in existing_cols if c in save_df.columns]
        save_df = save_df[save_cols]
        
        # 插入数据（UPSERT）
        for _, row in save_df.iterrows():
            cols = ', '.join(save_cols)
            placeholders = ', '.join(['?' for _ in save_cols])
            update_cols = ', '.join([f"{c}=excluded.{c}" for c in save_cols if c != 'date'])
            
            sql = f'''
                INSERT INTO panic_index ({cols}) VALUES ({placeholders})
                ON CONFLICT(date) DO UPDATE SET {update_cols}
            '''
            conn.execute(sql, tuple(row))
        
        # 更新元数据
        conn.execute('''
            INSERT INTO metadata (key, value, updated_at)
            VALUES ('last_update', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
        ''', (datetime.now().isoformat(),))
        
        conn.commit()
        conn.close()
        print(f"  ✅ 数据已保存到SQLite: {self.db_path}")
    
    def get_latest(self, days: int = 30) -> pd.DataFrame:
        """获取最近N天的数据"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query(f'''
            SELECT * FROM panic_index
            WHERE date >= date('now', '-{days} days')
            ORDER BY date DESC
        ''', conn, parse_dates=['date'], index_col='date')
        conn.close()
        return df
    
    def clear(self):
        """清除所有缓存数据"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('DELETE FROM panic_index')
        conn.execute('DELETE FROM metadata')
        conn.commit()
        conn.close()
        print("  ✅ SQLite缓存已清除")


class PickleCache(CacheManager):
    """Pickle缓存实现（向后兼容）"""
    
    def __init__(self):
        super().__init__()
        self.cache_path = Path(self.config.get('pickle_path', './data_cache/panic_index_cache.pkl'))
    
    def is_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self.cache_path.exists():
            return False
        
        mtime = datetime.fromtimestamp(self.cache_path.stat().st_mtime)
        max_age = timedelta(hours=self.config.get('max_age_hours', 6))
        
        return datetime.now() - mtime < max_age
    
    def load(self) -> Optional[pd.DataFrame]:
        """加载pickle缓存"""
        if not self.is_valid():
            return None
        
        try:
            with open(self.cache_path, 'rb') as f:
                cache_data = pickle.load(f)
            return cache_data.get('result')
        except Exception as e:
            print(f"  ⚠️  加载pickle缓存失败: {e}")
            return None
    
    def save(self, df: pd.DataFrame):
        """保存到pickle（向后兼容）"""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            cache_data = {
                'result': df,
                'save_time': datetime.now()
            }
            with open(self.cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
            print(f"  ✅ 数据已保存到pickle: {self.cache_path}")
        except Exception as e:
            print(f"  ⚠️  保存pickle缓存失败: {e}")
    
    def clear(self):
        """清除pickle缓存"""
        if self.cache_path.exists():
            self.cache_path.unlink()
            print("  ✅ Pickle缓存已清除")


def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例"""
    config = get_config()
    cache_type = config.get('cache.type', 'sqlite')
    
    if cache_type == 'sqlite':
        return SQLiteCache()
    elif cache_type == 'pickle':
        return PickleCache()
    else:
        return SQLiteCache()  # 默认

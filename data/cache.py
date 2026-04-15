"""
数据缓存模块 - 支持SQLite和Pickle
"""

import os
import pickle
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
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
        self.db_path = Path(
            self.config.get("sqlite_path", "./data_cache/panic_index.db")
        )
        self._ensure_db()

    def _ensure_db(self):
        """确保数据库和表存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 创建恐慌指数表
        cursor.execute("""
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
        """)

        # 创建元数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def is_valid(self) -> bool:
        """检查缓存是否在有效期内"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT updated_at FROM metadata 
            WHERE key = 'last_update' 
            ORDER BY updated_at DESC LIMIT 1
        """)
        result = cursor.fetchone()
        conn.close()

        if result is None:
            return False

        last_update = datetime.fromisoformat(result[0])
        max_age = timedelta(hours=self.config.get("max_age_hours", 6))

        return datetime.now() - last_update < max_age

    def load(self) -> Optional[pd.DataFrame]:
        """从SQLite加载数据"""
        if not self.is_valid():
            return None

        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query(
            """
            SELECT date, panic_index, volatility, limit_ratio, 
                   limit_up, limit_down, futures_basis,
                   northbound_flow, southbound_flow,
                   hs300_close, sh_index_close, status
            FROM panic_index
            ORDER BY date
        """,
            conn,
            parse_dates=["date"],
            index_col="date",
        )
        conn.close()

        return df if not df.empty else None

    def save(self, df: pd.DataFrame):
        """保存数据到SQLite"""
        conn = sqlite3.connect(self.db_path)

        # 准备数据
        save_df = df.copy()
        save_df.reset_index(inplace=True)
        # 处理日期列 - 检查是否存在'date'列或'index'列
        if 'date' not in save_df.columns and 'index' in save_df.columns:
            save_df.rename(columns={'index': 'date'}, inplace=True)
        save_df["date"] = pd.to_datetime(save_df["date"]).dt.strftime("%Y-%m-%d")

        # 列名映射
        column_map = {
            "panic_index": "panic_index",
            "iv": "volatility",
            "limit_ratio": "limit_ratio",
            "limit_up": "limit_up",
            "limit_down": "limit_down",
            "futures_basis": "futures_basis",
            "northbound_flow": "northbound_flow",
            "southbound_flow": "southbound_flow",
            "hs300": "hs300_close",
            "sh_index": "sh_index_close",
            "status": "status",
        }

        # 重命名列
        for old, new in column_map.items():
            if old in save_df.columns:
                save_df.rename(columns={old: new}, inplace=True)

        # 只保留存在的列
        existing_cols = [
            "date",
            "panic_index",
            "volatility",
            "limit_ratio",
            "limit_up",
            "limit_down",
            "futures_basis",
            "northbound_flow",
            "southbound_flow",
            "hs300_close",
            "sh_index_close",
            "status",
        ]
        save_cols = [c for c in existing_cols if c in save_df.columns]
        save_df = save_df[save_cols]

        # 插入数据（UPSERT）
        for _, row in save_df.iterrows():
            cols = ", ".join(save_cols)
            placeholders = ", ".join(["?" for _ in save_cols])
            update_cols = ", ".join(
                [f"{c}=excluded.{c}" for c in save_cols if c != "date"]
            )

            sql = f"""
                INSERT INTO panic_index ({cols}) VALUES ({placeholders})
                ON CONFLICT(date) DO UPDATE SET {update_cols}
            """
            conn.execute(sql, tuple(row))

        # 更新元数据
        conn.execute(
            """
            INSERT INTO metadata (key, value, updated_at)
            VALUES ('last_update', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
        """,
            (datetime.now().isoformat(),),
        )

        conn.commit()
        conn.close()

    def get_latest(self, days: int = 30) -> pd.DataFrame:
        """获取最近N天的数据"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query(
            f"""
            SELECT * FROM panic_index
            WHERE date >= date('now', '-{days} days')
            ORDER BY date DESC
        """,
            conn,
            parse_dates=["date"],
            index_col="date",
        )
        conn.close()
        return df

    def clear(self):
        """清除所有缓存数据"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM panic_index")
        conn.execute("DELETE FROM metadata")
        conn.commit()
        conn.close()


class PickleCache(CacheManager):
    """Pickle缓存实现（向后兼容）"""

    def __init__(self):
        super().__init__()
        self.cache_path = Path(
            self.config.get("pickle_path", "./data_cache/panic_index_cache.pkl")
        )

    def is_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self.cache_path.exists():
            return False

        mtime = datetime.fromtimestamp(self.cache_path.stat().st_mtime)
        max_age = timedelta(hours=self.config.get("max_age_hours", 6))

        return datetime.now() - mtime < max_age

    def load(self) -> Optional[pd.DataFrame]:
        """加载pickle缓存"""
        if not self.is_valid():
            return None

        try:
            with open(self.cache_path, "rb") as f:
                cache_data = pickle.load(f)
            return cache_data.get("result")
        except Exception as e:
            print(f"  ⚠️  加载pickle缓存失败: {e}")
            return None

    def save(self, df: pd.DataFrame):
        """保存到pickle（向后兼容）"""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            cache_data = {"result": df, "save_time": datetime.now()}
            with open(self.cache_path, "wb") as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            print(f"  ⚠️  保存pickle缓存失败: {e}")

    def clear(self):
        """清除pickle缓存"""
        if self.cache_path.exists():
            self.cache_path.unlink()


class MemoryCache:
    """内存缓存实现"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._max_age = timedelta(hours=1)  # 内存缓存1小时

    def is_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False

        cache_data = self._cache[key]
        saved_time = cache_data.get("saved_time")
        if saved_time is None:
            return False

        return datetime.now() - saved_time < self._max_age

    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        if self.is_valid(key):
            return self._cache[key].get("data")
        return None

    def set(self, key: str, data: Any):
        """设置缓存数据"""
        self._cache[key] = {"data": data, "saved_time": datetime.now()}

    def clear(self, key: str = None):
        """清除缓存"""
        if key:
            if key in self._cache:
                del self._cache[key]
        else:
            self._cache.clear()


class MultiLevelCache:
    """多级缓存实现"""

    def __init__(self):
        self.memory_cache = MemoryCache()
        self.disk_cache = get_cache_manager_by_type("sqlite")

    def load(self) -> Optional[pd.DataFrame]:
        """加载缓存数据（优先内存缓存）"""
        # 先尝试内存缓存
        memory_data = self.memory_cache.get("panic_index")
        if memory_data is not None:
            print("✅ 使用内存缓存")
            return memory_data

        # 再尝试磁盘缓存
        disk_data = self.disk_cache.load()
        if disk_data is not None:
            # 加载到内存缓存
            self.memory_cache.set("panic_index", disk_data)
            print("✅ 使用磁盘缓存")
            return disk_data

        return None

    def save(self, df: pd.DataFrame):
        """保存数据到多级缓存"""
        # 保存到内存缓存
        self.memory_cache.set("panic_index", df)
        # 保存到磁盘缓存
        self.disk_cache.save(df)
        print("✅ 数据已保存到多级缓存")

    def clear(self):
        """清除所有缓存"""
        self.memory_cache.clear()
        self.disk_cache.clear()
        print("✅ 所有缓存已清除")


def get_cache_manager_by_type(cache_type: str) -> CacheManager:
    """根据类型获取缓存管理器"""
    if cache_type == "sqlite":
        return SQLiteCache()
    elif cache_type == "pickle":
        return PickleCache()
    else:
        return SQLiteCache()  # 默认


def get_cache_manager() -> MultiLevelCache:
    """获取缓存管理器实例"""
    return MultiLevelCache()


# 全局缓存管理器实例
cache_manager = get_cache_manager()

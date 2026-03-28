"""
数据库管理模块
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import pandas as pd

class Database:
    """SQLite数据库管理"""
    
    def __init__(self, db_path: str = "./data_cache/panic_index.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 恐慌指数主表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS panic_index (
                date TEXT PRIMARY KEY,
                panic_index REAL NOT NULL,
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
        
        # 交易信号表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                signal_type TEXT NOT NULL,  -- buy, sell, hold
                panic_index REAL,
                reason TEXT,
                executed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 回测结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                initial_capital REAL,
                final_capital REAL,
                total_return REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                win_rate REAL,
                trade_count INTEGER,
                params TEXT,  -- JSON格式存储策略参数
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON panic_index(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_signal_date ON signals(date)')
        
        conn.commit()
        conn.close()
    
    def save_panic_index(self, df: pd.DataFrame):
        """保存恐慌指数数据"""
        conn = sqlite3.connect(self.db_path)
        
        # 转换列名
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
        
        save_df = df.copy().reset_index()
        save_df['date'] = pd.to_datetime(save_df['date']).dt.strftime('%Y-%m-%d')
        
        for old, new in column_map.items():
            if old in save_df.columns:
                save_df.rename(columns={old: new}, inplace=True)
        
        # 插入或更新
        cols = ['date', 'panic_index', 'volatility', 'limit_ratio', 
                'limit_up', 'limit_down', 'futures_basis',
                'northbound_flow', 'southbound_flow',
                'hs300_close', 'sh_index_close', 'status']
        
        for _, row in save_df.iterrows():
            values = [row.get(c) for c in cols]
            placeholders = ', '.join(['?' for _ in cols])
            updates = ', '.join([f"{c}=excluded.{c}" for c in cols if c != 'date'])
            
            sql = f'''
                INSERT INTO panic_index ({', '.join(cols)})
                VALUES ({placeholders})
                ON CONFLICT(date) DO UPDATE SET {updates}
            '''
            conn.execute(sql, values)
        
        conn.commit()
        conn.close()
    
    def get_panic_index(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """查询恐慌指数数据"""
        conn = sqlite3.connect(self.db_path)
        
        query = "SELECT * FROM panic_index WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " ORDER BY date"
        
        df = pd.read_sql_query(query, conn, params=params, 
                              parse_dates=['date'], index_col='date')
        conn.close()
        return df
    
    def get_latest(self, days: int = 30) -> pd.DataFrame:
        """获取最近N天数据"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query('''
            SELECT * FROM panic_index
            ORDER BY date DESC
            LIMIT ?
        ''', conn, params=(days,), parse_dates=['date'], index_col='date')
        conn.close()
        return df.sort_index()
    
    def save_signal(self, date: str, signal_type: str, panic_index: float, reason: str = ""):
        """保存交易信号"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO signals (date, signal_type, panic_index, reason)
            VALUES (?, ?, ?, ?)
        ''', (date, signal_type, panic_index, reason))
        conn.commit()
        conn.close()
    
    def get_signals(self, limit: int = 100) -> pd.DataFrame:
        """获取历史交易信号"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query('''
            SELECT * FROM signals
            ORDER BY date DESC
            LIMIT ?
        ''', conn, params=(limit,), parse_dates=['date'])
        conn.close()
        return df
    
    def save_backtest_result(self, result: dict):
        """保存回测结果"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO backtest_results 
            (strategy_name, start_date, end_date, initial_capital, final_capital,
             total_return, max_drawdown, sharpe_ratio, win_rate, trade_count, params)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result['strategy_name'],
            result.get('start_date'),
            result.get('end_date'),
            result.get('initial_capital'),
            result.get('final_capital'),
            result.get('total_return'),
            result.get('max_drawdown'),
            result.get('sharpe_ratio'),
            result.get('win_rate'),
            result.get('trade_count'),
            result.get('params', '{}')
        ))
        conn.commit()
        conn.close()
    
    def get_backtest_results(self, strategy_name: str = None) -> pd.DataFrame:
        """获取回测历史"""
        conn = sqlite3.connect(self.db_path)
        
        if strategy_name:
            df = pd.read_sql_query('''
                SELECT * FROM backtest_results
                WHERE strategy_name = ?
                ORDER BY created_at DESC
            ''', conn, params=(strategy_name,))
        else:
            df = pd.read_sql_query('''
                SELECT * FROM backtest_results
                ORDER BY created_at DESC
            ''', conn)
        
        conn.close()
        return df

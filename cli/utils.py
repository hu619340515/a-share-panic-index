"""CLI工具函数"""

from data import data_manager


def fetch_all_data(days: int = 730):
    """获取所有数据源"""
    return data_manager.get_data(days)

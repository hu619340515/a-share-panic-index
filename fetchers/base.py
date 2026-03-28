"""
数据获取基类
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd

class DataFetcher(ABC):
    """数据获取器基类"""
    
    def __init__(self):
        self.raw_data: Dict[str, Any] = {}
        self.name = self.__class__.__name__
    
    @abstractmethod
    def fetch(self, start_date: datetime, end_date: datetime) -> Optional[pd.Series]:
        """获取数据"""
        pass
    
    def get_raw_data(self) -> Dict[str, Any]:
        """获取原始数据"""
        return self.raw_data

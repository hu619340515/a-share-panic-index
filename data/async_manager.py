"""
异步数据管理中心
"""

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from fetchers.index import IndexFetcher
from fetchers.limit_up import LimitUpDownFetcher
from fetchers.futures import FuturesFetcher
from fetchers.fund_flow import FundFlowFetcher
from data.cache import get_cache_manager
from data.database import Database


class AsyncDataManager:
    """异步数据管理中心"""

    def __init__(self):
        self.cache = get_cache_manager()
        self.database = Database()
        # 尝试使用Baostock作为指数数据源
        try:
            from fetchers.baostock_index import BaostockIndexFetcher
            self.fetchers = {
                "index": BaostockIndexFetcher(),  # 使用Baostock指数数据源
                "limit_up": LimitUpDownFetcher(),
                "futures": FuturesFetcher(),
                "fund_flow": FundFlowFetcher(),
            }
            print("✅ 使用Baostock指数数据源")
        except ImportError:
            # 如果Baostock不可用，使用默认数据源
            self.fetchers = {
                "index": IndexFetcher(),
                "limit_up": LimitUpDownFetcher(),
                "futures": FuturesFetcher(),
                "fund_flow": FundFlowFetcher(),
            }
            print("⚠️ Baostock不可用，使用默认指数数据源")

    async def fetch_with_timeout(
        self,
        fetcher_name: str,
        start_date: datetime,
        end_date: datetime,
        timeout: int = 30,
    ):
        """带超时的异步获取"""
        try:
            # 使用线程池执行同步代码
            loop = asyncio.get_event_loop()
            fetcher = self.fetchers[fetcher_name]

            # 转换为异步任务
            result = await asyncio.wait_for(
                loop.run_in_executor(None, fetcher.fetch, start_date, end_date),
                timeout=timeout,
            )
            return fetcher_name, result
        except asyncio.TimeoutError:
            print(f"  - {fetcher_name} 数据获取超时")
            return fetcher_name, None
        except Exception as e:
            print(f"  - {fetcher_name} 数据获取失败: {e}")
            return fetcher_name, None

    async def get_data(
        self, days: int = 730, use_cache: bool = True
    ) -> tuple[pd.DataFrame, dict]:
        """
        异步获取所有数据源

        Args:
            days: 获取天数
            use_cache: 是否使用缓存

        Returns:
            (DataFrame, dict): 数据和原始数据
        """
        # 尝试从缓存加载
        if use_cache:
            cached_data = self.cache.load()
            if cached_data is not None:
                print("✅ 使用缓存数据")
                return cached_data, {}

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        print(
            f"正在获取数据 ({start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')})..."
        )

        # 并行获取数据
        tasks = [
            self.fetch_with_timeout("index", start_date, end_date),
            self.fetch_with_timeout("limit_up", start_date, end_date),
            self.fetch_with_timeout("fund_flow", start_date, end_date),
        ]

        results = await asyncio.gather(*tasks)

        # 处理结果
        result = pd.DataFrame()
        raw_data = {}

        # 处理指数数据
        for fetcher_name, data in results:
            if fetcher_name == "index" and data is not None:
                result["iv"] = data
                raw_data.update(self.fetchers["index"].get_raw_data())
            elif fetcher_name == "limit_up" and data is not None:
                if isinstance(data, pd.DataFrame):
                    result = result.join(
                        data[["limit_ratio", "limit_up", "limit_down"]], how="outer"
                    )
                else:
                    # 如果是Series，只包含limit_ratio
                    result["limit_ratio"] = data
                raw_data.update(self.fetchers["limit_up"].get_raw_data())
            elif fetcher_name == "fund_flow" and data is not None:
                result["southbound_flow"] = data
                raw_data.update(self.fetchers["fund_flow"].get_raw_data())

        # 单独获取期货数据（因为依赖指数数据）
        if "hs300" in raw_data:
            try:
                print("  - 期货数据...", end="", flush=True)
                basis = self.fetchers["futures"].fetch(
                    start_date, end_date, raw_data.get("hs300")
                )
                if basis is not None:
                    result["futures_basis"] = basis
                print("✅")
            except Exception as e:
                print(f"⚠️ ({e})")

        # 归一化索引
        result.index = pd.to_datetime(result.index).normalize()
        result = result[~result.index.duplicated(keep="last")]
        result.sort_index(inplace=True)
        
        # 过滤非交易日（只保留至少有一个指标数据的日期）
        # 计算每行的非空值数量
        non_null_count = result.notnull().sum(axis=1)
        # 只保留至少有一个非空值的行
        result = result[non_null_count > 0]
        
        # 如果数据为空，返回空DataFrame
        if result.empty:
            print("⚠️ 没有有效数据，返回空DataFrame")

        # 过滤raw_data中的数据，只保留与result相同的日期
        filtered_raw_data = {}
        for key, data in raw_data.items():
            if isinstance(data, pd.Series) or isinstance(data, pd.DataFrame):
                # 只保留与result相同的日期
                filtered_raw_data[key] = data[data.index.isin(result.index)]
            else:
                filtered_raw_data[key] = data
        
        # 保存到缓存
        if use_cache:
            self.cache.save(result)

        # 保存到数据库
        self.database.save_panic_index(result)

        return result, filtered_raw_data

    def get_data_sync(
        self, days: int = 730, use_cache: bool = True
    ) -> tuple[pd.DataFrame, dict]:
        """
        同步接口，用于兼容现有代码

        Args:
            days: 获取天数
            use_cache: 是否使用缓存

        Returns:
            (DataFrame, dict): 数据和原始数据
        """
        return asyncio.run(self.get_data(days, use_cache))


# 全局异步数据管理器实例
async_data_manager = AsyncDataManager()

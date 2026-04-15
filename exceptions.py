"""自定义异常模块"""


class PanicIndexError(Exception):
    """恐慌指数基础异常"""

    pass


class DataFetchError(PanicIndexError):
    """数据获取异常"""

    pass


class ConfigError(PanicIndexError):
    """配置异常"""

    pass


class CalculationError(PanicIndexError):
    """计算异常"""

    pass


class DatabaseError(PanicIndexError):
    """数据库异常"""

    pass


class AlertError(PanicIndexError):
    """告警异常"""

    pass


class CacheError(PanicIndexError):
    """缓存异常"""

    pass

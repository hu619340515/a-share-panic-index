"""工具函数"""
import functools
import time
from typing import Callable, Any, TypeVar

from exceptions import PanicIndexError

T = TypeVar("T")


def error_handler(
    retry: int = 3, delay: int = 1
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    错误处理装饰器

    Args:
        retry: 重试次数
        delay: 重试延迟（秒）

    Returns:
        Callable: 装饰后的函数
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error = None

            for attempt in range(retry + 1):
                try:
                    return func(*args, **kwargs)
                except PanicIndexError as e:
                    last_error = e
                    print(f"错误: {e}")
                except Exception as e:
                    last_error = e
                    print(f"未预期的错误: {e}")

                if attempt < retry:
                    print(f"重试中... ({attempt + 1}/{retry})")
                    time.sleep(delay)

            # 所有重试都失败
            if last_error:
                raise last_error
            raise Exception("未知错误")

        return wrapper

    return decorator


def timeout_handler(
    timeout: int = 30,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    超时处理装饰器

    Args:
        timeout: 超时时间（秒）

    Returns:
        Callable: 装饰后的函数
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            import signal

            def handler(signum, frame):
                raise TimeoutError(f"函数 {func.__name__} 执行超时")

            signal.signal(signal.SIGALRM, handler)
            signal.alarm(timeout)

            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)

            return result

        return wrapper

    return decorator

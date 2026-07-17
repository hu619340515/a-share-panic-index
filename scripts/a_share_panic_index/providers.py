"""多数据源获取、校验、重试和硬超时。"""

from __future__ import annotations

import json
import io
import multiprocessing
import os
import queue
import random
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .models import ProviderResult


PROVIDER_CHAINS = {
    "index": [
        "baostock_volatility",
        "eastmoney_index_volatility",
        "sina_index_volatility",
        "tencent_index_realtime",
    ],
    "limit": ["jrj_limit_ratio", "eastmoney_limit_pool"],
    "futures": ["sina_futures_basis", "cffex_futures_basis"],
    "southbound": [
        "eastmoney_southbound_history",
        "eastmoney_southbound_summary",
    ],
}


class ProviderError(RuntimeError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderDataUnavailable(ProviderError):
    pass


def _fixture_result(provider: str, start: date, end: date) -> ProviderResult | None:
    fixture_path = os.environ.get("PANIC_INDEX_FIXTURE_FILE")
    if not fixture_path:
        return None
    with Path(fixture_path).open("r", encoding="utf-8") as file:
        payload = json.load(file).get("providers", {}).get(provider)
    if payload is None:
        raise ProviderError(f"测试夹具未定义数据源: {provider}")
    if payload.get("sleep"):
        time.sleep(float(payload["sleep"]))
    if payload.get("error"):
        raise ProviderError(str(payload["error"]))
    frame = pd.DataFrame(payload.get("records", []))
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame[
            frame["date"].dt.date.between(start, end, inclusive="both")
        ]
        frame.set_index("date", inplace=True)
    return ProviderResult(
        provider=provider,
        data=frame,
        provisional=bool(payload.get("provisional", False)),
    )


def _volatility_from_close(close: pd.Series, start: date, end: date) -> pd.DataFrame:
    prices = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    returns = prices.pct_change()
    volatility = returns.rolling(window=20).std() * (252**0.5)
    frame = pd.DataFrame({"volatility": volatility, "hs300_close": prices})
    return frame.loc[pd.Timestamp(start) : pd.Timestamp(end)]


def fetch_baostock_volatility(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("baostock_volatility", start, end)
    if fixture:
        return fixture
    import baostock as bs

    login = bs.login()
    if login.error_code != "0":
        raise ProviderError(f"Baostock登录失败: {login.error_msg}")
    try:
        query = bs.query_history_k_data_plus(
            "sh.000300",
            "date,close",
            start_date=(start - timedelta(days=40)).isoformat(),
            end_date=end.isoformat(),
            frequency="d",
            adjustflag="3",
        )
        if query.error_code != "0":
            raise ProviderError(f"Baostock取数失败: {query.error_msg}")
        records = []
        while query.next():
            records.append(query.get_row_data())
        frame = pd.DataFrame(records, columns=query.fields)
        if frame.empty:
            raise ProviderError("Baostock返回空数据")
        frame["date"] = pd.to_datetime(frame["date"])
        frame.set_index("date", inplace=True)
        data = _volatility_from_close(frame["close"], start, end)
        return ProviderResult("baostock_volatility", data, False)
    finally:
        bs.logout()


def fetch_eastmoney_index_volatility(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("eastmoney_index_volatility", start, end)
    if fixture:
        return fixture
    import akshare as ak

    frame = ak.stock_zh_index_daily_em(
        symbol="sh000300",
        start_date=(start - timedelta(days=40)).strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    if frame.empty:
        raise ProviderError("东方财富指数日线返回空数据")
    frame["date"] = pd.to_datetime(frame["date"])
    frame.set_index("date", inplace=True)
    return ProviderResult(
        "eastmoney_index_volatility",
        _volatility_from_close(frame["close"], start, end),
        True,
    )


def fetch_sina_index_volatility(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("sina_index_volatility", start, end)
    if fixture:
        return fixture
    import requests

    response = requests.get(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        params={"symbol": "sh000300", "scale": "240", "ma": "5", "datalen": "3000"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    frame = pd.DataFrame(response.json())
    if frame.empty:
        raise ProviderError("新浪指数日线返回空数据")
    frame["date"] = pd.to_datetime(frame["day"])
    frame.set_index("date", inplace=True)
    data = _volatility_from_close(frame["close"], start, end)
    return ProviderResult("sina_index_volatility", data, True)


def fetch_tencent_index_realtime(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("tencent_index_realtime", start, end)
    if fixture:
        return fixture
    import requests

    response = requests.get(
        "https://qt.gtimg.cn/q=sh000300",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    text = response.content.decode("gbk", errors="replace")
    try:
        fields = text.split('"', 2)[1].split("~")
        quote_date = datetime.strptime(fields[30][:8], "%Y%m%d").date()
        close = float(fields[3])
    except (IndexError, ValueError) as error:
        raise ProviderError("腾讯实时指数响应格式异常") from error
    if quote_date != target:
        raise ProviderError(f"腾讯实时指数日期为 {quote_date}，目标日期为 {target}")

    spot = _spot_series(context)
    spot.loc[pd.Timestamp(target)] = close
    data = _volatility_from_close(spot, target, target)
    if data["volatility"].dropna().empty:
        raise ProviderError("历史现货数据不足20个交易日，无法计算当日波动率")
    return ProviderResult("tencent_index_realtime", data, True)


def fetch_jrj_limit_ratio(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("jrj_limit_ratio", start, end)
    if fixture:
        return fixture
    import requests

    url = "https://gateway.jrj.com/quot-dc/zdt/market_history"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Referer": "https://summary.jrj.com.cn/",
        "Origin": "https://summary.jrj.com.cn",
        "productid": "6000021",
    }
    months = []
    current = start.replace(day=1)
    final_month = end.replace(day=1)
    while current <= final_month:
        months.append(current.strftime("%Y%m"))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

    records = []
    for year_month in months:
        response = requests.post(
            url,
            headers=headers,
            json={"yearMonth": year_month, "pageIndex": 1, "pageSize": 100},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 20000:
            continue
        for item in payload.get("data", {}).get("list", []):
            value_date = datetime.strptime(str(item["tradeDate"]), "%Y%m%d").date()
            if start <= value_date <= end:
                limit_up = int(item["upLimitCount"])
                limit_down = int(item["downLimitCount"])
                total = limit_up + limit_down
                records.append(
                    {
                        "date": value_date,
                        "limit_up": limit_up,
                        "limit_down": limit_down,
                        "limit_ratio": limit_down / total if total else 0.5,
                    }
                )
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ProviderError("金融界涨跌停历史返回空数据")
    frame["date"] = pd.to_datetime(frame["date"])
    frame.drop_duplicates("date", keep="last", inplace=True)
    frame.set_index("date", inplace=True)
    return ProviderResult("jrj_limit_ratio", frame, False)


def fetch_eastmoney_limit_pool(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("eastmoney_limit_pool", start, end)
    if fixture:
        return fixture
    import akshare as ak

    limit_up_frame = ak.stock_zt_pool_em(date=target.strftime("%Y%m%d"))
    limit_down_frame = ak.stock_zt_pool_dtgc_em(date=target.strftime("%Y%m%d"))
    limit_up = len(limit_up_frame)
    limit_down = len(limit_down_frame)
    total = limit_up + limit_down
    if total == 0:
        raise ProviderError("东方财富涨跌停池为空")
    frame = pd.DataFrame(
        {
            "limit_up": [limit_up],
            "limit_down": [limit_down],
            "limit_ratio": [limit_down / total],
        },
        index=pd.DatetimeIndex([pd.Timestamp(target)], name="date"),
    )
    return ProviderResult("eastmoney_limit_pool", frame, True)


def _spot_series(context: dict[str, Any]) -> pd.Series:
    records = context.get("spot_records", [])
    if not records:
        raise ProviderError("缺少沪深300现货价格")
    frame = pd.DataFrame(records)
    frame["date"] = pd.to_datetime(frame["date"])
    frame.set_index("date", inplace=True)
    return pd.to_numeric(frame["hs300_close"], errors="coerce").dropna()


def fetch_sina_futures_basis(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("sina_futures_basis", start, end)
    if fixture:
        return fixture
    import akshare as ak

    frame = ak.futures_main_sina(
        symbol="IF0",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    if frame.empty:
        raise ProviderError("新浪IF主力连续返回空数据")
    date_column = "日期" if "日期" in frame.columns else "date"
    close_column = "收盘价" if "收盘价" in frame.columns else "close"
    frame[date_column] = pd.to_datetime(frame[date_column])
    frame.set_index(date_column, inplace=True)
    futures_close = pd.to_numeric(frame[close_column], errors="coerce")
    spot = _spot_series(context)
    combined = pd.concat([spot.rename("spot"), futures_close.rename("futures")], axis=1).dropna()
    combined["futures_basis"] = (combined["spot"] - combined["futures"]) / combined["spot"]
    return ProviderResult(
        "sina_futures_basis",
        combined[["futures_basis"]].loc[pd.Timestamp(start) : pd.Timestamp(end)],
        False,
    )


def fetch_cffex_futures_basis(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("cffex_futures_basis", start, end)
    if fixture:
        return fixture
    import akshare as ak

    frame = ak.futures_hist_daily_cffex(date=target.strftime("%Y%m%d"))
    if frame.empty:
        raise ProviderError("中金所当日行情返回空数据")
    if "variety" in frame.columns:
        frame = frame[frame["variety"].astype(str).eq("IF")]
    else:
        frame = frame[frame["symbol"].astype(str).str.startswith("IF")]
    if frame.empty:
        raise ProviderError("中金所当日行情缺少IF合约")
    frame["open_interest"] = pd.to_numeric(frame["open_interest"], errors="coerce").fillna(0)
    contract = frame.sort_values(["open_interest", "volume"], ascending=False).iloc[0]
    spot = _spot_series(context)
    target_timestamp = pd.Timestamp(target)
    if target_timestamp not in spot.index:
        raise ProviderError("现货数据缺少目标交易日")
    spot_close = float(spot.loc[target_timestamp])
    futures_close = float(contract["close"])
    basis = (spot_close - futures_close) / spot_close
    data = pd.DataFrame(
        {"futures_basis": [basis]},
        index=pd.DatetimeIndex([target_timestamp], name="date"),
    )
    return ProviderResult("cffex_futures_basis", data, True)


def fetch_eastmoney_southbound_history(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("eastmoney_southbound_history", start, end)
    if fixture:
        return fixture
    import akshare as ak

    frame = ak.stock_hsgt_hist_em(symbol="南向资金")
    if frame.empty:
        raise ProviderError("东方财富南向资金历史返回空数据")
    frame["date"] = pd.to_datetime(frame["日期"])
    frame.set_index("date", inplace=True)
    data = pd.DataFrame(
        {"southbound_flow": pd.to_numeric(frame["当日成交净买额"], errors="coerce")}
    )
    return ProviderResult(
        "eastmoney_southbound_history",
        data.loc[pd.Timestamp(start) : pd.Timestamp(end)],
        False,
    )


def fetch_eastmoney_southbound_summary(start: date, end: date, target: date, context: dict) -> ProviderResult:
    fixture = _fixture_result("eastmoney_southbound_summary", start, end)
    if fixture:
        return fixture
    import akshare as ak

    frame = ak.stock_hsgt_fund_flow_summary_em()
    if frame.empty:
        raise ProviderError("东方财富南向资金摘要返回空数据")
    frame["交易日"] = pd.to_datetime(frame["交易日"])
    rows = frame[
        frame["资金方向"].astype(str).eq("南向")
        & frame["交易日"].dt.normalize().eq(pd.Timestamp(target))
    ]
    if rows.empty:
        raise ProviderError("南向资金摘要缺少目标交易日")
    value = pd.to_numeric(rows["成交净买额"], errors="coerce").sum(min_count=1)
    if pd.isna(value):
        raise ProviderError("南向资金摘要数值无效")
    data = pd.DataFrame(
        {"southbound_flow": [float(value)]},
        index=pd.DatetimeIndex([pd.Timestamp(target)], name="date"),
    )
    return ProviderResult("eastmoney_southbound_summary", data, True)


PROVIDERS: dict[str, Callable[[date, date, date, dict], ProviderResult]] = {
    "baostock_volatility": fetch_baostock_volatility,
    "eastmoney_index_volatility": fetch_eastmoney_index_volatility,
    "sina_index_volatility": fetch_sina_index_volatility,
    "tencent_index_realtime": fetch_tencent_index_realtime,
    "jrj_limit_ratio": fetch_jrj_limit_ratio,
    "eastmoney_limit_pool": fetch_eastmoney_limit_pool,
    "sina_futures_basis": fetch_sina_futures_basis,
    "cffex_futures_basis": fetch_cffex_futures_basis,
    "eastmoney_southbound_history": fetch_eastmoney_southbound_history,
    "eastmoney_southbound_summary": fetch_eastmoney_southbound_summary,
}


def _validate_result(result: ProviderResult) -> ProviderResult:
    frame = result.data.copy()
    if frame.empty:
        raise ProviderError(f"{result.provider} 返回空数据")
    frame.index = pd.to_datetime(frame.index).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.dropna(how="all", inplace=True)
    if frame.empty:
        raise ProviderError(f"{result.provider} 没有有效数值")
    if "volatility" in frame and not frame["volatility"].dropna().between(0, 5).all():
        raise ProviderError("波动率超出合理范围")
    if "limit_ratio" in frame and not frame["limit_ratio"].dropna().between(0, 1).all():
        raise ProviderError("涨跌停比超出合理范围")
    if "futures_basis" in frame and not frame["futures_basis"].dropna().between(-1, 1).all():
        raise ProviderError("期货基差超出合理范围")
    result.data = frame
    return result


def execute_provider(provider: str, start: date, end: date, target: date, context: dict) -> ProviderResult:
    try:
        function = PROVIDERS[provider]
    except KeyError as error:
        raise ProviderError(f"未知数据源: {provider}") from error
    return _validate_result(function(start, end, target, context))


def _process_worker(output_queue, provider: str, start: date, end: date, target: date, context: dict) -> None:
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = execute_provider(provider, start, end, target, context)
        output_queue.put(("ok", result))
    except Exception as error:
        output_queue.put(("error", type(error).__name__, str(error)))


class ProviderExecutor:
    def __init__(
        self,
        retries: int,
        retry_delay: float,
        timeout: float,
        logger,
        use_subprocess: bool = True,
    ):
        self.retries = retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.logger = logger
        self.use_subprocess = use_subprocess and os.environ.get(
            "PANIC_INDEX_DISABLE_SUBPROCESS"
        ) != "1"

    def run(
        self,
        provider: str,
        start: date,
        end: date,
        target: date,
        context: dict,
        deadline: float | None = None,
    ) -> ProviderResult:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                timeout = self.timeout
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ProviderTimeout("daily总超时")
                    timeout = min(timeout, remaining)
                result = self._run_once(provider, start, end, target, context, timeout)
                self.logger.info("数据源成功 provider=%s rows=%s", provider, len(result.data))
                return result
            except Exception as error:
                last_error = error
                self.logger.warning(
                    "数据源失败 provider=%s attempt=%s/%s error=%s",
                    provider,
                    attempt,
                    self.retries,
                    error,
                )
                if isinstance(error, (ProviderTimeout, ProviderDataUnavailable)):
                    break
                if attempt < self.retries:
                    delay = self.retry_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    if deadline is not None and time.monotonic() + delay >= deadline:
                        break
                    time.sleep(delay)
        raise ProviderError(f"{provider} 获取失败: {last_error}")

    def _run_once(
        self,
        provider: str,
        start: date,
        end: date,
        target: date,
        context: dict,
        timeout: float,
    ) -> ProviderResult:
        if not self.use_subprocess:
            return execute_provider(provider, start, end, target, context)

        process_context = multiprocessing.get_context("spawn")
        output_queue = process_context.Queue(maxsize=1)
        process = process_context.Process(
            target=_process_worker,
            args=(output_queue, provider, start, end, target, context),
            daemon=True,
        )
        process.start()
        try:
            payload = output_queue.get(timeout=timeout)
        except queue.Empty as error:
            if process.is_alive():
                process.terminate()
                process.join(5)
            raise ProviderTimeout(f"{provider} 超过 {timeout:.1f} 秒") from error
        finally:
            output_queue.close()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
        if payload[0] == "error":
            _, error_type, message = payload
            if error_type == "ProviderError":
                raise ProviderDataUnavailable(message)
            raise ProviderError(f"{error_type}: {message}")
        return payload[1]

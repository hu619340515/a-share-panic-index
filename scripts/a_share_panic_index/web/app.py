"""V3 HTTP API和单页Dashboard。"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from ..pipeline.realtime import RealtimePipeline


STATIC_ROOT = Path(__file__).resolve().parent / "static"


class RealtimeCollector:
    def __init__(self, settings, database, logger, fixture: str | None = None):
        self.settings = settings
        self.database = database
        self.logger = logger
        self.fixture = fixture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="panic-index-collector", daemon=True
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread:
            thread.join(timeout=5)

    def collect_once(self) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"status": "collector_busy"}
        try:
            timezone = ZoneInfo(self.settings.get("market.timezone"))
            result, meta = RealtimePipeline(
                self.settings, self.database, self.logger
            ).run(datetime.now(timezone), fixture=self.fixture)
            return result.to_dict() if result else meta
        finally:
            self._lock.release()

    def _loop(self) -> None:
        interval = int(self.settings.get("realtime.refresh_seconds"))
        while not self._stop.is_set():
            try:
                self.collect_once()
            except Exception as error:
                self.logger.exception("Dashboard实时采集失败: %s", error)
            self._stop.wait(interval)


def create_app(
    settings,
    database,
    logger,
    fixture: str | None = None,
    start_collector: bool = False,
) -> FastAPI:
    collector = RealtimeCollector(settings, database, logger, fixture)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_collector:
            collector.start()
        try:
            yield
        finally:
            collector.stop()

    app = FastAPI(title="A股实时恐慌指数", version="3.0", lifespan=lifespan)
    app.state.collector = collector

    @app.get("/api/v1/realtime")
    def realtime() -> dict[str, Any]:
        value = database.latest_realtime_with_aggregate()
        if value is None:
            raise HTTPException(status_code=404, detail="暂无盘中数据")
        return value

    @app.get("/api/v1/realtime/history")
    def realtime_history(
        trade_date: str | None = None,
        limit: int = Query(500, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return database.realtime_history(trade_date, limit)

    @app.get("/api/v1/daily/latest")
    def daily_latest() -> dict[str, Any]:
        value = database.latest_daily()
        if value is None:
            raise HTTPException(status_code=404, detail="暂无收盘正式数据")
        return value

    @app.get("/api/v1/daily/history")
    def daily_history(
        limit: int = Query(500, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return database.daily_history(limit=limit)

    @app.get("/api/v1/sources")
    def sources() -> dict[str, Any]:
        return {
            "health": database.provider_status(),
            "probe": database.probe_results(),
        }

    @app.get("/api/v1/reference")
    def reference() -> dict[str, Any]:
        latest = database.latest_realtime()
        return {
            "current_reference_mode": latest.get("reference_mode") if latest else None,
            "curves": database.reference_curves(),
        }

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "database_journal_mode": database.journal_mode(),
            "collector_running": bool(
                collector._thread and collector._thread.is_alive()
            ),
        }

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        path = STATIC_ROOT / "index.html"
        return HTMLResponse(path.read_text(encoding="utf-8"))

    return app

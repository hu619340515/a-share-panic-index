"""版本化 SQLite 数据库。"""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd


SCHEMA_VERSION = "3"


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path: Path | None = None
        self._prepare_schema()

    def _prepare_schema(self) -> None:
        if self.path.exists() and self.path.stat().st_size:
            try:
                with closing(sqlite3.connect(self.path)) as connection:
                    row = connection.execute(
                        "SELECT value FROM metadata WHERE key='schema_version'"
                    ).fetchone()
                if row and row[0] == SCHEMA_VERSION:
                    return
            except sqlite3.Error:
                pass

            backup_dir = self.path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_path = backup_dir / f"{self.path.stem}_{timestamp}{self.path.suffix}"
            shutil.copy2(self.path, self.backup_path)
            self.path.unlink()

        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_metrics (
                    date TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    source TEXT NOT NULL,
                    provisional INTEGER NOT NULL DEFAULT 0,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (date, metric)
                );

                CREATE TABLE IF NOT EXISTS panic_index (
                    date TEXT PRIMARY KEY,
                    panic_index REAL NOT NULL,
                    status TEXT NOT NULL,
                    volatility REAL NOT NULL,
                    limit_ratio REAL NOT NULL,
                    limit_up INTEGER,
                    limit_down INTEGER,
                    futures_basis REAL NOT NULL,
                    southbound_flow REAL NOT NULL,
                    quality_status TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_raw_metrics_date ON raw_metrics(date);
                """
            )
            now = datetime.now().isoformat()
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", SCHEMA_VERSION, now),
            )
            connection.commit()

    def latest_observation_date(self) -> pd.Timestamp | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT MAX(date) FROM raw_metrics").fetchone()
        return pd.Timestamp(row[0]) if row and row[0] else None

    def load_observations(self) -> pd.DataFrame:
        with closing(sqlite3.connect(self.path)) as connection:
            return pd.read_sql_query(
                "SELECT date, metric, value, source, provisional, fetched_at FROM raw_metrics",
                connection,
                parse_dates=["date", "fetched_at"],
            )

    def latest_snapshot(self) -> dict | None:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM panic_index ORDER BY date DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["sources"] = json.loads(result.pop("sources_json"))
        return result

    def persist(self, observations: pd.DataFrame, panic_rows: pd.DataFrame) -> dict[str, int]:
        now = datetime.now().isoformat()
        observation_count = 0
        panic_count = 0
        with closing(sqlite3.connect(self.path)) as connection:
            try:
                connection.execute("BEGIN")
                for row in observations.itertuples(index=False):
                    connection.execute(
                        """
                        INSERT INTO raw_metrics(date, metric, value, source, provisional, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(date, metric) DO UPDATE SET
                            value=excluded.value,
                            source=excluded.source,
                            provisional=excluded.provisional,
                            fetched_at=excluded.fetched_at
                        """,
                        (
                            pd.Timestamp(row.date).strftime("%Y-%m-%d"),
                            row.metric,
                            float(row.value),
                            row.source,
                            int(bool(row.provisional)),
                            pd.Timestamp(row.fetched_at).isoformat(),
                        ),
                    )
                    observation_count += 1

                for index, row in panic_rows.iterrows():
                    connection.execute(
                        """
                        INSERT INTO panic_index(
                            date, panic_index, status, volatility, limit_ratio,
                            limit_up, limit_down, futures_basis, southbound_flow,
                            quality_status, sources_json, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(date) DO UPDATE SET
                            panic_index=excluded.panic_index,
                            status=excluded.status,
                            volatility=excluded.volatility,
                            limit_ratio=excluded.limit_ratio,
                            limit_up=excluded.limit_up,
                            limit_down=excluded.limit_down,
                            futures_basis=excluded.futures_basis,
                            southbound_flow=excluded.southbound_flow,
                            quality_status=excluded.quality_status,
                            sources_json=excluded.sources_json,
                            updated_at=excluded.updated_at
                        """,
                        (
                            pd.Timestamp(index).strftime("%Y-%m-%d"),
                            float(row["panic_index"]),
                            row["status"],
                            float(row["volatility"]),
                            float(row["limit_ratio"]),
                            _nullable_int(row.get("limit_up")),
                            _nullable_int(row.get("limit_down")),
                            float(row["futures_basis"]),
                            float(row["southbound_flow"]),
                            row["quality_status"],
                            json.dumps(row["sources"], ensure_ascii=False, sort_keys=True),
                            now,
                        ),
                    )
                    panic_count += 1

                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES (?, ?, ?)",
                    ("last_successful_update", now, now),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return {"observations_upserted": observation_count, "panic_rows_upserted": panic_count}


def _nullable_int(value):
    if value is None or pd.isna(value):
        return None
    return int(value)

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

from app.config import get_settings
from app.schemas import ReportBlock, ReportCreate, ReportDetail, ReportSummary, ReportUpdate


class ReportStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.db_path = self.settings.database_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    blocks_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_updated_at ON reports(updated_at)")

    def list_reports(self) -> list[ReportSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, blocks_json, created_at, updated_at FROM reports ORDER BY updated_at DESC"
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    def create_report(self, payload: ReportCreate) -> ReportDetail:
        now = _now()
        blocks_json = _blocks_to_json(payload.blocks)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO reports (title, blocks_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (payload.title, blocks_json, now, now),
            )
            report_id = int(cursor.lastrowid)
        return self.get_report(report_id)

    def get_report(self, report_id: int) -> ReportDetail:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, blocks_json, created_at, updated_at FROM reports WHERE id = ?",
                (report_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Report not found: {report_id}")
        return self._detail_from_row(row)

    def update_report(self, report_id: int, payload: ReportUpdate) -> ReportDetail:
        now = _now()
        blocks_json = _blocks_to_json(payload.blocks)
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE reports SET title = ?, blocks_json = ?, updated_at = ? WHERE id = ?",
                (payload.title, blocks_json, now, report_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"Report not found: {report_id}")
        return self.get_report(report_id)

    def delete_report(self, report_id: int) -> None:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        if cursor.rowcount == 0:
            raise KeyError(f"Report not found: {report_id}")

    def _summary_from_row(self, row: sqlite3.Row) -> ReportSummary:
        blocks = _json_to_blocks(row["blocks_json"])
        return ReportSummary(
            id=int(row["id"]),
            title=str(row["title"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            block_count=len(blocks),
        )

    def _detail_from_row(self, row: sqlite3.Row) -> ReportDetail:
        blocks = _json_to_blocks(row["blocks_json"])
        return ReportDetail(
            id=int(row["id"]),
            title=str(row["title"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            block_count=len(blocks),
            blocks=blocks,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blocks_to_json(blocks: list[ReportBlock]) -> str:
    return json.dumps([block.model_dump() for block in blocks], ensure_ascii=False)


def _json_to_blocks(value: str) -> list[ReportBlock]:
    raw = json.loads(value or "[]")
    return [ReportBlock(**item) for item in raw]

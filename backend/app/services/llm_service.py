from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import urllib.error
import urllib.request
from typing import Any

from app.config import get_settings
from app.schemas import QueryResponse

FREE_USAGE_MESSAGE = "무료 AI 사용량이 모두 소진되었습니다. 차트 조회와 보고서 편집은 계속 사용할 수 있습니다. 내일 다시 이용해주세요."


def maybe_enhance_with_llm(result: QueryResponse, user_key: str | None) -> QueryResponse:
    settings = get_settings()
    if not settings.gemini_api_key:
        result.llm_status = "not_configured"
        result.llm_message = "Gemini API 키가 없어 결정론적 분석 설명을 사용했습니다."
        return result

    limiter = UsageLimiter()
    allowed, message = limiter.can_call(user_key)
    if not allowed:
        result.llm_status = "quota_exhausted"
        result.llm_message = message
        return result

    try:
        generated = _call_gemini(result)
    except QuotaExhaustedError:
        result.llm_status = "quota_exhausted"
        result.llm_message = FREE_USAGE_MESSAGE
        return result
    except Exception as exc:  # pragma: no cover - external service boundary
        result.llm_status = "failed"
        result.llm_message = f"LLM 호출에 실패해 기본 분석 설명을 사용했습니다: {exc}"
        return result

    limiter.record_call(user_key)
    if generated.get("answer"):
        result.answer = str(generated["answer"]).strip()
    suggestions = generated.get("suggestions")
    if isinstance(suggestions, list) and suggestions:
        result.suggestions = [str(item).strip() for item in suggestions if str(item).strip()][:5]
    result.llm_status = "used"
    result.llm_message = "Gemini가 분석 설명과 다음 질문을 다듬었습니다."
    return result


class QuotaExhaustedError(RuntimeError):
    pass


class UsageLimiter:
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
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usage_date TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_date ON llm_usage(usage_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_user_date ON llm_usage(user_key, usage_date)")

    def can_call(self, user_key: str | None) -> tuple[bool, str | None]:
        user = _normalize_user_key(user_key)
        today = _today()
        with self._connect() as conn:
            global_count = conn.execute(
                "SELECT COUNT(*) AS count FROM llm_usage WHERE usage_date = ?", (today,)
            ).fetchone()["count"]
            user_count = conn.execute(
                "SELECT COUNT(*) AS count FROM llm_usage WHERE usage_date = ? AND user_key = ?", (today, user)
            ).fetchone()["count"]

        if global_count >= self.settings.llm_daily_global_limit:
            return False, FREE_USAGE_MESSAGE
        if user_count >= self.settings.llm_daily_user_limit:
            return False, FREE_USAGE_MESSAGE
        return True, None

    def record_call(self, user_key: str | None) -> None:
        user = _normalize_user_key(user_key)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO llm_usage (usage_date, user_key, created_at) VALUES (?, ?, ?)",
                (_today(), user, now),
            )


def _normalize_user_key(user_key: str | None) -> str:
    value = (user_key or "anonymous").strip()
    return value[:120] or "anonymous"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _call_gemini(result: QueryResponse) -> dict[str, Any]:
    settings = get_settings()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    prompt = _build_prompt(result)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": settings.llm_max_output_tokens,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.gemini_timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise QuotaExhaustedError() from exc
        error_body = exc.read().decode("utf-8", errors="ignore")
        if "RESOURCE_EXHAUSTED" in error_body or "quota" in error_body.lower():
            raise QuotaExhaustedError() from exc
        raise RuntimeError(f"Gemini HTTP {exc.code}") from exc

    text = _extract_text(body)
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"answer": text, "suggestions": result.suggestions}


def _extract_text(body: dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(str(part.get("text", "")) for part in parts).strip()


def _build_prompt(result: QueryResponse) -> str:
    compact = {
        "question": result.question,
        "intent": result.intent,
        "title": result.title,
        "base_answer": result.answer,
        "metrics": [metric.model_dump() for metric in result.metrics],
        "table_sample": result.table[:5],
        "evidence": result.evidence.model_dump(),
        "chart_titles": [chart.title for chart in result.charts],
    }
    return (
        "너는 제조 설비 데이터 분석 Copilot이다. "
        "아래 결정론적 분석 결과를 바탕으로 한국어 보고서형 답변을 작성해라. "
        "숫자는 제공된 값만 사용하고 새로운 수치를 만들어내지 마라. "
        "원인 해석, 상태 판단, 권장 조치를 간결하게 포함해라. "
        "반드시 JSON으로만 응답해라. 형식: "
        "{\"answer\": \"...\", \"suggestions\": [\"...\", \"...\", \"...\"]}.\n\n"
        f"분석 결과:\n{json.dumps(compact, ensure_ascii=False)}"
    )

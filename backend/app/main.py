from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config import get_settings
from app.schemas import QueryRequest, QueryResponse, ReportCreate, ReportDetail, ReportSummary, ReportUpdate
from app.services.data_service import analyze_question, get_dataset_summary
from app.services.docx_export import build_docx
from app.services.llm_service import maybe_enhance_with_llm
from app.services.report_store import ReportStore

settings = get_settings()
app = FastAPI(title="Manufacturing Insight AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _user_key(request: Request, explicit: str | None) -> str:
    if explicit:
        return explicit
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "anonymous"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary")
def summary() -> dict:
    return get_dataset_summary()


@app.post("/api/query", response_model=QueryResponse)
def query(payload: QueryRequest, request: Request) -> QueryResponse:
    result = analyze_question(payload.question)
    return maybe_enhance_with_llm(result, _user_key(request, payload.user_key))


@app.get("/api/reports", response_model=list[ReportSummary])
def list_reports() -> list[ReportSummary]:
    return ReportStore().list_reports()


@app.post("/api/reports", response_model=ReportDetail)
def create_report(payload: ReportCreate) -> ReportDetail:
    return ReportStore().create_report(payload)


@app.get("/api/reports/{report_id}", response_model=ReportDetail)
def get_report(report_id: int) -> ReportDetail:
    try:
        return ReportStore().get_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/reports/{report_id}", response_model=ReportDetail)
def update_report(report_id: int, payload: ReportUpdate) -> ReportDetail:
    try:
        return ReportStore().update_report(report_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int) -> dict[str, bool]:
    try:
        ReportStore().delete_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/reports/{report_id}/export/docx")
def export_docx(report_id: int) -> Response:
    try:
        report = ReportStore().get_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = build_docx(report)
    safe_name = f"manufacturing-insight-ai-report-{report_id}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


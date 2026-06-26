from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

ChartType = Literal["bar", "horizontal_bar", "donut", "line", "scatter", "table", "kpi"]
BlockType = Literal["title", "summary", "answer", "kpi", "chart", "table", "recommendation", "suggestions"]


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    user_key: str | None = Field(default=None, max_length=120)


class MetricCard(BaseModel):
    label: str
    value: str | float | int
    helper: str | None = None
    tone: Literal["neutral", "good", "warning", "danger"] = "neutral"


class ChartSpec(BaseModel):
    id: str
    title: str
    type: ChartType
    allowed_types: list[ChartType]
    x_key: str | None = None
    y_key: str | None = None
    category_key: str | None = None
    value_key: str | None = None
    data: list[dict[str, Any]]
    reason: str


class AnalysisEvidence(BaseModel):
    dataset_rows: int
    used_columns: list[str]
    filters: list[str] = []
    method: str


class QueryResponse(BaseModel):
    intent: str
    question: str
    title: str
    answer: str
    metrics: list[MetricCard]
    charts: list[ChartSpec]
    table: list[dict[str, Any]]
    evidence: AnalysisEvidence
    suggestions: list[str]
    llm_status: Literal["not_configured", "used", "quota_exhausted", "failed", "skipped"]
    llm_message: str | None = None


class ReportBlock(BaseModel):
    id: str
    type: BlockType
    title: str
    content: dict[str, Any]


class ReportCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    blocks: list[ReportBlock] = []


class ReportUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    blocks: list[ReportBlock] = []


class ReportSummary(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    block_count: int


class ReportDetail(ReportSummary):
    blocks: list[ReportBlock]

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import csv
import re
from statistics import mean
from typing import Any

from app.config import get_settings
from app.schemas import AnalysisEvidence, ChartSpec, MetricCard, QueryResponse


COL_PRODUCTION = "(*)Production_Qty"
COL_AVAILABILITY = "(*)Availability"
COL_QUALITY = "(*)Quality_Rate"
COL_DEFECT = "(*)Defect_Rate"
COL_PERFORMANCE = "(*)Performance"
COL_OEE = "(*)OEE"
COL_RISK = "(*)Risk_Level"
COL_PRIORITY = "(*)Maintenance_Priority"
COL_EQUIPMENT = "(*)Equipment_ID"
COL_LINE = "(*)Line"
COL_TOOL_WEAR = "Tool wear [min]"
COL_TORQUE = "Torque [Nm]"
COL_PROCESS_TEMP = "Process temperature [K]"
COL_SPEED = "Rotational speed [rpm]"
COL_FAILURE = "Machine failure"

NUMERIC_COLUMNS = {
    COL_PRODUCTION,
    COL_AVAILABILITY,
    COL_QUALITY,
    COL_DEFECT,
    COL_PERFORMANCE,
    COL_OEE,
    COL_TOOL_WEAR,
    COL_TORQUE,
    COL_PROCESS_TEMP,
    COL_SPEED,
    COL_FAILURE,
}

RISK_ORDER = {"Low": 1, "Medium": 2, "Warning": 3, "High": 4}
PRIORITY_ORDER = {"Normal": 1, "Plan": 2, "Urgent": 3, "Immediate": 4}
FREE_USAGE_MESSAGE = "무료 AI 사용량이 모두 소진되었습니다. 차트 조회와 보고서 편집은 계속 사용할 수 있습니다. 내일 다시 이용해주세요."


@dataclass(frozen=True)
class Dataset:
    rows: list[dict[str, Any]]
    columns: list[str]


@lru_cache(maxsize=1)
def load_dataset() -> Dataset:
    settings = get_settings()
    path = settings.dataset_path
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for raw in reader:
            row: dict[str, Any] = {}
            for key, value in raw.items():
                if key in NUMERIC_COLUMNS:
                    row[key] = _to_float(value)
                else:
                    row[key] = value
            rows.append(row)
        columns = list(reader.fieldnames or [])
    return Dataset(rows=rows, columns=columns)


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def _pct(value: float, digits: int = 1) -> str:
    return f"{_round(value, digits)}%"


def _avg(rows: list[dict[str, Any]], column: str) -> float:
    if not rows:
        return 0.0
    return mean(float(row[column]) for row in rows)


def _count_by(rows: list[dict[str, Any]], column: str, order: dict[str, int] | None = None) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row[column])
        counts[key] = counts.get(key, 0) + 1
    items = [{column: key, "count": value} for key, value in counts.items()]
    if order:
        items.sort(key=lambda item: order.get(str(item[column]), 999))
    else:
        items.sort(key=lambda item: str(item[column]))
    return items


def _top_low_oee(rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda row: float(row[COL_OEE]))[:limit]
    return [_equipment_row(row) for row in sorted_rows]


def _top_priority(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            PRIORITY_ORDER.get(str(row[COL_PRIORITY]), 0),
            RISK_ORDER.get(str(row[COL_RISK]), 0),
            -float(row[COL_OEE]),
        ),
        reverse=True,
    )[:limit]
    return [_equipment_row(row) for row in sorted_rows]


def _equipment_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "equipmentId": row[COL_EQUIPMENT],
        "line": row[COL_LINE],
        "oee": _round(row[COL_OEE], 2),
        "riskLevel": row[COL_RISK],
        "maintenancePriority": row[COL_PRIORITY],
        "availability": _round(row[COL_AVAILABILITY], 2),
        "qualityRate": _round(row[COL_QUALITY], 2),
        "productionQty": _round(row[COL_PRODUCTION], 2),
        "toolWear": _round(row[COL_TOOL_WEAR], 2),
        "torque": _round(row[COL_TORQUE], 2),
        "processTemp": _round(row[COL_PROCESS_TEMP], 2),
        "rotationalSpeed": _round(row[COL_SPEED], 2),
        "machineFailure": int(row[COL_FAILURE]),
    }


def get_dataset_summary() -> dict[str, Any]:
    dataset = load_dataset()
    rows = dataset.rows
    high_count = sum(1 for row in rows if row[COL_RISK] == "High")
    return {
        "rowCount": len(rows),
        "lineCount": len({row[COL_LINE] for row in rows}),
        "equipmentCount": len({row[COL_EQUIPMENT] for row in rows}),
        "avgOee": _round(_avg(rows, COL_OEE), 2),
        "avgAvailability": _round(_avg(rows, COL_AVAILABILITY), 2),
        "avgQualityRate": _round(_avg(rows, COL_QUALITY), 2),
        "highRiskCount": high_count,
        "riskDistribution": _count_by(rows, COL_RISK, RISK_ORDER),
        "lineDistribution": _count_by(rows, COL_LINE),
        "topLowOee": _top_low_oee(rows, 5),
    }


def analyze_question(question: str) -> QueryResponse:
    normalized = question.strip()
    dataset = load_dataset()
    rows = dataset.rows
    equipment_match = re.search(r"MC-?\s*(\d+)", normalized, flags=re.IGNORECASE)
    line_match = re.search(r"Line\s*(101|102|201)|라인\s*(101|102|201)", normalized, flags=re.IGNORECASE)

    if equipment_match:
        equipment_id = f"MC-{equipment_match.group(1)}"
        return _equipment_analysis(normalized, rows, equipment_id)
    if line_match:
        line_no = line_match.group(1) or line_match.group(2)
        return _line_analysis(normalized, rows, f"Line {line_no}")
    if any(keyword in normalized.lower() for keyword in ["정비", "점검", "maintenance", "priority", "우선"]):
        return _maintenance_analysis(normalized, rows)
    if any(keyword in normalized.lower() for keyword in ["위험", "risk", "high"]):
        return _risk_analysis(normalized, rows)
    if any(keyword in normalized.lower() for keyword in ["생산", "production", "불량", "defect"]):
        return _production_analysis(normalized, rows)
    if "oee" in normalized.lower() or "효율" in normalized:
        return _oee_analysis(normalized, rows)
    return _overview_analysis(normalized, rows)


def _overview_analysis(question: str, rows: list[dict[str, Any]]) -> QueryResponse:
    risk_data = _count_by(rows, COL_RISK, RISK_ORDER)
    line_data = _line_oee_data(rows)
    avg_oee = _avg(rows, COL_OEE)
    high_count = sum(1 for row in rows if row[COL_RISK] == "High")
    answer = (
        f"전체 {len(rows):,}대 설비의 평균 OEE는 {_pct(avg_oee, 2)}입니다. "
        f"High 위험 설비는 {high_count:,}대로, 우선 점검 후보를 별도로 확인하는 것이 좋습니다. "
        "라인별 평균 OEE와 위험도 분포를 함께 보면 운영 효율과 리스크를 동시에 파악할 수 있습니다."
    )
    return QueryResponse(
        intent="overview",
        question=question,
        title="전체 설비 운영 개요",
        answer=answer,
        metrics=[
            MetricCard(label="전체 설비", value=f"{len(rows):,}대"),
            MetricCard(label="평균 OEE", value=_pct(avg_oee, 2), tone="good" if avg_oee >= 70 else "warning"),
            MetricCard(label="High Risk", value=f"{high_count:,}대", tone="danger" if high_count else "neutral"),
            MetricCard(label="평균 가동률", value=_pct(_avg(rows, COL_AVAILABILITY), 2)),
        ],
        charts=[
            ChartSpec(
                id="line-oee",
                title="라인별 평균 OEE",
                type="bar",
                allowed_types=["bar", "horizontal_bar", "line", "table"],
                x_key="line",
                y_key="avgOee",
                data=line_data,
                reason="라인별 비교에는 막대 차트가 가장 직관적입니다.",
            ),
            ChartSpec(
                id="risk-distribution",
                title="위험도 분포",
                type="donut",
                allowed_types=["donut", "bar", "table"],
                category_key=COL_RISK,
                value_key="count",
                data=risk_data,
                reason="위험도 구성 비율은 도넛 차트가 한눈에 보기 좋습니다.",
            ),
        ],
        table=_top_low_oee(rows, 8),
        evidence=_evidence(rows, [COL_OEE, COL_RISK, COL_LINE, COL_AVAILABILITY], [], "전체 평균과 그룹 집계를 계산했습니다."),
        suggestions=[
            "OEE가 가장 낮은 설비를 알려줘",
            "High Risk 설비의 특징은 뭐야?",
            "Line 201 상태를 분석해줘",
        ],
        llm_status="skipped",
    )


def _oee_analysis(question: str, rows: list[dict[str, Any]]) -> QueryResponse:
    low_rows = _top_low_oee(rows, 10)
    avg_oee = _avg(rows, COL_OEE)
    worst = low_rows[0]
    answer = (
        f"평균 OEE는 {_pct(avg_oee, 2)}이며, 가장 낮은 설비는 {worst['equipmentId']}입니다. "
        f"해당 설비의 OEE는 {worst['oee']}%, 위험도는 {worst['riskLevel']}, 정비 우선순위는 {worst['maintenancePriority']}입니다. "
        "OEE 저하는 가동률, 성능, 품질률 중 하나 이상이 낮아졌을 때 발생하므로 하위 설비를 우선 확인해야 합니다."
    )
    return QueryResponse(
        intent="oee_analysis",
        question=question,
        title="OEE 하위 설비 분석",
        answer=answer,
        metrics=[
            MetricCard(label="평균 OEE", value=_pct(avg_oee, 2)),
            MetricCard(label="최저 OEE 설비", value=worst["equipmentId"], tone="danger"),
            MetricCard(label="최저 OEE", value=f"{worst['oee']}%", tone="danger"),
        ],
        charts=[
            ChartSpec(
                id="low-oee-ranking",
                title="OEE 하위 설비 Top 10",
                type="horizontal_bar",
                allowed_types=["horizontal_bar", "bar", "table"],
                x_key="equipmentId",
                y_key="oee",
                data=low_rows,
                reason="설비 순위 비교에는 가로 막대 차트가 읽기 쉽습니다.",
            )
        ],
        table=low_rows,
        evidence=_evidence(rows, [COL_EQUIPMENT, COL_OEE, COL_RISK, COL_PRIORITY], [], "OEE 오름차순으로 설비를 정렬했습니다."),
        suggestions=["가장 위험한 설비를 알려줘", "정비 우선순위를 추천해줘", "OEE가 낮은 원인이 뭐야?"],
        llm_status="skipped",
    )


def _risk_analysis(question: str, rows: list[dict[str, Any]]) -> QueryResponse:
    risk_data = _count_by(rows, COL_RISK, RISK_ORDER)
    high_rows = [row for row in rows if row[COL_RISK] == "High"]
    top = _top_priority(high_rows or rows, 10)
    answer = (
        f"High Risk 설비는 {len(high_rows):,}대입니다. "
        "위험 설비는 OEE가 낮고 정비 우선순위가 높은 장비를 먼저 보는 것이 좋습니다. "
        f"현재 최우선 후보는 {top[0]['equipmentId']}이며 {top[0]['maintenancePriority']} 점검이 권장됩니다."
    )
    return QueryResponse(
        intent="risk_detection",
        question=question,
        title="위험 설비 탐지",
        answer=answer,
        metrics=[
            MetricCard(label="High Risk", value=f"{len(high_rows):,}대", tone="danger"),
            MetricCard(label="Warning 이상", value=f"{sum(1 for row in rows if RISK_ORDER.get(str(row[COL_RISK]), 0) >= 3):,}대", tone="warning"),
            MetricCard(label="최우선 점검", value=top[0]["equipmentId"], tone="danger"),
        ],
        charts=[
            ChartSpec(
                id="risk-distribution",
                title="위험도 분포",
                type="donut",
                allowed_types=["donut", "bar", "table"],
                category_key=COL_RISK,
                value_key="count",
                data=risk_data,
                reason="위험도 단계의 비중을 보여주기 위해 도넛 차트를 추천합니다.",
            )
        ],
        table=top,
        evidence=_evidence(rows, [COL_RISK, COL_PRIORITY, COL_OEE, COL_EQUIPMENT], ["Risk_Level = High 우선"], "위험도와 정비 우선순위를 기준으로 후보를 정렬했습니다."),
        suggestions=["High Risk 설비의 공통점은 뭐야?", "어떤 설비를 먼저 점검해야 해?", "라인별 위험 설비 수를 보여줘"],
        llm_status="skipped",
    )


def _maintenance_analysis(question: str, rows: list[dict[str, Any]]) -> QueryResponse:
    priority_data = _count_by(rows, COL_PRIORITY, PRIORITY_ORDER)
    top = _top_priority(rows, 10)
    answer = (
        f"정비 우선순위가 가장 높은 설비는 {top[0]['equipmentId']}입니다. "
        f"해당 설비는 {top[0]['riskLevel']} 위험 수준이며, {top[0]['maintenancePriority']} 점검이 권장됩니다. "
        "정비 계획은 Immediate, Urgent, Plan 순서로 점검 대상을 좁히는 방식이 적합합니다."
    )
    return QueryResponse(
        intent="maintenance_priority",
        question=question,
        title="정비 우선순위 추천",
        answer=answer,
        metrics=[
            MetricCard(label="Immediate", value=f"{sum(1 for row in rows if row[COL_PRIORITY] == 'Immediate'):,}대", tone="danger"),
            MetricCard(label="Urgent", value=f"{sum(1 for row in rows if row[COL_PRIORITY] == 'Urgent'):,}대", tone="warning"),
            MetricCard(label="1순위 설비", value=top[0]["equipmentId"], tone="danger"),
        ],
        charts=[
            ChartSpec(
                id="maintenance-distribution",
                title="정비 우선순위 분포",
                type="bar",
                allowed_types=["bar", "donut", "table"],
                x_key=COL_PRIORITY,
                y_key="count",
                category_key=COL_PRIORITY,
                value_key="count",
                data=priority_data,
                reason="우선순위 단계별 수량 비교에는 막대 차트가 적합합니다.",
            )
        ],
        table=top,
        evidence=_evidence(rows, [COL_PRIORITY, COL_RISK, COL_OEE, COL_EQUIPMENT], [], "정비 우선순위와 위험도 기준으로 설비를 정렬했습니다."),
        suggestions=["Immediate 설비만 보여줘", "정비 대상의 OEE는 어느 정도야?", "Line 101에서 먼저 점검할 설비는?"],
        llm_status="skipped",
    )


def _line_analysis(question: str, rows: list[dict[str, Any]], line: str) -> QueryResponse:
    line_rows = [row for row in rows if row[COL_LINE] == line]
    if not line_rows:
        return _overview_analysis(question, rows)
    risk_data = _count_by(line_rows, COL_RISK, RISK_ORDER)
    top = _top_low_oee(line_rows, 8)
    answer = (
        f"{line}에는 {len(line_rows):,}대의 설비가 있으며 평균 OEE는 {_pct(_avg(line_rows, COL_OEE), 2)}입니다. "
        f"High Risk 설비는 {sum(1 for row in line_rows if row[COL_RISK] == 'High'):,}대입니다. "
        "라인 평가는 평균 OEE와 위험 설비 비율을 함께 확인하는 방식이 좋습니다."
    )
    return QueryResponse(
        intent="line_analysis",
        question=question,
        title=f"{line} 라인 분석",
        answer=answer,
        metrics=[
            MetricCard(label="설비 수", value=f"{len(line_rows):,}대"),
            MetricCard(label="평균 OEE", value=_pct(_avg(line_rows, COL_OEE), 2)),
            MetricCard(label="High Risk", value=f"{sum(1 for row in line_rows if row[COL_RISK] == 'High'):,}대", tone="danger"),
            MetricCard(label="평균 불량률", value=_pct(_avg(line_rows, COL_DEFECT), 2)),
        ],
        charts=[
            ChartSpec(
                id="line-risk-distribution",
                title=f"{line} 위험도 분포",
                type="donut",
                allowed_types=["donut", "bar", "table"],
                category_key=COL_RISK,
                value_key="count",
                data=risk_data,
                reason="라인 내부 위험도 구성은 도넛 차트가 적합합니다.",
            )
        ],
        table=top,
        evidence=_evidence(line_rows, [COL_LINE, COL_OEE, COL_RISK, COL_DEFECT], [f"Line = {line}"], "선택 라인의 평균 KPI와 위험도 분포를 계산했습니다."),
        suggestions=[f"{line}에서 OEE가 가장 낮은 설비는?", f"{line} 정비 우선순위를 알려줘", "다른 라인과 비교해줘"],
        llm_status="skipped",
    )


def _equipment_analysis(question: str, rows: list[dict[str, Any]], equipment_id: str) -> QueryResponse:
    match = next((row for row in rows if str(row[COL_EQUIPMENT]).lower() == equipment_id.lower()), None)
    if not match:
        return _overview_analysis(question, rows)
    equipment = _equipment_row(match)
    answer = (
        f"{equipment_id} 설비의 OEE는 {equipment['oee']}%이며 위험도는 {equipment['riskLevel']}입니다. "
        f"정비 우선순위는 {equipment['maintenancePriority']}이고, 가동률은 {equipment['availability']}%, 품질률은 {equipment['qualityRate']}%입니다. "
        "공구 마모, 토크, 가동률을 함께 확인해 점검 필요성을 판단하는 것이 좋습니다."
    )
    kpi_data = [
        {"metric": "OEE", "value": equipment["oee"]},
        {"metric": "Availability", "value": equipment["availability"]},
        {"metric": "Quality", "value": equipment["qualityRate"]},
        {"metric": "Production", "value": equipment["productionQty"]},
    ]
    return QueryResponse(
        intent="equipment_status",
        question=question,
        title=f"{equipment_id} 설비 상태",
        answer=answer,
        metrics=[
            MetricCard(label="OEE", value=f"{equipment['oee']}%", tone="danger" if equipment["riskLevel"] == "High" else "neutral"),
            MetricCard(label="Risk", value=equipment["riskLevel"], tone="danger" if equipment["riskLevel"] == "High" else "warning"),
            MetricCard(label="정비 우선순위", value=equipment["maintenancePriority"]),
            MetricCard(label="공구 마모", value=equipment["toolWear"]),
        ],
        charts=[
            ChartSpec(
                id="equipment-kpis",
                title=f"{equipment_id} 주요 KPI",
                type="bar",
                allowed_types=["bar", "horizontal_bar", "table"],
                x_key="metric",
                y_key="value",
                data=kpi_data,
                reason="단일 설비의 KPI 비교에는 막대 차트가 적합합니다.",
            )
        ],
        table=[equipment],
        evidence=_evidence([match], [COL_EQUIPMENT, COL_OEE, COL_RISK, COL_PRIORITY, COL_TOOL_WEAR, COL_TORQUE], [f"Equipment_ID = {equipment_id}"], "설비 ID로 단일 행을 조회했습니다."),
        suggestions=[f"{equipment_id}의 OEE가 낮은 이유는?", f"{equipment_id}와 같은 라인의 위험 설비는?", "정비 우선순위를 추천해줘"],
        llm_status="skipped",
    )


def _production_analysis(question: str, rows: list[dict[str, Any]]) -> QueryResponse:
    sorted_rows = sorted(rows, key=lambda row: float(row[COL_PRODUCTION]))[:10]
    table = [_equipment_row(row) for row in sorted_rows]
    avg_prod = _avg(rows, COL_PRODUCTION)
    answer = (
        f"전체 평균 생산량은 {_round(avg_prod, 2)} EA입니다. "
        f"생산량이 가장 낮은 설비는 {table[0]['equipmentId']}이며 생산량은 {table[0]['productionQty']} EA입니다. "
        "생산량 저하는 공구 마모 증가, 낮은 가동률, 품질률 저하와 함께 해석하는 것이 좋습니다."
    )
    scatter = [
        {
            "equipmentId": row[COL_EQUIPMENT],
            "toolWear": _round(row[COL_TOOL_WEAR], 2),
            "productionQty": _round(row[COL_PRODUCTION], 2),
            "oee": _round(row[COL_OEE], 2),
        }
        for row in rows[:: max(1, len(rows) // 300)]
    ]
    return QueryResponse(
        intent="production_analysis",
        question=question,
        title="생산량 저하 분석",
        answer=answer,
        metrics=[
            MetricCard(label="평균 생산량", value=f"{_round(avg_prod, 2)} EA"),
            MetricCard(label="최저 생산 설비", value=table[0]["equipmentId"], tone="warning"),
            MetricCard(label="최저 생산량", value=f"{table[0]['productionQty']} EA", tone="warning"),
        ],
        charts=[
            ChartSpec(
                id="tool-wear-production",
                title="공구 마모와 생산량 관계",
                type="scatter",
                allowed_types=["scatter", "table"],
                x_key="toolWear",
                y_key="productionQty",
                data=scatter,
                reason="두 연속형 지표의 관계는 산점도로 보는 것이 적합합니다.",
            )
        ],
        table=table,
        evidence=_evidence(rows, [COL_PRODUCTION, COL_TOOL_WEAR, COL_AVAILABILITY, COL_QUALITY], [], "생산량 오름차순과 공구 마모 관계를 계산했습니다."),
        suggestions=["공구 마모가 높은 설비를 보여줘", "생산량이 낮은 설비의 공통점은?", "불량률이 높은 설비는?"],
        llm_status="skipped",
    )


def _line_oee_data(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = sorted({str(row[COL_LINE]) for row in rows})
    result = []
    for line in lines:
        line_rows = [row for row in rows if row[COL_LINE] == line]
        result.append({"line": line, "avgOee": _round(_avg(line_rows, COL_OEE), 2), "equipmentCount": len(line_rows)})
    return result


def _evidence(rows: list[dict[str, Any]], columns: list[str], filters: list[str], method: str) -> AnalysisEvidence:
    return AnalysisEvidence(dataset_rows=len(rows), used_columns=columns, filters=filters, method=method)


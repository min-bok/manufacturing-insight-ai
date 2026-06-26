"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FilePlus2,
  FileText,
  LayoutTemplate,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { askQuestion, createReport, getDocxUrl, getReport, getSummary, listReports, updateReport } from "@/lib/api";
import type { BlockType, ChartSpec, ChartType, DatasetSummary, MetricCard, QueryResponse, ReportBlock, ReportSummary } from "@/types/api";
import { ChartPanel, DataTable } from "./chart-panel";
import { ReportBuilder } from "./report-builder";

const sampleQuestions = [
  "전체 설비 상태를 요약해줘",
  "OEE가 가장 낮은 설비는?",
  "가장 위험한 설비를 알려줘",
  "Line 201 상태를 분석해줘",
  "어떤 설비를 먼저 점검해야 해?",
  "생산량이 낮은 원인이 뭐야?",
];

const DEFAULT_REPORT_TITLE = "Manufacturing Insight AI 보고서";
const DRAFT_KEY = "manufacturing-insight-ai:draft:v1";

const reportTemplates = [
  { id: "daily", title: "일일 보고서", description: "운영 KPI와 당일 점검 메모를 빠르게 구성합니다." },
  { id: "weekly", title: "주간 리스크 보고서", description: "위험도 분포와 개선 액션 중심으로 구성합니다." },
  { id: "inspection", title: "설비 점검 보고서", description: "점검 후보 설비와 권장 조치를 정리합니다." },
] as const;

type ReportTemplateId = (typeof reportTemplates)[number]["id"];

interface WorkspaceDraft {
  version: 1;
  reportId: number | null;
  reportTitle: string;
  blocks: ReportBlock[];
  question: string;
  result: QueryResponse | null;
  chartOverrides: Record<string, ChartType>;
  updatedAt: string;
}

export function Workspace() {
  const [summary, setSummary] = useState<DatasetSummary | null>(null);
  const [question, setQuestion] = useState(sampleQuestions[0]);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [chartOverrides, setChartOverrides] = useState<Record<string, ChartType>>({});
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [reportId, setReportId] = useState<number | null>(null);
  const [reportTitle, setReportTitle] = useState(DEFAULT_REPORT_TITLE);
  const [blocks, setBlocks] = useState<ReportBlock[]>([]);
  const [selectedEquipment, setSelectedEquipment] = useState<Record<string, unknown> | null>(null);
  const [savedReportsOpen, setSavedReportsOpen] = useState(false);
  const [reportExpanded, setReportExpanded] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [draftReady, setDraftReady] = useState(false);
  const [draftStatus, setDraftStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refreshInitialData();
    const draft = readDraft();
    if (draft) {
      setReportId(draft.reportId);
      setReportTitle(draft.reportTitle || DEFAULT_REPORT_TITLE);
      setBlocks(draft.blocks || []);
      setQuestion(draft.question || sampleQuestions[0]);
      setResult(draft.result || null);
      setChartOverrides(draft.chartOverrides || {});
      setDraftStatus("작성 중 복원됨");
    }
    setDraftReady(true);
  }, []);

  useEffect(() => {
    if (!draftReady) return;
    const hasDraft = hasDraftableWork({ reportId, reportTitle, blocks, question, result });
    if (!hasDraft) {
      removeDraft();
      setDraftStatus(null);
      return;
    }
    const ok = writeDraft({ reportId, reportTitle, blocks, question, result, chartOverrides });
    setDraftStatus(ok ? "임시저장됨" : "임시저장 실패");
  }, [draftReady, reportId, reportTitle, blocks, question, result, chartOverrides]);

  const displayCharts = useMemo(() => {
    if (!result) return [];
    return result.charts.map((chart) => ({ ...chart, type: chartOverrides[chart.id] || chart.type }));
  }, [result, chartOverrides]);

  const answerMode = useMemo(() => {
    if (result?.llm_status === "used") return { className: "gemini", label: "Gemini Free Tier 보호 모드" };
    if (result?.llm_status === "quota_exhausted") return { className: "warning", label: "무료 AI 소진 - 규칙 기반 분석" };
    if (result?.llm_status === "failed") return { className: "warning", label: "Gemini 실패 - 규칙 기반 분석" };
    return { className: "rules", label: "규칙 기반 분석 모드" };
  }, [result?.llm_status]);

  async function refreshInitialData() {
    try {
      const [nextSummary, nextReports] = await Promise.all([getSummary(), listReports()]);
      setSummary(nextSummary);
      setReports(nextReports);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "초기 데이터를 불러오지 못했습니다.");
    }
  }

  async function handleAsk(nextQuestion = question) {
    if (!nextQuestion.trim()) return;
    setLoading(true);
    setError(null);
    setQuestion(nextQuestion);
    setSelectedEquipment(null);
    try {
      const response = await askQuestion(nextQuestion.trim());
      setResult(response);
      setChartOverrides({});
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "질의 처리 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  function addBlock(block: ReportBlock) {
    setBlocks((current) => [...current, block]);
  }

  function createBlock(type: BlockType, title: string, content: Record<string, unknown>): ReportBlock {
    return {
      id: crypto.randomUUID(),
      type,
      title,
      content: { ...content, layout: { rowId: crypto.randomUUID(), order: 0 } },
    };
  }

  function addAnswerBlock() {
    if (!result) return;
    addBlock(createBlock("answer", result.title, { text: result.answer, evidence: result.evidence }));
  }

  function addKpiBlock() {
    if (!result) return;
    addBlock(createBlock("kpi", `${result.title} KPI`, { metrics: result.metrics }));
  }

  function addChartBlock(chart: ChartSpec) {
    addBlock(createBlock("chart", chart.title, { chart }));
  }

  function addTableBlock() {
    if (!result) return;
    addBlock(createBlock("table", `${result.title} 상세 데이터`, { rows: result.table }));
  }

  function addSuggestionsBlock() {
    if (!result) return;
    addBlock(createBlock("suggestions", "다음 질문 추천", { suggestions: result.suggestions }));
  }

  function applyTemplate(templateId: ReportTemplateId) {
    setReportId(null);
    if (templateId === "daily") {
      setReportTitle("Manufacturing Insight AI 일일 보고서");
      setBlocks([
        createBlock("summary", "일일 운영 요약", { text: "오늘의 설비 운영 상태와 주요 변화를 작성하세요." }),
        createBlock("kpi", "핵심 KPI", { metrics: buildSummaryMetrics(summary) }),
        createBlock("recommendation", "당일 점검 메모", { text: "우선 점검 설비와 조치 결과를 작성하세요." }),
      ]);
      return;
    }
    if (templateId === "weekly") {
      const nextBlocks = [
        createBlock("summary", "주간 리스크 요약", { text: "이번 주 주요 위험 설비와 라인별 효율 저하 원인을 작성하세요." }),
      ];
      if (summary) {
        nextBlocks.push(
          createBlock("chart", "위험도 분포", {
            chart: {
              id: "template-risk-distribution",
              title: "위험도 분포",
              type: "donut",
              allowed_types: ["donut", "bar", "table"],
              category_key: "(*)Risk_Level",
              value_key: "count",
              data: summary.riskDistribution,
              reason: "위험 단계별 비중을 주간 리스크 요약의 기준으로 사용합니다.",
            },
          }),
        );
      }
      nextBlocks.push(createBlock("recommendation", "주간 개선 액션", { text: "반복 위험 설비와 라인별 개선 과제를 작성하세요." }));
      setReportTitle("Manufacturing Insight AI 주간 리스크 보고서");
      setBlocks(nextBlocks);
      return;
    }
    setReportTitle("Manufacturing Insight AI 설비 점검 보고서");
    setBlocks([
      createBlock("summary", "점검 대상 요약", { text: "OEE 하위 설비와 High Risk 설비를 기준으로 점검 대상을 작성하세요." }),
      createBlock("table", "우선 점검 후보", { rows: summary?.topLowOee || [] }),
      createBlock("recommendation", "권장 조치", { text: "설비별 센서값, KPI, 정비 우선순위를 확인해 조치 계획을 작성하세요." }),
    ]);
  }

  async function saveReport() {
    setSaving(true);
    setError(null);
    try {
      const saved = reportId ? await updateReport(reportId, reportTitle, blocks) : await createReport(reportTitle, blocks);
      setReportId(saved.id);
      setReportTitle(saved.title);
      setBlocks(saved.blocks);
      setReports(await listReports());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "보고서 저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function loadReport(id: number) {
    try {
      const report = await getReport(id);
      setReportId(report.id);
      setReportTitle(report.title);
      setBlocks(report.blocks);
      setSavedReportsOpen(false);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "보고서를 불러오지 못했습니다.");
    }
  }

  function newReport() {
    if (blocks.length > 0 && !window.confirm("작성 중인 보고서 블록을 비우고 새 보고서를 시작할까요?")) return;
    setReportId(null);
    setReportTitle(DEFAULT_REPORT_TITLE);
    setBlocks([]);
  }

  function downloadDocx() {
    if (!reportId) return;
    window.location.href = getDocxUrl(reportId);
  }

  return (
    <main className={`app-shell ${reportExpanded ? "report-focus-mode" : ""}`}>
      <section className="topbar compact-topbar">
        <div>
          <p className="eyebrow">Insight Workspace</p>
          <h1>Manufacturing Insight AI</h1>
        </div>
        <div className="topbar-actions">
          <button className="overview-toggle" onClick={() => setSummaryOpen((value) => !value)}>
            {summaryOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            데이터 개요
          </button>
          {draftStatus && (
            <span className={`draft-pill ${draftStatus.includes("실패") ? "failed" : ""}`}>
              <CheckCircle2 size={15} /> {draftStatus}
            </span>
          )}
          <div className={`status-pill ${answerMode.className}`}>
            <Sparkles size={16} /> {answerMode.label}
          </div>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      {summaryOpen && (
        <section className="summary-grid data-overview-grid">
          <SummaryCard label="설비 수" value={summary ? `${summary.equipmentCount.toLocaleString()}대` : "-"} />
          <SummaryCard label="평균 OEE" value={summary ? `${summary.avgOee}%` : "-"} />
          <SummaryCard label="High Risk" value={summary ? `${summary.highRiskCount.toLocaleString()}대` : "-"} tone="danger" />
          <SummaryCard label="생산 라인" value={summary ? `${summary.lineCount}개` : "-"} />
        </section>
      )}

      <div className="workspace-grid">
        <section className="query-panel">
          <div className="panel-title-row">
            <div>
              <p className="eyebrow">Ask Data</p>
              <h2>제조 데이터 질의</h2>
            </div>
            <Bot size={24} />
          </div>

          <div className="question-box">
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={3} />
            <button className="primary-button" onClick={() => void handleAsk()} disabled={loading}>
              {loading ? <RefreshCw className="spin" size={18} /> : <Send size={18} />}
              분석 실행
            </button>
          </div>

          <div className="sample-list">
            {sampleQuestions.map((item) => (
              <button key={item} onClick={() => void handleAsk(item)}>
                {item}
              </button>
            ))}
          </div>

          {result && (
            <article className="result-panel">
              <div className="panel-title-row compact-row">
                <div>
                  <p className="eyebrow">{result.intent}</p>
                  <h2>{result.title}</h2>
                </div>
                <button className="secondary-button" onClick={addAnswerBlock}>
                  <Plus size={17} /> 답변 추가
                </button>
              </div>

              <p className="answer-text">{result.answer}</p>
              {result.llm_message && <p className={`llm-status ${result.llm_status}`}>{result.llm_message}</p>}
              <ExplainabilityPanel evidence={result.evidence} metrics={result.metrics} />

              <div className="metric-grid">
                {result.metrics.map((metric) => (
                  <div className={`metric-card ${metric.tone}`} key={metric.label}>
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                    {metric.helper && <small>{metric.helper}</small>}
                  </div>
                ))}
              </div>
              <div className="block-actions">
                <button onClick={addKpiBlock}>KPI 블록 추가</button>
                <button onClick={addTableBlock}>테이블 추가</button>
                <button onClick={addSuggestionsBlock}>추천 질문 추가</button>
              </div>

              {displayCharts.map((chart) => (
                <div key={chart.id} className="chart-result-wrap">
                  <ChartPanel
                    chart={chart}
                    onTypeChange={(type) => setChartOverrides((current) => ({ ...current, [chart.id]: type }))}
                  />
                  <button className="secondary-button" onClick={() => addChartBlock(chart)}>
                    <Plus size={17} /> 차트 추가
                  </button>
                </div>
              ))}

              <section className="followup-box">
                <h3>다음 질문 추천</h3>
                <div className="sample-list">
                  {result.suggestions.map((item) => (
                    <button key={item} onClick={() => void handleAsk(item)}>
                      {item}
                    </button>
                  ))}
                </div>
              </section>

              {selectedEquipment && <EquipmentDetailPanel equipment={selectedEquipment} onClose={() => setSelectedEquipment(null)} />}
              <DataTable rows={result.table} onEquipmentClick={setSelectedEquipment} />
            </article>
          )}
        </section>

        <aside className="report-side">
          <TemplatePanel onApply={applyTemplate} />
          <section className={`saved-reports ${savedReportsOpen ? "" : "collapsed"}`}>
            <div className="panel-title-row compact-row">
              <button className="saved-toggle" onClick={() => setSavedReportsOpen((value) => !value)}>
                {savedReportsOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                <span>
                  <span className="eyebrow">Saved</span>
                  <strong>저장된 보고서</strong>
                </span>
              </button>
              <button className="icon-button" onClick={newReport} title="새 보고서">
                <FilePlus2 size={18} />
              </button>
            </div>
            {savedReportsOpen &&
              (reports.length === 0 ? (
                <div className="empty-state">저장된 보고서가 없습니다.</div>
              ) : (
                <div className="report-list">
                  {reports.map((report) => (
                    <button key={report.id} className={report.id === reportId ? "active" : ""} onClick={() => void loadReport(report.id)}>
                      <strong>{report.title}</strong>
                      <span>{new Date(report.updated_at).toLocaleString()} · {report.block_count} blocks</span>
                    </button>
                  ))}
                </div>
              ))}
          </section>

          <ReportBuilder
            title={reportTitle}
            blocks={blocks}
            savedReportId={reportId}
            saving={saving}
            expanded={reportExpanded}
            onTitleChange={setReportTitle}
            onBlocksChange={setBlocks}
            onSave={() => void saveReport()}
            onDownload={downloadDocx}
            onToggleExpanded={() => setReportExpanded((value) => !value)}
          />
        </aside>
      </div>
    </main>
  );
}

function TemplatePanel({ onApply }: { onApply: (templateId: ReportTemplateId) => void }) {
  return (
    <section className="template-panel">
      <div className="panel-title-row compact-row">
        <div>
          <p className="eyebrow">Templates</p>
          <h2>보고서 템플릿</h2>
        </div>
        <LayoutTemplate size={22} />
      </div>
      <div className="template-list">
        {reportTemplates.map((template) => (
          <button key={template.id} onClick={() => onApply(template.id)}>
            <FileText size={17} />
            <span>
              <strong>{template.title}</strong>
              <small>{template.description}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function ExplainabilityPanel({ evidence, metrics }: { evidence: QueryResponse["evidence"]; metrics: MetricCard[] }) {
  return (
    <section className="explainability-panel">
      <div className="panel-title-row compact-row">
        <div>
          <p className="eyebrow">Explainability</p>
          <h3>결론 근거</h3>
        </div>
        <span>{evidence.dataset_rows.toLocaleString()} rows</span>
      </div>
      <p>{evidence.method}</p>
      <div className="evidence-detail-grid">
        <EvidenceItem label="필터" value={evidence.filters.length ? evidence.filters.join(", ") : "전체 데이터"} />
        <EvidenceItem label="주요 KPI" value={metrics.slice(0, 3).map((metric) => `${metric.label} ${metric.value}`).join(" · ")} />
      </div>
      <div className="evidence-tags">
        {evidence.used_columns.map((column) => (
          <span key={column}>{column}</span>
        ))}
      </div>
    </section>
  );
}

function EvidenceItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EquipmentDetailPanel({ equipment, onClose }: { equipment: Record<string, unknown>; onClose: () => void }) {
  const equipmentId = getEquipmentId(equipment);
  const kpis = [
    ["OEE", formatWithUnit(equipment.oee, "%")],
    ["가동률", formatWithUnit(equipment.availability, "%")],
    ["품질률", formatWithUnit(equipment.qualityRate, "%")],
    ["생산량", formatWithUnit(equipment.productionQty, " EA")],
  ];
  const sensors = [
    ["공구 마모", formatWithUnit(equipment.toolWear, " min")],
    ["토크", formatWithUnit(equipment.torque, " Nm")],
    ["공정 온도", formatWithUnit(equipment.processTemp, " K")],
    ["회전 속도", formatWithUnit(equipment.rotationalSpeed, " rpm")],
  ];

  return (
    <section className="equipment-detail-panel">
      <div className="panel-title-row compact-row">
        <div>
          <p className="eyebrow">Equipment Detail</p>
          <h3>{equipmentId || "설비 상세"}</h3>
        </div>
        <button className="ghost-icon-button" onClick={onClose} title="닫기">
          <X size={17} />
        </button>
      </div>
      <div className="equipment-status-row">
        <span>{String(equipment.line || "-")}</span>
        <span>{String(equipment.riskLevel || "-")}</span>
        <span>{String(equipment.maintenancePriority || "-")}</span>
      </div>
      <div className="equipment-detail-grid">
        <DetailGroup title="KPI" items={kpis} />
        <DetailGroup title="Sensor" items={sensors} />
      </div>
    </section>
  );
}

function DetailGroup({ title, items }: { title: string; items: string[][] }) {
  return (
    <div className="detail-group">
      <h4>{title}</h4>
      {items.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: string; tone?: "danger" }) {
  return (
    <div className={`summary-card ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function buildSummaryMetrics(summary: DatasetSummary | null): MetricCard[] {
  return [
    { label: "설비 수", value: summary ? `${summary.equipmentCount.toLocaleString()}대` : "-", tone: "neutral" },
    { label: "평균 OEE", value: summary ? `${summary.avgOee}%` : "-", tone: "good" },
    { label: "High Risk", value: summary ? `${summary.highRiskCount.toLocaleString()}대` : "-", tone: "danger" },
    { label: "생산 라인", value: summary ? `${summary.lineCount}개` : "-", tone: "neutral" },
  ];
}

function hasDraftableWork({
  reportId,
  reportTitle,
  blocks,
  question,
  result,
}: Pick<WorkspaceDraft, "reportId" | "reportTitle" | "blocks" | "question" | "result">): boolean {
  return Boolean(reportId || blocks.length > 0 || result || reportTitle !== DEFAULT_REPORT_TITLE || question !== sampleQuestions[0]);
}

function readDraft(): WorkspaceDraft | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as WorkspaceDraft;
    if (parsed.version !== 1) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeDraft(value: Omit<WorkspaceDraft, "version" | "updatedAt">): boolean {
  if (typeof window === "undefined") return false;
  try {
    const draft: WorkspaceDraft = { version: 1, updatedAt: new Date().toISOString(), ...value };
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

function removeDraft() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Ignore localStorage failures.
  }
}

function getEquipmentId(row: Record<string, unknown>): string {
  return String(row.equipmentId || row.Equipment_ID || row["(*)Equipment_ID"] || "");
}

function formatWithUnit(value: unknown, unit: string): string {
  if (typeof value === "number") return `${Number.isInteger(value) ? value : value.toFixed(2)}${unit}`;
  if (value === undefined || value === null || value === "") return "-";
  return `${value}${unit}`;
}

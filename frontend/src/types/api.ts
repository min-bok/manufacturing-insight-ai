export type ChartType = "bar" | "horizontal_bar" | "donut" | "line" | "scatter" | "table" | "kpi";
export type BlockType = "title" | "summary" | "answer" | "kpi" | "chart" | "table" | "recommendation" | "suggestions";

export interface MetricCard {
  label: string;
  value: string | number;
  helper?: string | null;
  tone: "neutral" | "good" | "warning" | "danger";
}

export interface ChartSpec {
  id: string;
  title: string;
  type: ChartType;
  allowed_types: ChartType[];
  x_key?: string | null;
  y_key?: string | null;
  category_key?: string | null;
  value_key?: string | null;
  data: Record<string, unknown>[];
  reason: string;
}

export interface AnalysisEvidence {
  dataset_rows: number;
  used_columns: string[];
  filters: string[];
  method: string;
}

export interface QueryResponse {
  intent: string;
  question: string;
  title: string;
  answer: string;
  metrics: MetricCard[];
  charts: ChartSpec[];
  table: Record<string, unknown>[];
  evidence: AnalysisEvidence;
  suggestions: string[];
  llm_status: "not_configured" | "used" | "quota_exhausted" | "failed" | "skipped";
  llm_message?: string | null;
}

export interface ReportBlock {
  id: string;
  type: BlockType;
  title: string;
  content: Record<string, unknown>;
}

export interface ReportSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  block_count: number;
}

export interface ReportDetail extends ReportSummary {
  blocks: ReportBlock[];
}

export interface DatasetSummary {
  rowCount: number;
  lineCount: number;
  equipmentCount: number;
  avgOee: number;
  avgAvailability: number;
  avgQualityRate: number;
  highRiskCount: number;
  riskDistribution: Record<string, unknown>[];
  lineDistribution: Record<string, unknown>[];
  topLowOee: Record<string, unknown>[];
}

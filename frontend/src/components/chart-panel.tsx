"use client";

import { useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { ChartSpec, ChartType } from "@/types/api";

export interface EChartsHandle {
  getDataURL(opts: { type: string; pixelRatio: number; backgroundColor: string }): string;
}

interface ChartPanelProps {
  chart: ChartSpec;
  onTypeChange?: (type: ChartType) => void;
  onChartReady?: (instance: EChartsHandle) => void;
  onTitleEdit?: (newTitle: string) => void;
  compact?: boolean;
  hideReason?: boolean;
}

interface DataTableProps {
  rows: Record<string, unknown>[];
  compact?: boolean;
  onEquipmentClick?: (row: Record<string, unknown>) => void;
}

const chartLabels: Record<ChartType, string> = {
  bar: "바차트",
  horizontal_bar: "가로 바차트",
  donut: "도넛차트",
  line: "라인차트",
  scatter: "산점도",
  table: "테이블",
  kpi: "KPI",
};

export function ChartPanel({ chart, onTypeChange, onChartReady, onTitleEdit, compact = false, hideReason = false }: ChartPanelProps) {
  if (chart.type === "table") {
    return (
      <div className="chart-panel">
        <ChartHeader chart={chart} onTypeChange={onTypeChange} onTitleEdit={onTitleEdit} />
        <DataTable rows={chart.data} compact={compact} />
      </div>
    );
  }

  return (
    <div className="chart-panel">
      <ChartHeader chart={chart} onTypeChange={onTypeChange} onTitleEdit={onTitleEdit} />
      <ReactECharts
        option={buildOption(chart)}
        style={{ height: compact ? 240 : 320, width: "100%" }}
        notMerge
        lazyUpdate
        onChartReady={onChartReady ? (inst) => onChartReady(inst as unknown as EChartsHandle) : undefined}
      />
      {!compact && !hideReason && <p className="chart-reason">{chart.reason}</p>}
    </div>
  );
}

function ChartHeader({ chart, onTypeChange, onTitleEdit }: ChartPanelProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(chart.title);
  const inputRef = useRef<HTMLInputElement>(null);

  function startEdit() {
    if (!onTitleEdit) return;
    setDraft(chart.title);
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  }

  function commit() {
    setEditing(false);
    if (draft.trim() && draft.trim() !== chart.title) {
      onTitleEdit?.(draft.trim());
    }
  }

  function cancel() {
    setEditing(false);
    setDraft(chart.title);
  }

  return (
    <div className="chart-header">
      <div className="block-title-wrap">
        {editing ? (
          <input
            ref={inputRef}
            className="block-title-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") cancel();
            }}
            autoFocus
          />
        ) : (
          <h3
            onDoubleClick={startEdit}
            style={onTitleEdit ? { cursor: "text" } : undefined}
            title={onTitleEdit ? "더블클릭으로 제목 편집" : undefined}
          >
            {chart.title}
          </h3>
        )}
      </div>
      {onTypeChange && (
        <label className="select-label">
          <span>차트</span>
          <select value={chart.type} onChange={(event) => onTypeChange(event.target.value as ChartType)}>
            {chart.allowed_types.map((type) => (
              <option key={type} value={type}>
                {chartLabels[type]}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

export function DataTable({ rows, compact = false, onEquipmentClick }: DataTableProps) {
  if (!rows.length) {
    return <div className="empty-state">표시할 데이터가 없습니다.</div>;
  }
  const keys = Object.keys(rows[0]).slice(0, compact ? 5 : 8);
  const equipmentClick = onEquipmentClick;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {keys.map((key) => (
              <th key={key}>{key}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, compact ? 5 : 12).map((row, index) => (
            <tr key={index}>
              {keys.map((key) => {
                const value = row[key];
                const valueText = formatCell(value);
                const clickable = Boolean(equipmentClick && isEquipmentKey(key) && valueText.startsWith("MC-"));
                return (
                  <td key={key}>
                    {clickable ? (
                      <button className="equipment-link" onClick={() => equipmentClick?.(row)}>
                        {valueText}
                      </button>
                    ) : (
                      valueText
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function buildOption(chart: ChartSpec) {
  const type = chart.type;
  const xKey = chart.x_key || chart.category_key || "name";
  const yKey = chart.y_key || chart.value_key || "value";

  if (type === "donut") {
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0, left: "center" },
      series: [
        {
          name: chart.title,
          type: "pie",
          radius: ["48%", "72%"],
          center: ["50%", "44%"],
          data: chart.data.map((item) => ({ name: String(item[chart.category_key || xKey]), value: Number(item[chart.value_key || yKey]) })),
        },
      ],
    };
  }

  if (type === "scatter") {
    return {
      tooltip: { trigger: "item" },
      grid: { left: 48, right: 24, top: 24, bottom: 48 },
      xAxis: { name: xKey, type: "value" },
      yAxis: { name: yKey, type: "value" },
      series: [{ type: "scatter", data: chart.data.map((item) => [Number(item[xKey]), Number(item[yKey])]) }],
    };
  }

  if (type === "line") {
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 48, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "category", data: chart.data.map((item) => String(item[xKey])) },
      yAxis: { type: "value" },
      series: [{ type: "line", smooth: true, data: chart.data.map((item) => Number(item[yKey])) }],
    };
  }

  if (type === "horizontal_bar") {
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 96, right: 24, top: 24, bottom: 32 },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: chart.data.map((item) => String(item[xKey])), inverse: true },
      series: [{ type: "bar", data: chart.data.map((item) => Number(item[yKey])), itemStyle: { borderRadius: [0, 6, 6, 0] } }],
    };
  }

  return {
    tooltip: { trigger: "axis" },
    grid: { left: 48, right: 24, top: 24, bottom: 48 },
    xAxis: { type: "category", data: chart.data.map((item) => String(item[xKey])) },
    yAxis: { type: "value" },
    series: [{ type: "bar", data: chart.data.map((item) => Number(item[yKey])), itemStyle: { borderRadius: [6, 6, 0, 0] } }],
  };
}

function isEquipmentKey(key: string): boolean {
  const normalized = key.toLowerCase();
  return normalized.includes("equipment") || normalized.includes("설비");
}

function formatCell(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value ?? "");
}


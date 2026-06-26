"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import {
  DndContext,
  DragEndEvent,
  DragStartEvent,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { Download, GripVertical, Maximize2, Minimize2, Save, Trash2 } from "lucide-react";
import type { BlockType, ChartSpec, ReportBlock } from "@/types/api";
import { exportDocxDirect } from "@/lib/api";
import { ChartPanel, DataTable, type EChartsHandle } from "./chart-panel";

interface ReportBuilderProps {
  title: string;
  blocks: ReportBlock[];
  savedReportId?: number | null;
  saving: boolean;
  expanded: boolean;
  onTitleChange: (title: string) => void;
  onBlocksChange: (blocks: ReportBlock[]) => void;
  onSave: () => void;
  onToggleExpanded: () => void;
}

interface BlockLayout {
  rowId?: string;
  order?: number;
  span?: number;
  width?: number;
}

interface ReportRow {
  id: string;
  blocks: ReportBlock[];
}

type RowDropPosition = "before" | "after";
type BlockSide = "left" | "right";
type CombinePreview = { label: string; kind: "allowed" | "blocked" };

const MAX_ROW_COLUMNS = 3;
const MIN_COLUMN_WIDTH = 30;
const MAX_COLUMN_WIDTH = 70;

export function ReportBuilder({
  title,
  blocks,
  savedReportId,
  saving,
  expanded,
  onTitleChange,
  onBlocksChange,
  onSave,
  onToggleExpanded,
}: ReportBuilderProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [layoutMessage, setLayoutMessage] = useState<string | null>(null);
  const [editingBlockId, setEditingBlockId] = useState<string | null>(null);
  const [draftText, setDraftText] = useState("");
  const [editingTitleId, setEditingTitleId] = useState<string | null>(null);
  const [draftTitleValue, setDraftTitleValue] = useState("");
  const [downloading, setDownloading] = useState(false);
  const chartInstancesRef = useRef<Map<string, EChartsHandle>>(new Map());
  const rows = useMemo(() => buildRows(blocks), [blocks]);
  const activeBlock = useMemo(() => blocks.find((block) => block.id === activeId) || null, [blocks, activeId]);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  // Remove stale chart instance refs when blocks are removed
  useEffect(() => {
    const currentIds = new Set(blocks.map((b) => b.id));
    for (const id of chartInstancesRef.current.keys()) {
      if (!currentIds.has(id)) chartInstancesRef.current.delete(id);
    }
  }, [blocks]);

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
    setLayoutMessage(null);
    cancelTextEdit();
    cancelTitleEdit();
  }

  function handleDragEnd(event: DragEndEvent) {
    const draggedId = String(event.active.id);
    const overId = event.over ? String(event.over.id) : "";
    setActiveId(null);

    if (!overId || draggedId === overId) return;

    if (overId.startsWith("new-row:")) {
      const [, rowId, position] = overId.split(":") as [string, string, RowDropPosition];
      onBlocksChange(moveBlockToNewRow(blocks, draggedId, rowId, position));
      return;
    }

    if (overId.startsWith("combine:")) {
      const [, side, targetId] = overId.split(":") as [string, BlockSide, string];
      const result = moveBlockBeside(blocks, draggedId, targetId, side);
      if (result.ok) {
        onBlocksChange(result.blocks);
      } else {
        setLayoutMessage(result.message);
      }
    }
  }

  function beginTextEdit(block: ReportBlock) {
    const editable = getEditableText(block);
    if (!editable) return;
    cancelTitleEdit();
    setEditingBlockId(block.id);
    setDraftText(editable.value);
  }

  function saveTextEdit() {
    if (!editingBlockId) return;
    onBlocksChange(blocks.map((block) => (block.id === editingBlockId ? setBlockText(block, draftText) : block)));
    setEditingBlockId(null);
    setDraftText("");
  }

  function cancelTextEdit() {
    setEditingBlockId(null);
    setDraftText("");
  }

  function beginTitleEdit(block: ReportBlock) {
    cancelTextEdit();
    setEditingTitleId(block.id);
    setDraftTitleValue(block.title);
  }

  function saveTitleEdit() {
    if (!editingTitleId) return;
    onBlocksChange(
      blocks.map((block) =>
        block.id === editingTitleId ? { ...block, title: draftTitleValue.trim() || block.title } : block,
      ),
    );
    setEditingTitleId(null);
    setDraftTitleValue("");
  }

  function cancelTitleEdit() {
    setEditingTitleId(null);
    setDraftTitleValue("");
  }

  function removeBlock(id: string) {
    if (editingBlockId === id) cancelTextEdit();
    if (editingTitleId === id) cancelTitleEdit();
    onBlocksChange(blocks.filter((block) => block.id !== id));
  }

  function handleChartTitleEdit(blockId: string, newTitle: string) {
    onBlocksChange(
      blocks.map((block) => {
        if (block.id !== blockId) return block;
        const chart = block.content.chart as ChartSpec | undefined;
        return {
          ...block,
          title: newTitle,
          content: {
            ...block.content,
            chart: chart ? { ...chart, title: newTitle } : block.content.chart,
          },
        };
      }),
    );
  }

  function handleChartReady(blockId: string, instance: EChartsHandle) {
    chartInstancesRef.current.set(blockId, instance);
  }

  async function handleDownload() {
    setDownloading(true);
    try {
      const blocksWithImages = blocks.map((block) => {
        if (block.type !== "chart") return block;
        const instance = chartInstancesRef.current.get(block.id);
        if (!instance) return block;
        try {
          const imageDataUrl = instance.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
          return { ...block, content: { ...block.content, imageDataUrl } };
        } catch {
          return block;
        }
      });

      const blob = await exportDocxDirect(title, blocksWithImages);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      const safeTitle = title.replace(/[^\w가-힣\-]/g, "_").slice(0, 40);
      anchor.href = url;
      anchor.download = `${dateStr}_${safeTitle}.docx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("DOCX export failed:", err);
    } finally {
      setDownloading(false);
    }
  }

  function updateRowRatio(rowId: string, leftWidth: number) {
    const row = rows.find((item) => item.id === rowId);
    if (!row || row.blocks.length !== 2) return;
    const leftId = row.blocks[0].id;
    const rightId = row.blocks[1].id;
    const safeLeft = clamp(leftWidth, MIN_COLUMN_WIDTH, MAX_COLUMN_WIDTH);
    onBlocksChange(
      blocks.map((block) => {
        if (block.id === leftId) return setBlockWidth(block, safeLeft);
        if (block.id === rightId) return setBlockWidth(block, 100 - safeLeft);
        return block;
      }),
    );
  }

  // savedReportId kept for future use (e.g. showing saved indicator)
  void savedReportId;

  return (
    <section className="report-builder">
      <div className="panel-title-row report-builder-title-row">
        <div>
          <p className="eyebrow">Report Builder</p>
          <h2>보고서 편집</h2>
        </div>
        <div className="toolbar-actions">
          <button className="icon-button" onClick={onToggleExpanded} title={expanded ? "분석 화면 같이 보기" : "보고서 크게 보기"}>
            {expanded ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </button>
          <button className="icon-button" onClick={onSave} disabled={saving} title="보고서 저장">
            <Save size={18} />
          </button>
          <button
            className="icon-button"
            onClick={() => void handleDownload()}
            disabled={downloading || blocks.length === 0}
            title="DOCX 다운로드"
          >
            <Download size={18} />
          </button>
        </div>
      </div>

      <input className="report-title-input" value={title} onChange={(event) => onTitleChange(event.target.value)} />

      <div className="report-canvas-note">
        <span>자동 행 레이아웃</span>
        <span>텍스트는 더블클릭해서 수정하고, 2열 행은 가운데 핸들로 비율을 조정할 수 있습니다.</span>
      </div>
      {layoutMessage && <div className="layout-message">{layoutMessage}</div>}

      {blocks.length === 0 ? (
        <div className="empty-state tall">분석 결과에서 답변, 차트, 테이블을 보고서에 추가하세요.</div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
          <div className={`report-row-stack ${activeId ? "drag-active" : ""}`}>
            {rows.map((row, index) => (
              <Fragment key={row.id}>
                <RowDropZone rowId={row.id} position="before" active={Boolean(activeId)} />
                <ReportRowView row={row} onRatioChange={(value) => updateRowRatio(row.id, value)}>
                  {row.blocks.map((block) => (
                    <DraggableBlock
                      key={block.id}
                      block={block}
                      columnCount={row.blocks.length}
                      rowBlocks={row.blocks}
                      activeId={activeId}
                      activeBlock={activeBlock}
                      editing={editingBlockId === block.id}
                      draftText={draftText}
                      editingTitle={editingTitleId === block.id}
                      draftTitleValue={draftTitleValue}
                      onDraftTextChange={setDraftText}
                      onDraftTitleChange={setDraftTitleValue}
                      onBeginEdit={() => beginTextEdit(block)}
                      onSaveEdit={saveTextEdit}
                      onCancelEdit={cancelTextEdit}
                      onBeginTitleEdit={() => beginTitleEdit(block)}
                      onSaveTitleEdit={saveTitleEdit}
                      onCancelTitleEdit={cancelTitleEdit}
                      onRemove={() => removeBlock(block.id)}
                      onChartTitleEdit={(newTitle) => handleChartTitleEdit(block.id, newTitle)}
                      onChartReady={(instance) => handleChartReady(block.id, instance)}
                    />
                  ))}
                </ReportRowView>
                {index === rows.length - 1 && <RowDropZone rowId={row.id} position="after" active={Boolean(activeId)} />}
              </Fragment>
            ))}
          </div>
        </DndContext>
      )}
    </section>
  );
}

function ReportRowView({ row, onRatioChange, children }: { row: ReportRow; onRatioChange: (value: number) => void; children: ReactNode }) {
  const leftWidth = getRowLeftWidth(row);
  const style = row.blocks.length === 2 ? ({ "--left-width": `${leftWidth}fr`, "--right-width": `${100 - leftWidth}fr` } as CSSProperties) : undefined;
  return (
    <div className="report-row-wrap">
      <div className={`report-row columns-${row.blocks.length}`} style={style}>
        {children}
      </div>
      {row.blocks.length === 2 && <RowResizeHandle leftPercent={leftWidth} onChange={onRatioChange} />}
    </div>
  );
}

function RowResizeHandle({ leftPercent, onChange }: { leftPercent: number; onChange: (value: number) => void }) {
  function handlePointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    const container = event.currentTarget.parentElement;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const handleMove = (moveEvent: PointerEvent) => {
      const next = ((moveEvent.clientX - rect.left) / rect.width) * 100;
      onChange(clamp(next, MIN_COLUMN_WIDTH, MAX_COLUMN_WIDTH));
    };
    const handleUp = () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
  }

  return (
    <button
      className="row-resize-handle"
      style={{ left: `${leftPercent}%` }}
      onPointerDown={handlePointerDown}
      title="열 비율 조정"
      aria-label="열 비율 조정"
    />
  );
}

function RowDropZone({ rowId, position, active }: { rowId: string; position: RowDropPosition; active: boolean }) {
  const { isOver, setNodeRef } = useDroppable({ id: `new-row:${rowId}:${position}` });
  return (
    <div ref={setNodeRef} className={`row-drop-zone ${active ? "active" : ""} ${isOver ? "over" : ""}`}>
      <span>{isOver ? "새 행으로 배치" : ""}</span>
    </div>
  );
}

function DraggableBlock({
  block,
  columnCount,
  rowBlocks,
  activeId,
  activeBlock,
  editing,
  draftText,
  editingTitle,
  draftTitleValue,
  onDraftTextChange,
  onDraftTitleChange,
  onBeginEdit,
  onSaveEdit,
  onCancelEdit,
  onBeginTitleEdit,
  onSaveTitleEdit,
  onCancelTitleEdit,
  onRemove,
  onChartTitleEdit,
  onChartReady,
}: {
  block: ReportBlock;
  columnCount: number;
  rowBlocks: ReportBlock[];
  activeId: string | null;
  activeBlock: ReportBlock | null;
  editing: boolean;
  draftText: string;
  editingTitle: boolean;
  draftTitleValue: string;
  onDraftTextChange: (value: string) => void;
  onDraftTitleChange: (value: string) => void;
  onBeginEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onBeginTitleEdit: () => void;
  onSaveTitleEdit: () => void;
  onCancelTitleEdit: () => void;
  onRemove: () => void;
  onChartTitleEdit: (newTitle: string) => void;
  onChartReady: (instance: EChartsHandle) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: block.id });
  const style = { transform: CSS.Translate.toString(transform) };
  const showSideSlots = Boolean(activeBlock && activeId !== block.id);
  const combinePreview = getCombinePreview(activeBlock, rowBlocks);
  const isChart = block.type === "chart";

  return (
    <article ref={setNodeRef} style={style} className={`report-block columns-${columnCount} ${isDragging ? "dragging" : ""}`}>
      {showSideSlots && (
        <>
          <BlockSideDropZone blockId={block.id} side="left" preview={combinePreview} />
          <BlockSideDropZone blockId={block.id} side="right" preview={combinePreview} />
        </>
      )}
      <div className="report-block-header">
        <button className="drag-handle" {...attributes} {...listeners} title="블록 이동">
          <GripVertical size={18} />
        </button>
        <div className="block-title-wrap">
          <span className="block-type">{block.type}</span>
          {!isChart && (
            editingTitle ? (
              <input
                className="block-title-input"
                value={draftTitleValue}
                autoFocus
                onChange={(e) => onDraftTitleChange(e.target.value)}
                onBlur={onSaveTitleEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSaveTitleEdit();
                  if (e.key === "Escape") onCancelTitleEdit();
                }}
              />
            ) : (
              <h3 onDoubleClick={onBeginTitleEdit} title="더블클릭해서 제목 수정">
                {block.title}
              </h3>
            )
          )}
        </div>
        <div className="report-block-tools">
          <button className="ghost-icon-button" onClick={onRemove} title="블록 삭제">
            <Trash2 size={17} />
          </button>
        </div>
      </div>
      <BlockPreview
        block={block}
        compact={columnCount > 1}
        editing={editing}
        draftText={draftText}
        onDraftTextChange={onDraftTextChange}
        onBeginEdit={onBeginEdit}
        onSaveEdit={onSaveEdit}
        onCancelEdit={onCancelEdit}
        onChartTitleEdit={onChartTitleEdit}
        onChartReady={onChartReady}
      />
    </article>
  );
}

function BlockSideDropZone({ blockId, side, preview }: { blockId: string; side: BlockSide; preview: CombinePreview }) {
  const { isOver, setNodeRef } = useDroppable({ id: `combine:${side}:${blockId}` });
  const label = side === "left" && preview.kind === "allowed" ? `왼쪽 ${preview.label}` : preview.label;
  return (
    <div ref={setNodeRef} className={`block-side-drop-zone ${side} ${isOver ? "over" : ""} ${preview.kind}`}>
      {isOver && <span>{label}</span>}
    </div>
  );
}

function getCombinePreview(activeBlock: ReportBlock | null, rowBlocks: ReportBlock[]): CombinePreview {
  if (!activeBlock) return { label: "", kind: "allowed" };
  const candidateBlocks = [...rowBlocks.filter((block) => block.id !== activeBlock.id), activeBlock];
  if (!canUseRow(candidateBlocks)) return { label: getCompactLayoutIssue(candidateBlocks), kind: "blocked" };
  const columnCount = candidateBlocks.length;
  if (columnCount <= 1) return { label: "같은 행으로 배치", kind: "allowed" };
  return { label: `${columnCount}열로 배치`, kind: "allowed" };
}

function getCompactLayoutIssue(blocks: ReportBlock[]): string {
  if (blocks.length > MAX_ROW_COLUMNS) return "최대 3열까지 가능";
  if (blocks.some((block) => block.type === "table")) return "테이블은 단독 배치 권장";
  if (blocks.length > 2 && blocks.some((block) => block.type === "chart" || block.type === "answer" || block.type === "summary")) {
    return "최대 2열까지 가능";
  }
  return "같은 행 배치 제한";
}

function BlockPreview({
  block,
  compact,
  editing,
  draftText,
  onDraftTextChange,
  onBeginEdit,
  onSaveEdit,
  onCancelEdit,
  onChartTitleEdit,
  onChartReady,
}: {
  block: ReportBlock;
  compact: boolean;
  editing: boolean;
  draftText: string;
  onDraftTextChange: (value: string) => void;
  onBeginEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onChartTitleEdit: (newTitle: string) => void;
  onChartReady: (instance: EChartsHandle) => void;
}) {
  const content = block.content;
  if (block.type === "chart" && content.chart && typeof content.chart === "object") {
    return (
      <ChartPanel
        chart={content.chart as ChartSpec}
        compact={compact}
        hideReason
        onTitleEdit={onChartTitleEdit}
        onChartReady={onChartReady}
      />
    );
  }
  if (block.type === "table") {
    const rows = (content.rows || content.table || []) as Record<string, unknown>[];
    return <DataTable rows={rows} compact={compact} />;
  }
  if (block.type === "kpi") {
    const metrics = (content.metrics || []) as { label: string; value: string | number }[];
    return (
      <div className="metric-grid compact">
        {metrics.map((metric) => (
          <div className="metric-card" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
    );
  }

  const editable = getEditableText(block);
  const suggestions = (content.suggestions || []) as string[];
  if (editing) {
    return (
      <div className="text-editor-wrap">
        <textarea
          className="text-block-editor"
          value={draftText}
          autoFocus
          rows={4}
          onChange={(event) => onDraftTextChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") onCancelEdit();
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") onSaveEdit();
          }}
        />
        <div className="text-editor-actions">
          <button onClick={onCancelEdit}>취소</button>
          <button onClick={onSaveEdit}>저장</button>
        </div>
      </div>
    );
  }

  return (
    <div className={`text-preview ${editable ? "editable-text-preview" : ""}`} onDoubleClick={editable ? onBeginEdit : undefined}>
      {editable?.value && <p>{editable.value}</p>}
      {editable && !editable.value && <p className="placeholder-text">더블클릭해서 내용을 작성하세요.</p>}
      {suggestions.length > 0 && (
        <ul>
          {suggestions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function buildRows(blocks: ReportBlock[]): ReportRow[] {
  if (blocks.length === 0) return [];
  const hasRowLayout = blocks.some((block) => Boolean(getLayout(block).rowId));

  if (!hasRowLayout) {
    return buildLegacyRows(blocks);
  }

  const rows = new Map<string, { id: string; items: { block: ReportBlock; order: number; index: number }[] }>();
  const rowOrder: string[] = [];

  blocks.forEach((block, index) => {
    const layout = getLayout(block);
    const rowId = layout.rowId || `legacy-row-${index}`;
    if (!rows.has(rowId)) {
      rows.set(rowId, { id: rowId, items: [] });
      rowOrder.push(rowId);
    }
    rows.get(rowId)?.items.push({
      block,
      order: typeof layout.order === "number" ? layout.order : index,
      index,
    });
  });

  return rowOrder
    .map((rowId) => rows.get(rowId))
    .filter((row): row is { id: string; items: { block: ReportBlock; order: number; index: number }[] } => Boolean(row))
    .map((row) => ({
      id: row.id,
      blocks: row.items.sort((a, b) => a.order - b.order || a.index - b.index).map((item) => item.block),
    }));
}

function buildLegacyRows(blocks: ReportBlock[]): ReportRow[] {
  const rows: ReportRow[] = [];
  let current: ReportRow = { id: `legacy-row-${rows.length}`, blocks: [] };
  let usedSpan = 0;

  blocks.forEach((block) => {
    const span = getLegacySpan(block);
    if (current.blocks.length > 0 && usedSpan + span > 12) {
      rows.push(current);
      current = { id: `legacy-row-${rows.length}`, blocks: [] };
      usedSpan = 0;
    }
    current.blocks.push(block);
    usedSpan += span;
    if (usedSpan >= 12) {
      rows.push(current);
      current = { id: `legacy-row-${rows.length}`, blocks: [] };
      usedSpan = 0;
    }
  });

  if (current.blocks.length > 0) rows.push(current);
  return rows;
}

function moveBlockToNewRow(blocks: ReportBlock[], activeId: string, targetRowId: string, position: RowDropPosition): ReportBlock[] {
  const rows = buildRows(blocks);
  const activeBlock = rows.flatMap((row) => row.blocks).find((block) => block.id === activeId);
  if (!activeBlock) return blocks;

  const activeRow = rows.find((row) => row.blocks.some((block) => block.id === activeId));
  if (activeRow?.id === targetRowId && activeRow.blocks.length === 1) return blocks;

  const rowsWithoutActive = rows
    .map((row) => ({ ...row, blocks: row.blocks.filter((block) => block.id !== activeId) }))
    .filter((row) => row.blocks.length > 0);
  const targetIndex = rowsWithoutActive.findIndex((row) => row.id === targetRowId);
  const insertIndex = targetIndex === -1 ? rowsWithoutActive.length : position === "before" ? targetIndex : targetIndex + 1;
  const nextRows = [...rowsWithoutActive];
  nextRows.splice(insertIndex, 0, { id: createRowId(), blocks: [activeBlock] });
  return commitRows(nextRows);
}

function moveBlockBeside(
  blocks: ReportBlock[],
  activeId: string,
  targetId: string,
  side: BlockSide,
): { ok: true; blocks: ReportBlock[] } | { ok: false; message: string } {
  if (activeId === targetId) return { ok: true, blocks };

  const rows = buildRows(blocks);
  const activeBlock = rows.flatMap((row) => row.blocks).find((block) => block.id === activeId);
  const targetRow = rows.find((row) => row.blocks.some((block) => block.id === targetId));
  if (!activeBlock || !targetRow) return { ok: true, blocks };

  const rowsWithoutActive = rows
    .map((row) => ({ ...row, blocks: row.blocks.filter((block) => block.id !== activeId) }))
    .filter((row) => row.blocks.length > 0);
  const nextTargetRow = rowsWithoutActive.find((row) => row.id === targetRow.id);
  if (!nextTargetRow) return { ok: true, blocks };

  const targetIndex = nextTargetRow.blocks.findIndex((block) => block.id === targetId);
  const insertIndex = side === "left" ? targetIndex : targetIndex + 1;
  const candidateBlocks = [...nextTargetRow.blocks];
  candidateBlocks.splice(Math.max(0, insertIndex), 0, activeBlock);

  if (!canUseRow(candidateBlocks)) {
    return { ok: false, message: getLayoutIssue(candidateBlocks) };
  }

  const nextRows = rowsWithoutActive.map((row) => (row.id === nextTargetRow.id ? { ...row, blocks: candidateBlocks } : row));
  return { ok: true, blocks: commitRows(nextRows) };
}

function commitRows(rows: ReportRow[]): ReportBlock[] {
  return rows.flatMap((row) => {
    const widths = getCommittedWidths(row.blocks);
    return row.blocks.map((block, order) => {
      const { span, width, ...layout } = getLayout(block);
      void span;
      void width;
      return {
        ...block,
        content: {
          ...block.content,
          layout: {
            ...layout,
            rowId: row.id,
            order,
            ...(widths ? { width: widths[order] } : {}),
          },
        },
      };
    });
  });
}

function canUseRow(blocks: ReportBlock[]): boolean {
  const columnCount = blocks.length;
  if (columnCount > MAX_ROW_COLUMNS) return false;
  return blocks.every((block) => getMaxColumns(block.type) >= columnCount);
}

function getCommittedWidths(blocks: ReportBlock[]): [number, number] | null {
  if (blocks.length !== 2) return null;
  const first = normalizeWidth(getLayout(blocks[0]).width);
  const second = normalizeWidth(getLayout(blocks[1]).width);
  const left = first ?? (second ? 100 - second : 50);
  const safeLeft = clamp(left, MIN_COLUMN_WIDTH, MAX_COLUMN_WIDTH);
  return [safeLeft, 100 - safeLeft];
}

function getRowLeftWidth(row: ReportRow): number {
  if (row.blocks.length !== 2) return 50;
  return getCommittedWidths(row.blocks)?.[0] ?? 50;
}

function getLayoutIssue(blocks: ReportBlock[]): string {
  if (blocks.length > MAX_ROW_COLUMNS) return "한 행에는 최대 3개의 블록까지만 배치할 수 있습니다.";
  if (blocks.some((block) => block.type === "table")) return "테이블은 가독성을 위해 단독 전체폭 행으로 배치됩니다.";
  if (blocks.length > 2 && blocks.some((block) => block.type === "chart" || block.type === "answer" || block.type === "summary")) {
    return "긴 답변과 차트는 최대 2열까지만 배치할 수 있습니다.";
  }
  return "이 블록 조합은 같은 행에 배치하기 어렵습니다.";
}

function getMaxColumns(type: BlockType): number {
  if (type === "table") return 1;
  if (type === "chart" || type === "answer" || type === "summary" || type === "recommendation") return 2;
  return 3;
}

function getLayout(block: ReportBlock): BlockLayout {
  const layout = block.content.layout;
  if (!layout || typeof layout !== "object") return {};
  return layout as BlockLayout;
}

function getEditableText(block: ReportBlock): { key: string; value: string } | null {
  if (!(block.type === "answer" || block.type === "summary" || block.type === "recommendation")) return null;
  if (typeof block.content.text === "string") return { key: "text", value: block.content.text };
  if (typeof block.content.answer === "string") return { key: "answer", value: block.content.answer };
  if (typeof block.content.summary === "string") return { key: "summary", value: block.content.summary };
  return { key: "text", value: "" };
}

function setBlockText(block: ReportBlock, text: string): ReportBlock {
  const editable = getEditableText(block);
  const key = editable?.key || "text";
  return { ...block, content: { ...block.content, [key]: text } };
}

function setBlockWidth(block: ReportBlock, width: number): ReportBlock {
  return {
    ...block,
    content: {
      ...block.content,
      layout: { ...getLayout(block), width: clamp(width, MIN_COLUMN_WIDTH, MAX_COLUMN_WIDTH) },
    },
  };
}

function getLegacySpan(block: ReportBlock): number {
  const span = getLayout(block).span;
  if (span === 4 || span === 6 || span === 12) return span;
  if (block.type === "kpi" || block.type === "suggestions") return 6;
  return 12;
}

function normalizeWidth(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return clamp(value, MIN_COLUMN_WIDTH, MAX_COLUMN_WIDTH);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(value)));
}

function createRowId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `row-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

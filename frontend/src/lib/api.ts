import type { DatasetSummary, QueryResponse, ReportBlock, ReportDetail, ReportSummary } from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getSummary(): Promise<DatasetSummary> {
  return request<DatasetSummary>("/api/summary");
}

export function askQuestion(question: string): Promise<QueryResponse> {
  return request<QueryResponse>("/api/query", {
    method: "POST",
    body: JSON.stringify({ question, user_key: getUserKey() }),
  });
}

export function listReports(): Promise<ReportSummary[]> {
  return request<ReportSummary[]>("/api/reports");
}

export function createReport(title: string, blocks: ReportBlock[]): Promise<ReportDetail> {
  return request<ReportDetail>("/api/reports", {
    method: "POST",
    body: JSON.stringify({ title, blocks }),
  });
}

export function updateReport(id: number, title: string, blocks: ReportBlock[]): Promise<ReportDetail> {
  return request<ReportDetail>(`/api/reports/${id}`, {
    method: "PUT",
    body: JSON.stringify({ title, blocks }),
  });
}

export function getReport(id: number): Promise<ReportDetail> {
  return request<ReportDetail>(`/api/reports/${id}`);
}

export function getDocxUrl(id: number): string {
  return `${API_BASE_URL}/api/reports/${id}/export/docx`;
}

function getUserKey(): string {
  if (typeof window === "undefined") return "server";
  const storageKey = "manufacturing-ai-user-key";
  const existing = window.localStorage.getItem(storageKey);
  if (existing) return existing;
  const next = crypto.randomUUID();
  window.localStorage.setItem(storageKey, next);
  return next;
}

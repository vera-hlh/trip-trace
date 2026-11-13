const BACKEND_URL = "http://localhost:17890";

export function backendUrl(path: string): string {
  return `${BACKEND_URL}${path}`;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const json = await res.json();
    return json.detail || json.error || `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

/** 发起请求；非 2xx 统一抛 ApiError（带后端 detail）。 */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(backendUrl(path), init);
  if (!res.ok) {
    throw new ApiError(await errorMessage(res), res.status);
  }
  return res;
}

export async function apiJson<T = Record<string, unknown>>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await apiFetch(path, init);
  return (await res.json()) as T;
}

export async function apiText(path: string, init?: RequestInit): Promise<string> {
  const res = await apiFetch(path, init);
  return res.text();
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export function apiGet<T = Record<string, unknown>>(path: string): Promise<T> {
  return apiJson<T>(path);
}

export function apiPost<T = Record<string, unknown>>(
  path: string,
  body?: unknown
): Promise<T> {
  return apiJson<T>(path, jsonInit("POST", body));
}

export function apiPut<T = Record<string, unknown>>(
  path: string,
  body?: unknown
): Promise<T> {
  return apiJson<T>(path, jsonInit("PUT", body));
}

export function apiPatch<T = Record<string, unknown>>(
  path: string,
  body?: unknown
): Promise<T> {
  return apiJson<T>(path, jsonInit("PATCH", body));
}

export function apiDelete<T = Record<string, unknown>>(path: string): Promise<T> {
  return apiJson<T>(path, { method: "DELETE" });
}

export interface PlanTripNode {
  id: number;
  folder: string;
  display_name: string;
  start_date: string | null;
  end_date: string | null;
  sequence_num?: number | null;
  location?: string;
  file_count?: number;
  total_files?: number;
  sub_trips?: PlanTripNode[];
}

export interface PlanFileInfo {
  id: number;
  trip_id: number | null;
  media_file_id: number | null;
  target_rel_path: string;
  status: "pending" | "copied" | "skipped" | "failed" | string;
  error?: string | null;
  file_name: string | null;
  original_path: string | null;
}

export interface PlanData {
  plan: {
    id: number;
    source_folder: string;
    output_folder: string;
    status: "draft" | "executed" | "abandoned" | string;
    plan_version: number;
    source_snapshot: string | null;
    created_at: string;
    executed_at: string | null;
    options: Record<string, unknown>;
  };
  trips_structure: PlanTripNode[];
  files: PlanFileInfo[];
}

async function requestJson(path: string, init?: RequestInit) {
  return apiJson<Record<string, any>>(path, init);
}

export async function checkHealth() {
  return apiJson("/health");
}

export async function getTrips() {
  return apiJson("/api/trips");
}

export async function archivePreview(body: object) {
  return requestJson("/api/archive/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function createArchivePlan(body: object) {
  return requestJson("/api/archive/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getArchivePlan(planId: number): Promise<{ success: boolean; data: PlanData }> {
  return apiJson<{ success: boolean; data: PlanData }>(`/api/archive/plans/${planId}`);
}

export async function patchArchivePlan(planId: number, body: object) {
  return requestJson(`/api/archive/plans/${planId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function executeArchivePlan(planId: number, body: object): Promise<Response> {
  return apiFetch(`/api/archive/plans/${planId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

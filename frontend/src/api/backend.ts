const BACKEND_URL = "http://localhost:17890";

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
  const res = await fetch(`${BACKEND_URL}${path}`, init);
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(json.detail || json.error || `HTTP ${res.status}`);
  }
  return json;
}

export async function checkHealth() {
  const res = await fetch(`${BACKEND_URL}/health`);
  return res.json();
}

export async function getTrips() {
  const res = await fetch(`${BACKEND_URL}/api/trips`);
  return res.json();
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
  return requestJson(`/api/archive/plans/${planId}`);
}

export async function patchArchivePlan(planId: number, body: object) {
  return requestJson(`/api/archive/plans/${planId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function executeArchivePlan(planId: number, body: object): Promise<Response> {
  const res = await fetch(`${BACKEND_URL}/api/archive/plans/${planId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    throw new Error(json.detail || json.error || `HTTP ${res.status}`);
  }
  return res;
}

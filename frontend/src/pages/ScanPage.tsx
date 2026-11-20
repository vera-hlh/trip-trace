/**
 * ScanPage.tsx
 * 扫描进度页面 + 行程树形视图
 *
 * 工作流程（3步）：
 *   1. 扫描文件夹（SSE 实时进度）
 *   2. 逆地理编码（GPS → 城市名）
 *   3. 归档预览（生成可交互行程树：重命名 / 合并子行程）
 */
import { useState, useRef, useEffect } from "react";
import { useAppStore } from "@/store/appStore";
import type { BigTripData } from "@/store/appStore";
import { createArchivePlan, getArchivePlan, patchArchivePlan } from "@/api/backend";
import {
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
  backendUrl,
} from "@/api/backend";
import { PoiTypeTag } from "@/components/scan/PoiTypeTag";
import { ProgressBar } from "@/components/scan/ProgressBar";
import { StatBox } from "@/components/scan/StatBox";
import { TripTree } from "@/components/scan/TripTree";
import clsx from "clsx";

// ── 类型定义 ─────────────────────────────────────────────────

interface ScanEvent {
  type: string;
  current?: number;
  total?: number;
  total_files?: number;
  file?: string;
  has_gps?: boolean;
  datetime?: string;
  error?: string | null;
  message?: string;
  with_gps?: number;
  without_gps?: number;
  errors?: number;
  new_files?: number;
  skipped?: number;
  skipped_dirs_count?: number;   // 因权限不足被跳过的目录数
  skipped_dirs?: string[];       // 前5个跳过目录路径
}

interface ScanStats {
  total: number;
  withGps: number;
  withoutGps: number;
  errors: number;
  newFiles: number;
  skipped: number;
  skippedDirs: number;        // 因权限跳过的目录数
  skippedDirNames: string[];  // 路径示例
}

interface PreviewSummary {
  total_files: number;
  big_trips_created: number;
  sub_trips_created: number;
  files_without_gps: number;
}

// POI 审核分组
interface PoiCandidate {
  name: string;
  type: string;
  distance: string | number;
}

interface PoiGroup {
  province: string;
  city: string;
  area_name?: string;   // 景区/片区（高德 AOI/父级推导）
  area_source?: string;
  area_confidence?: number;
  area_candidates?: Array<{ name: string; source?: string }>;
  poi: string;        // 当前 POI（空=仅城市级别）
  poi_type?: string;  // POI 类型字符串（新增，来自高德 place/around）
  lat?: number;       // 代表性坐标（用于候选 POI 查询）
  lon?: number;
  sample_path?: string;  // 代表性文件路径（用于在资源管理器中定位）
  sample_name?: string;  // 代表性文件名（浏览器模式下可复制）
  file_count: number;
  // 本地编辑状态
  draft?: string;     // 编辑草稿
  areaDraft?: string; // 景区编辑草稿
  areaSaving?: boolean;
  selected?: boolean;
  selectedFiles?: string[]; // 当前组内勾选的照片路径
  photoPoiDraft?: string;   // 照片级 POI 编辑草稿
  photoSaving?: boolean;
  loadingFiles?: boolean;
  editing?: boolean;
  saving?: boolean;
  candidates?: PoiCandidate[] | null;  // 候选 POI 列表（按需加载）
  loadingCandidates?: boolean;
  copied?: boolean;   // 文件名复制状态（短暂显示"已复制"）
  files?: Array<{ path: string; name: string }>;  // 该组所有文件（最多6个，缩略图用）
  thumbsOpen?: boolean;  // 是否展开缩略图
}

type FlowStep =
  | "idle"
  | "scanning"
  | "scan-done"
  | "geocoding"
  | "geocode-done"
  | "previewing"
  | "done";

// ── 方案数据 → 前端行程树 ───────────────────────────────────

function buildTripData(tripsStructure: any[], files: any[]): BigTripData[] {
  const fileMap = new Map<number, Array<{
    name: string;
    path: string;
    planFileId?: number;
    datetime?: string | null;
    areaName?: string;
    poi?: string;
  }>>();
  for (const f of files) {
    if (f.trip_id == null) continue;
    const name =
      f.file_name ||
      f.target_rel_path.replace(/\\/g, "/").split("/").pop() ||
      "";
    if (!fileMap.has(f.trip_id)) fileMap.set(f.trip_id, []);
    fileMap.get(f.trip_id)!.push({
      name,
      path: f.original_path || "",
      planFileId: f.id,
      datetime: f.datetime_original ?? null,
      areaName: f.area_name ?? "",
      poi: f.poi ?? "",
    });
  }

  return tripsStructure.map((big: any) => ({
    planTripId: big.id,
    folder: big.folder,
    displayName: big.display_name || big.folder,
    start_date: big.start_date,
    end_date: big.end_date,
    total_files: big.total_files ?? 0,
    sub_trips: (big.sub_trips || []).map((sub: any) => ({
      planTripId: sub.id,
      folder: sub.folder,
      displayName: sub.display_name || sub.folder,
      location: sub.location || "",
      areaName: sub.area_name || "",
      start_date: sub.start_date,
      end_date: sub.end_date,
      file_count: sub.file_count ?? 0,
      files: fileMap.get(sub.id) || [],
    })),
  }));
}

// ── 主页面 ───────────────────────────────────────────────────

export default function ScanPage() {
  const {
    sourceFolderPath,
    outputFolderPath,
    settings,
    updateSettings,
    setCurrentPage,
    tripStructure,
    setTripStructure,
    tripType,
    setTripType,
    currentPlanId,
    planVersion,
    setCurrentPlanId,
    setPlanVersion,
    setPlanExecuted,
  } = useAppStore();

  // 流程步骤
  const [step, setStep] = useState<FlowStep>(
    tripStructure ? "done" : "idle"
  );

  // 扫描状态
  const [scanEvents, setScanEvents] = useState<ScanEvent[]>([]);
  const [scanStats, setScanStats] = useState<ScanStats | null>(null);
  const [clearBeforeScan, setClearBeforeScan] = useState(true);  // 默认清空，确保每次处理新文件夹时数据干净

  // 地理编码状态
  const [geocodeResult, setGeocodeResult] = useState<{
    updated: number;
    errors: number;
  } | null>(null);

  // 异常文件状态（与 trip_type 不匹配的文件）
  const [anomalyResult, setAnomalyResult] = useState<{
    count: number;
    files: string[];
  } | null>(null);

  // 补充 POI 状态（force_repoi）
  const [repoiRunning, setRepoiRunning] = useState(false);
  const [repoiResult, setRepoiResult] = useState<{ updated: number; api_calls: number } | null>(null);

  // POI 审核分组状态
  const [poiGroups, setPoiGroups] = useState<PoiGroup[]>([]);
  const [poiGroupsLoading, setPoiGroupsLoading] = useState(false);
  const [bulkAreaDraft, setBulkAreaDraft] = useState("");
  const [bulkAreaSaving, setBulkAreaSaving] = useState(false);

  // 大图预览（Lightbox）
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  // 子行程拆分
  const [splitTarget, setSplitTarget] = useState<{ bi: number; si: number } | null>(null);
  const [splitSelected, setSplitSelected] = useState<number[]>([]);
  const [splitName, setSplitName] = useState("");
  const [splitSaving, setSplitSaving] = useState(false);

  // 景区名归一化/别名
  const [normalizeOpen, setNormalizeOpen] = useState(false);
  const [normalizeCity, setNormalizeCity] = useState("");
  const [normalizeSources, setNormalizeSources] = useState<string[]>([]);
  const [normalizeCanonical, setNormalizeCanonical] = useState("");
  const [normalizeSaving, setNormalizeSaving] = useState(false);

  // POI 分组自动恢复：从行程重建页返回时，step="done" 但 poiGroups 已被重置，
  // 通过 useEffect 在组件挂载时自动重新加载，确保用户能继续审核 POI
  useEffect(() => {
    if (step === "done" && poiGroups.length === 0 && sourceFolderPath) {
      // 延迟一帧确保组件完全挂载后再触发网络请求
      const timer = setTimeout(() => {
        apiGet<{ success: boolean; data: { groups: PoiGroup[] } }>(
          `/api/scan/geocoded?folder_path=${encodeURIComponent(sourceFolderPath)}`
        )
          .then((json) => {
            if (json.success && json.data.groups.length > 0) {
              setPoiGroups(
                json.data.groups.map((g: PoiGroup) => ({
                  ...g,
                  draft: g.poi,
                  editing: false,
                  saving: false,
                }))
              );
            }
          })
          .catch(() => {/* 静默失败，用户可手动刷新 */});
      }, 100);
      return () => clearTimeout(timer);
    }
  }, []); // 仅在组件挂载时执行一次 // eslint-disable-line react-hooks/exhaustive-deps

  // 预览摘要
  const [previewSummary, setPreviewSummary] = useState<PreviewSummary | null>(null);

  // 日志
  const [logs, setLogs] = useState<string[]>([]);
  const addLog = (msg: string) => {
    const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    setLogs((prev) => [`[${ts}] ${msg}`, ...prev.slice(0, 80)]);
  };

  // ── 扫描 ───────────────────────────────────────────────────

  const lastProgress = [...scanEvents]
    .reverse()
    .find((e) => e.type === "progress");
  const completedEvent = scanEvents.find((e) => e.type === "complete");

  const handleScan = async () => {
    if (!sourceFolderPath) {
      setCurrentPage("folder-setup");
      return;
    }
    setStep("scanning");
    setScanEvents([]);
    setScanStats(null);
    setCurrentPlanId(null);
    setPlanVersion(0);
    addLog(`开始扫描：${sourceFolderPath}`);

    if (clearBeforeScan) {
      try {
        await apiDelete("/api/scan/clear");
        addLog("已清空旧扫描数据");
      } catch (e) {
        addLog(`清空失败: ${e}`);
      }
    }

    try {
      const response = await fetch(backendUrl("/api/scan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_path: sourceFolderPath, options: {} }),
      });

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const ev: ScanEvent = JSON.parse(line.slice(6));
              setScanEvents((prev) => [...prev.slice(-800), ev]);

              if (ev.type === "complete") {
                const stats: ScanStats = {
                  total: ev.total_files || 0,
                  withGps: ev.with_gps || 0,
                  withoutGps: ev.without_gps || 0,
                  errors: ev.errors || 0,
                  newFiles: ev.new_files || 0,
                  skipped: ev.skipped || 0,
                  skippedDirs: ev.skipped_dirs_count || 0,
                  skippedDirNames: ev.skipped_dirs || [],
                };
                setScanStats(stats);
                const dirNote = stats.skippedDirs > 0 ? `，${stats.skippedDirs} 个目录因权限跳过` : "";
                addLog(
                  `扫描完成：共 ${stats.total} 个文件，新增 ${stats.newFiles}，有 GPS ${stats.withGps}${dirNote}`
                );
              }
            } catch {}
          }
        }
      }

      setStep("scan-done");
    } catch (e) {
      addLog(`扫描失败: ${e}`);
      setStep("idle");
    }
  };

  // ── 逆地理编码 ─────────────────────────────────────────────

  const handleGeocode = async () => {
    setStep("geocoding");
    setAnomalyResult(null);
    addLog(`开始逆地理编码（行程类型：${
      tripType === "domestic" ? "国内" : tripType === "abroad" ? "境外" : "混合"
    }）...`);
    try {
      const data = await apiPost<any>("/api/scan/geocode", { trip_type: tripType });
      if (data.success) {
        setGeocodeResult({ updated: data.updated, errors: data.errors || 0 });
        addLog(`地理编码完成：更新 ${data.updated} 个文件`);

        // 显示异常文件警告（坐标与行程类型不匹配）
        if (data.anomaly_count > 0) {
          setAnomalyResult({
            count: data.anomaly_count,
            files: data.anomaly_files || [],
          });
          addLog(`⚠️ 检测到 ${data.anomaly_count} 个异常文件（GPS坐标与行程类型不匹配）`);
        }

        setStep("geocode-done");
        // 地理编码完成后：自动加载 POI + 自动补充景点 POI（宁多勿缺）
        await handleLoadPoiGroups();
        await handleRepoi();  // P0 #2: 自动触发 force_repoi
      } else {
        addLog(`地理编码失败: ${JSON.stringify(data)}`);
        setStep("scan-done");
      }
    } catch (e) {
      addLog(`地理编码请求失败: ${e}`);
      setStep("scan-done");
    }
  };

  // ── 补充 POI（force_repoi）─────────────────────────────────

  const handleRepoi = async () => {
    setRepoiRunning(true);
    setRepoiResult(null);
    addLog("开始补充景点 POI（重新处理已有城市但无 POI 的文件）...");
    try {
      const data = await apiPost<any>("/api/scan/geocode", {
        trip_type: tripType,
        force_repoi: true,
      });
      if (data.success) {
        setRepoiResult({ updated: data.updated, api_calls: data.api_calls || 0 });
        addLog(`补充 POI 完成：更新 ${data.updated} 个文件，调用在线 API ${data.api_calls || 0} 次`);
        await handleLoadPoiGroups();
      } else {
        addLog(`补充 POI 失败: ${JSON.stringify(data)}`);
      }
    } catch (e) {
      addLog(`补充 POI 请求失败: ${e}`);
    } finally {
      setRepoiRunning(false);
    }
  };

  // ── POI 审核：按组加载更多照片 ─────────────────────────────

  const handleLoadMoreFiles = async (idx: number) => {
    const group = poiGroups[idx];
    if (!group || group.loadingFiles) return;
    const current = group.files?.length ?? 0;
    if (current >= group.file_count) return;

    setPoiGroups((prev) =>
      prev.map((g, i) => (i === idx ? { ...g, loadingFiles: true } : g))
    );
    try {
      const params = new URLSearchParams({
        province: group.province,
        city: group.city,
        area_name: group.area_name ?? "",
        poi: group.poi ?? "",
        offset: String(current),
        limit: "60",
      });
      const json = await apiGet<any>(`/api/scan/poi-files?${params}`);
      if (json.success) {
        setPoiGroups((prev) =>
          prev.map((g, i) =>
            i === idx
              ? {
                  ...g,
                  files: [...(g.files ?? []), ...(json.files ?? [])],
                  file_count: json.total ?? g.file_count,
                  loadingFiles: false,
                }
              : g
          )
        );
      } else {
        addLog("加载更多照片失败");
        setPoiGroups((prev) =>
          prev.map((g, i) => (i === idx ? { ...g, loadingFiles: false } : g))
        );
      }
    } catch (e) {
      addLog(`加载更多照片失败：${e}`);
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, loadingFiles: false } : g))
      );
    }
  };

  // ── POI 审核：加载分组 ─────────────────────────────────────

  const handleLoadPoiGroups = async () => {
    setPoiGroupsLoading(true);
    try {
      const params = new URLSearchParams();
      if (sourceFolderPath) params.set("folder_path", sourceFolderPath);
      const json = await apiGet<any>(`/api/scan/geocoded?${params}`);
      if (json.success) {
        setPoiGroups(json.data.groups.map((g: PoiGroup) => ({
          ...g,
          draft: g.poi,
          areaDraft: g.area_name ?? "",
          editing: false,
          saving: false,
          areaSaving: false,
          selected: false,
        })));
        addLog(`POI 分组已刷新：${json.data.groups.length} 组`);
      } else {
        addLog("刷新 POI 分组失败：接口返回失败");
      }
    } catch (e) {
      addLog(`刷新 POI 分组失败：${e}`);
      console.error("加载 POI 分组失败:", e);
    } finally {
      setPoiGroupsLoading(false);
    }
  };

  // ── POI 审核：整行点击 → 展开/收起（合并候选编辑器 + 缩略图）──────

  const handleToggleExpand = async (idx: number) => {
    const group = poiGroups[idx];

    if (group.editing) {
      // 已展开 → 收起，草稿还原为当前 POI（相当于取消未保存的修改）
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, editing: false, draft: g.poi } : g))
      );
      return;
    }

    // 展开：先设置 editing=true
    setPoiGroups((prev) =>
      prev.map((g, i) =>
        i === idx
          ? { ...g, editing: true, draft: g.poi, areaDraft: g.area_name ?? "" }
          : g
      )
    );

    // 候选 POI 只在首次展开时按需加载（已加载过则不重复请求）
    if (group.lat && group.lon && group.candidates == null) {
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, loadingCandidates: true } : g))
      );
      try {
        const data = await apiGet<any>(
          `/api/scan/poi-candidates?lat=${group.lat}&lon=${group.lon}`
        );
        setPoiGroups((prev) =>
          prev.map((g, i) =>
            i === idx ? { ...g, loadingCandidates: false, candidates: data.candidates || [] } : g
          )
        );
      } catch {
        setPoiGroups((prev) =>
          prev.map((g, i) => i === idx ? { ...g, loadingCandidates: false, candidates: [] } : g)
        );
      }
    }
  };

  // ── 景区审核：保存单组景区 ─────────────────────────────────

  const handleSaveAreaGroup = async (idx: number) => {
    const group = poiGroups[idx];
    if (!group || (group.areaDraft ?? "") === (group.area_name ?? "")) {
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, areaSaving: false } : g))
      );
      return;
    }

    setPoiGroups((prev) =>
      prev.map((g, i) => (i === idx ? { ...g, areaSaving: true } : g))
    );

    try {
      const json = await apiPut<any>("/api/scan/area-group", {
        province: group.province,
        city: group.city,
        old_area: group.area_name ?? "",
        old_poi: group.poi ?? "",
        new_area: group.areaDraft ?? "",
      });
      if (json.success) {
        addLog(
          `景区更新：${group.city} / ${group.poi || "（无 POI）"}：` +
          `${group.area_name || "（无）"} → ${json.area_name || "（无）"}`
        );
        setPoiGroups((prev) =>
          prev.map((g, i) =>
            i === idx
              ? {
                  ...g,
                  area_name: json.area_name || "",
                  area_source: "manual",
                  area_confidence: 1,
                  areaDraft: json.area_name || "",
                  areaSaving: false,
                }
              : g
          )
        );
      } else {
        addLog(`景区更新失败: ${json.error || "未知错误"}`);
        setPoiGroups((prev) =>
          prev.map((g, i) => (i === idx ? { ...g, areaSaving: false } : g))
        );
      }
    } catch (e) {
      addLog(`景区更新请求失败: ${e}`);
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, areaSaving: false } : g))
      );
    }
  };

  // ── 景区审核：批量设置已选组 ───────────────────────────────

  const handleBulkAreaSave = async () => {
    const selected = poiGroups
      .map((group, idx) => ({ group, idx }))
      .filter(({ group }) => group.selected);
    if (selected.length === 0) {
      addLog("请先勾选要设置景区的 POI 组");
      return;
    }

    setBulkAreaSaving(true);
    let updated = 0;
    let failed = 0;
    for (const { group, idx } of selected) {
      if ((group.area_name ?? "") === bulkAreaDraft.trim()) continue;
      try {
        const json = await apiPut<any>("/api/scan/area-group", {
          province: group.province,
          city: group.city,
          old_area: group.area_name ?? "",
          old_poi: group.poi ?? "",
          new_area: bulkAreaDraft.trim(),
        });
        if (json.success) {
          updated += 1;
          setPoiGroups((prev) =>
            prev.map((g, i) =>
              i === idx
                ? {
                    ...g,
                    area_name: json.area_name || "",
                    area_source: "manual",
                    area_confidence: 1,
                    areaDraft: json.area_name || "",
                    selected: false,
                  }
                : g
            )
          );
        } else {
          failed += 1;
        }
      } catch {
        failed += 1;
      }
    }
    setBulkAreaSaving(false);
    setBulkAreaDraft("");
    addLog(
      `批量设置景区：更新 ${updated} 组` +
      (failed ? `，失败 ${failed} 组` : "") +
      ` → ${bulkAreaDraft.trim() || "（清除）"}`
    );
  };

  // ── 照片级 POI：只修改勾选照片 ─────────────────────────────

  const handleSavePhotoPoi = async (idx: number) => {
    const group = poiGroups[idx];
    const paths = group?.selectedFiles ?? [];
    if (!group || paths.length === 0) {
      addLog("请先勾选要修改 POI 的照片");
      return;
    }

    setPoiGroups((prev) =>
      prev.map((g, i) => (i === idx ? { ...g, photoSaving: true } : g))
    );
    try {
      const json = await apiPut<any>("/api/scan/photo-poi", {
        paths,
        new_poi: group.photoPoiDraft ?? "",
      });
      if (json.success) {
        addLog(
          `照片级 POI 更新：${json.updated} 张 → ${json.new_poi || "（清空）"}`
        );
        await handleLoadPoiGroups();
      } else {
        addLog(`照片级 POI 更新失败：${json.error || "未知错误"}`);
        setPoiGroups((prev) =>
          prev.map((g, i) => (i === idx ? { ...g, photoSaving: false } : g))
        );
      }
    } catch (e) {
      addLog(`照片级 POI 更新请求失败：${e}`);
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, photoSaving: false } : g))
      );
    }
  };

  // ── POI 审核：保存单组修改 ─────────────────────────────────

  const handleSavePoiGroup = async (idx: number) => {
    const group = poiGroups[idx];
    if (!group || group.draft === group.poi) {
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, editing: false } : g))
      );
      return;
    }

    setPoiGroups((prev) =>
      prev.map((g, i) => (i === idx ? { ...g, saving: true } : g))
    );

    try {
      const json = await apiPut<any>("/api/scan/poi-group", {
        province: group.province,
        city: group.city,
        old_poi: group.poi,
        new_poi: group.draft ?? "",
      });
      if (json.success) {
        addLog(`POI 更新：${group.city} / ${group.poi || "（无）"} → ${group.draft || "（无）"}`);
        setPoiGroups((prev) =>
          prev.map((g, i) =>
            i === idx
              ? { ...g, poi: g.draft ?? "", editing: false, saving: false }
              : g
          )
        );
        // P0 #5: POI 更新后自动刷新行程预览（需要输出目录已配置）
        if (outputFolderPath) {
          await handlePreview();
        }
      } else {
        addLog(`POI 更新失败: ${json.error}`);
        setPoiGroups((prev) =>
          prev.map((g, i) => (i === idx ? { ...g, saving: false } : g))
        );
      }
    } catch (e) {
      addLog(`POI 更新请求失败: ${e}`);
      setPoiGroups((prev) =>
        prev.map((g, i) => (i === idx ? { ...g, saving: false } : g))
      );
    }
  };

  // ── 景区名归一化 ───────────────────────────────────────────

  const handleApplyAreaAlias = async () => {
    if (!normalizeCity || normalizeSources.length === 0 || !normalizeCanonical.trim()) {
      addLog("请选择城市、至少一个变体名，并填写规范名");
      return;
    }
    setNormalizeSaving(true);
    try {
      const res = await apiPut<any>("/api/scan/area-merge", {
        city: normalizeCity,
        source_names: normalizeSources,
        canonical_name: normalizeCanonical.trim(),
        apply_existing: true,
      });
      if (res.success) {
        addLog(
          `景区归一化：${res.source_names.length} 个变体 → ${res.canonical_name}，` +
          `更新 ${res.updated} 个文件`
        );
        setNormalizeOpen(false);
        setNormalizeSources([]);
        setNormalizeCanonical("");
        await handleLoadPoiGroups();
      } else {
        addLog(`景区归一化失败：${res.error || "未知错误"}`);
      }
    } catch (e) {
      addLog(`景区归一化请求失败：${e}`);
    } finally {
      setNormalizeSaving(false);
    }
  };

  // ── 子行程拆分 ─────────────────────────────────────────────

  const handleOpenSplit = (bi: number, si: number) => {
    const sub = tripStructure?.[bi]?.sub_trips?.[si];
    if (!sub?.planTripId) {
      addLog("该子行程没有方案 ID，无法拆分");
      return;
    }
    setSplitTarget({ bi, si });
    setSplitSelected([]);
    setSplitName(`${sub.displayName} 2`);
  };

  const handleSplitSub = async () => {
    if (!splitTarget || !currentPlanId) return;
    const sub = tripStructure?.[splitTarget.bi]?.sub_trips?.[splitTarget.si];
    if (!sub?.planTripId) return;

    const allIds = (sub.files ?? [])
      .map((f) => f.planFileId)
      .filter((id): id is number => typeof id === "number");
    const selected = splitSelected.filter((id) => allIds.includes(id));
    if (selected.length === 0 || selected.length >= allIds.length) {
      addLog("请选择至少 1 张、且不要选完全部照片");
      return;
    }
    const selectedSet = new Set(selected);
    const remaining = allIds.filter((id) => !selectedSet.has(id));
    const newName = splitName.trim() || `${sub.displayName} 2`;

    setSplitSaving(true);
    try {
      const res = await patchArchivePlan(currentPlanId, {
        plan_version: planVersion,
        splits: [{
          trip_id: sub.planTripId,
          groups: [
            { name: newName, file_ids: selected },
            { name: sub.displayName, file_ids: remaining },
          ],
        }],
      });
      if (!res.success) {
        throw new Error(res.error || res.detail || "拆分失败");
      }
      setPlanVersion(res.data.plan_version);

      const detail = await getArchivePlan(currentPlanId);
      if (!detail.success || !detail.data) {
        throw new Error("拆分后读取方案失败");
      }
      const parsed = buildTripData(detail.data.trips_structure, detail.data.files);
      setTripStructure(parsed);
      const subCount = parsed.reduce((n, big) => n + big.sub_trips.length, 0);
      setPreviewSummary({
        total_files: detail.data.files.length,
        big_trips_created: parsed.length,
        sub_trips_created: subCount,
        files_without_gps: scanStats?.withoutGps ?? 0,
      });
      setSplitTarget(null);
      addLog(`已拆分「${sub.displayName}」→「${newName}」（${selected.length} 张）`);
    } catch (e) {
      addLog(`拆分失败: ${e}`);
    } finally {
      setSplitSaving(false);
    }
  };

  // ── 归档预览 ───────────────────────────────────────────────

  const handlePreview = async () => {
    if (!sourceFolderPath || !outputFolderPath) return;
    setStep("previewing");
    addLog("生成归档方案...");

    try {
      const created = await createArchivePlan({
        folder_path: sourceFolderPath,
        output_path: outputFolderPath,
        options: {
          big_trip_threshold_days: settings.bigTripThresholdDays,
          small_trip_threshold_hours: settings.smallTripThresholdHours,
        },
      });
      if (!created.success || !created.data?.plan_id) {
        throw new Error(created.error || created.detail || "创建归档方案失败");
      }

      const planId = created.data.plan_id as number;
      const detail = await getArchivePlan(planId);
      if (!detail.success || !detail.data) {
        throw new Error("读取归档方案失败");
      }

      const { plan, trips_structure, files } = detail.data;
      setCurrentPlanId(planId);
      setPlanVersion(plan.plan_version);
      setPlanExecuted(false);

      const parsed = buildTripData(trips_structure, files);

      setTripStructure(parsed);
      const subCount = parsed.reduce((n, big) => n + big.sub_trips.length, 0);
      setPreviewSummary({
        total_files: files.length,
        big_trips_created: parsed.length,
        sub_trips_created: subCount,
        files_without_gps: scanStats?.withoutGps ?? 0,
      });
      addLog(
        `方案已生成：${parsed.length} 大行程，${subCount} 子行程，共 ${files.length} 个文件（plan #${planId} v${plan.plan_version}）`
      );
      setStep("done");
    } catch (e) {
      addLog(`生成方案失败: ${e}`);
      setStep("geocode-done");
    }
  };

  // ── 行程编辑 ───────────────────────────────────────────────

  const renameTrip = async (
    tripId: number | undefined,
    name: string,
    applyLocal: () => void
  ) => {
    const planId = useAppStore.getState().currentPlanId;
    if (!planId || !tripId) {
      applyLocal();
      addLog(`重命名 → "${name}"（仅本地）`);
      return;
    }
    try {
      const version = useAppStore.getState().planVersion;
      const res = await patchArchivePlan(planId, {
        plan_version: version,
        renames: [{ trip_id: tripId, display_name: name }],
      });
      useAppStore.getState().setPlanVersion(res.data.plan_version);
      applyLocal();
      addLog(`重命名 → "${name}"（已保存 plan v${res.data.plan_version}）`);
    } catch (e) {
      addLog(`重命名失败: ${e}`);
    }
  };

  const handleRenameBig = (bi: number, name: string) => {
    const big = useAppStore.getState().tripStructure?.[bi];
    if (!big) return;
    void renameTrip(big.planTripId, name, () => {
      const current = useAppStore.getState().tripStructure;
      if (!current) return;
      setTripStructure(
        current.map((item, i) =>
          i === bi ? { ...item, folder: name, displayName: name } : item
        )
      );
    });
  };

  const handleRenameSub = (bi: number, si: number, name: string) => {
    const sub = useAppStore.getState().tripStructure?.[bi]?.sub_trips?.[si];
    if (!sub) return;
    void renameTrip(sub.planTripId, name, () => {
      const current = useAppStore.getState().tripStructure;
      if (!current) return;
      setTripStructure(
        current.map((big, i) =>
          i !== bi
            ? big
            : {
                ...big,
                sub_trips: big.sub_trips.map((item, j) =>
                  j === si ? { ...item, folder: name, displayName: name } : item
                ),
              }
        )
      );
    });
  };

  // ── 重置 ───────────────────────────────────────────────────

  const handleReset = () => {
    setStep("idle");
    setScanEvents([]);
    setScanStats(null);
    setGeocodeResult(null);
    setPoiGroups([]);
    setPreviewSummary(null);
    setTripStructure(null);
    setCurrentPlanId(null);
    setPlanVersion(0);
    setPlanExecuted(false);
    setLogs([]);
  };

  // ── 步骤徽章 ───────────────────────────────────────────────

  const FLOW_STEPS = [
    {
      label: "扫描",
      done: ["scan-done", "geocoding", "geocode-done", "previewing", "done"].includes(step),
      active: step === "scanning",
    },
    {
      label: "地理编码",
      done: ["geocode-done", "previewing", "done"].includes(step),
      active: step === "geocoding",
    },
    {
      label: "行程预览",
      done: step === "done",
      active: step === "previewing",
    },
  ];

  // ── 渲染 ───────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      {/* 页头 */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">🔍 扫描 & 行程识别</h1>
          <p className="text-sm mt-1">
            {sourceFolderPath ? (
              <span className="font-mono text-slate-400 text-xs break-all">
                {sourceFolderPath}
              </span>
            ) : (
              <button
                onClick={() => setCurrentPage("folder-setup")}
                className="text-blue-400 hover:underline text-sm"
              >
                请先选择文件夹 →
              </button>
            )}
          </p>
        </div>
        {step !== "idle" && (
          <button
            onClick={handleReset}
            title="清除当前扫描会话，回到初始状态。&#10;不影响原始文件，已生成的归档文件夹也不受影响。&#10;适合：更换源文件夹、或想完全重新整理时使用。"
            className="flex-shrink-0 text-xs text-slate-500 hover:text-slate-300 border border-slate-700 hover:border-slate-600 px-3 py-1.5 rounded-lg transition-colors"
          >
            🔄 重新开始
          </button>
        )}
      </div>

      {/* 步骤指示器 */}
      <div className="flex items-center gap-2 flex-wrap">
        {FLOW_STEPS.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <div
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border",
                s.done
                  ? "bg-emerald-900/30 border-emerald-700/50 text-emerald-400"
                  : s.active
                  ? "bg-blue-900/40 border-blue-600/60 text-blue-300 animate-pulse"
                  : "bg-slate-800 border-slate-700 text-slate-500"
              )}
            >
              <span>{s.done ? "✅" : s.active ? "⏳" : `${i + 1}`}</span>
              <span>{s.label}</span>
            </div>
            {i < FLOW_STEPS.length - 1 && (
              <span className="text-slate-600 text-sm">→</span>
            )}
          </div>
        ))}
      </div>

      {/* ── 修复工具栏（始终可见，不依赖 step 状态）─────── */}
      <div className="flex items-center justify-between bg-slate-800/40 border border-slate-700/30 rounded-xl px-4 py-2.5">
        <div className="text-xs text-slate-500">
          {repoiResult ? (
            <span className="text-emerald-400">
              ✅ 已补充 {repoiResult.updated} 个文件的景点 POI（在线 API {repoiResult.api_calls} 次）
            </span>
          ) : (
            <span>🔧 <strong className="text-slate-400">补充景点 POI</strong>：修复已有城市名但缺少景点名的旧数据</span>
          )}
        </div>
        <button
          onClick={handleRepoi}
          disabled={repoiRunning}
          className={clsx(
            "ml-4 px-3 py-1 rounded-lg text-xs font-medium transition-all flex-shrink-0",
            repoiRunning
              ? "bg-slate-700 text-slate-500 cursor-not-allowed animate-pulse"
              : "bg-purple-800/50 hover:bg-purple-700/60 border border-purple-700/50 hover:border-purple-600 text-purple-300 hover:text-purple-200"
          )}
        >
          {repoiRunning ? "补充中..." : "🔧 执行"}
        </button>
      </div>

      {/* ── Step 1: 扫描 ─────────────────────────────────── */}
      <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">
            1️⃣ 扫描文件夹
          </h2>
          <div className="flex items-center gap-2">
            {step === "scanning" ? (
              <span className="text-xs text-blue-400 animate-pulse">扫描中...</span>
            ) : step === "idle" || step === "scan-done" ? (
              <button
                onClick={handleScan}
                disabled={!sourceFolderPath}
                className={clsx(
                  "px-4 py-1.5 rounded-lg text-sm font-medium transition-all",
                  sourceFolderPath
                    ? "bg-blue-600 hover:bg-blue-500 text-white"
                    : "bg-slate-700 text-slate-500 cursor-not-allowed"
                )}
              >
                {step === "scan-done" ? "🔄 重新扫描" : "🔍 开始扫描"}
              </button>
            ) : (
              <span className="text-xs text-emerald-400">✅ 已完成</span>
            )}
          </div>
        </div>

        {/* 扫描参数（仅 idle/scanning 时显示） */}
        {(step === "idle" || step === "scanning") && (
          <div className="grid grid-cols-2 gap-4 pt-1">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                大行程阈值（天）:{" "}
                <span className="text-blue-400 font-bold">
                  {settings.bigTripThresholdDays}
                </span>
              </label>
              <input
                type="range"
                min={7}
                max={90}
                value={settings.bigTripThresholdDays}
                onChange={(e) =>
                  updateSettings({ bigTripThresholdDays: Number(e.target.value) })
                }
                className="w-full accent-blue-500"
              />
              <div className="flex justify-between text-xs text-slate-600 mt-0.5">
                <span>7天</span>
                <span>90天</span>
              </div>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                子行程阈值（小时）:{" "}
                <span className="text-blue-400 font-bold">
                  {settings.smallTripThresholdHours}
                </span>
              </label>
              <input
                type="range"
                min={0.5}
                max={12}
                step={0.5}
                value={settings.smallTripThresholdHours}
                onChange={(e) =>
                  updateSettings({
                    smallTripThresholdHours: Number(e.target.value),
                  })
                }
                className="w-full accent-blue-500"
              />
              <div className="flex justify-between text-xs text-slate-600 mt-0.5">
                <span>0.5h</span>
                <span>12h</span>
              </div>
            </div>
            <div className="col-span-2 space-y-1.5">
              <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer w-fit">
                <input
                  type="checkbox"
                  checked={clearBeforeScan}
                  onChange={(e) => setClearBeforeScan(e.target.checked)}
                  className="accent-blue-500"
                />
                扫描前清空数据库旧数据
              </label>
              <div className="ml-5 text-xs text-slate-600 leading-relaxed space-y-0.5">
                <div>
                  <span className="text-slate-500">✅ 勾选（推荐）：</span>
                  处理新文件夹时使用，确保数据干净（不影响原始文件）
                </div>
                <div>
                  <span className="text-slate-500">⬜ 不勾选：</span>
                  仅在原文件夹<strong className="text-slate-500">新增了照片</strong>时使用，已有记录直接跳过省时省 API 额度
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 实时进度条 */}
        {step === "scanning" && lastProgress?.total && (
          <div className="space-y-2">
            <ProgressBar
              value={lastProgress.current || 0}
              max={lastProgress.total}
            />
            <div className="flex justify-between text-xs text-slate-400">
              <span className="font-mono truncate max-w-md">
                📄 {lastProgress.file}
                <span
                  className={clsx(
                    "ml-2",
                    lastProgress.has_gps ? "text-emerald-400" : "text-slate-500"
                  )}
                >
                  {lastProgress.has_gps ? "GPS✓" : "无GPS"}
                </span>
              </span>
              <span>
                {lastProgress.current}/{lastProgress.total}
              </span>
            </div>
          </div>
        )}

        {/* 扫描完成摘要 */}
        {completedEvent && (
          <div className="p-3 bg-emerald-900/20 border border-emerald-700/40 rounded-lg text-sm text-emerald-300">
            ✅ 扫描完成 · 共{" "}
            <strong>{completedEvent.total_files}</strong> 个文件 ·
            新增 <strong>{completedEvent.new_files}</strong> ·
            有GPS <strong>{completedEvent.with_gps}</strong> ·
            跳过（已有）<strong>{completedEvent.skipped}</strong>
          </div>
        )}

        {/* 详细统计格 */}
        {scanStats && step !== "scanning" && (
          <div className="space-y-2">
            <div className="grid grid-cols-5 gap-2">
              <StatBox value={scanStats.total} label="总文件" color="text-blue-400" />
              <StatBox value={scanStats.newFiles} label="新增" color="text-emerald-400" />
              <StatBox value={scanStats.withGps} label="有GPS" color="text-emerald-400" />
              <StatBox value={scanStats.withoutGps} label="无GPS" color="text-amber-400" />
              <StatBox value={scanStats.errors} label="错误" color="text-red-400" />
            </div>
            {/* 跳过目录提示（权限不足时显示）*/}
            {scanStats.skippedDirs > 0 && (
              <div className="p-3 bg-slate-800/60 border border-slate-600/40 rounded-lg space-y-1">
                <p className="text-xs text-slate-400 font-medium">
                  ⚠️ {scanStats.skippedDirs} 个子目录因权限不足被跳过（其中的文件未被扫描）
                </p>
                {scanStats.skippedDirNames.length > 0 && (
                  <div className="text-xs text-slate-600 font-mono space-y-0.5">
                    {scanStats.skippedDirNames.map((d, i) => (
                      <div key={i} className="truncate">· {d}</div>
                    ))}
                    {scanStats.skippedDirs > scanStats.skippedDirNames.length && (
                      <div>...还有 {scanStats.skippedDirs - scanStats.skippedDirNames.length} 个</div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Step 2: 逆地理编码 ───────────────────────────── */}
      {["scan-done", "geocoding", "geocode-done", "previewing", "done"].includes(step) && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">
              2️⃣ 逆地理编码
            </h2>
            {step === "scan-done" ? (
              <button
                onClick={handleGeocode}
                className="px-4 py-1.5 bg-purple-700 hover:bg-purple-600 rounded-lg text-sm font-medium text-white transition-all"
              >
                🌍 执行地理编码
              </button>
            ) : step === "geocoding" ? (
              <span className="text-xs text-purple-400 animate-pulse">
                编码中...
              </span>
            ) : (
              <span className="text-xs text-emerald-400">✅ 已完成</span>
            )}
          </div>

          {/* 行程类型选择器（仅 scan-done 时显示，地理编码后锁定） */}
          {step === "scan-done" && (
            <div className="space-y-2 pt-1">
              <p className="text-xs text-slate-400 font-medium">选择本次行程类型：</p>
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    { value: "domestic", icon: "🇨🇳", label: "国内行程", desc: "高德 API 精确地名" },
                    { value: "abroad",   icon: "🌍", label: "境外行程", desc: "Nominatim / 离线" },
                    { value: "mixed",    icon: "🗺️",  label: "混合行程", desc: "自动国内/境外分发" },
                  ] as const
                ).map(({ value, icon, label, desc }) => (
                  <button
                    key={value}
                    onClick={() => setTripType(value)}
                    className={clsx(
                      "flex flex-col items-center p-3 rounded-xl border text-xs transition-all",
                      tripType === value
                        ? "bg-purple-900/40 border-purple-600/60 text-purple-300"
                        : "bg-slate-800/60 border-slate-700/50 text-slate-400 hover:border-slate-600"
                    )}
                  >
                    <span className="text-lg mb-1">{icon}</span>
                    <span className="font-medium">{label}</span>
                    <span className="text-slate-500 mt-0.5">{desc}</span>
                  </button>
                ))}
              </div>
              <p className="text-xs text-amber-400/70">
                ⚠️ 高德仅处理中国坐标；境外坐标需要 Nominatim（未配置时只返回离线城市名）。境外照片请选择「境外」或「混合」行程。
              </p>
            </div>
          )}

          {/* 已锁定时显示当前行程类型 */}
          {!["scan-done"].includes(step) && (
            <p className="text-xs text-slate-500">
              行程类型：
              <span className="text-purple-400 font-medium ml-1">
                {tripType === "domestic" ? "🇨🇳 国内" : tripType === "abroad" ? "🌍 境外" : "🗺️ 混合"}
              </span>
            </p>
          )}

          {geocodeResult ? (
            <p className="text-xs text-slate-400">
              已更新{" "}
              <span className="text-emerald-400 font-bold">
                {geocodeResult.updated}
              </span>{" "}
              个文件的地理位置
              {geocodeResult.errors > 0 && (
                <span className="text-amber-400 ml-2">
                  （{geocodeResult.errors} 个失败）
                </span>
              )}
            </p>
          ) : step !== "scan-done" && (
            <p className="text-xs text-slate-500">
              将 GPS 坐标转换为城市/省份名称，用于行程命名和归档文件夹
            </p>
          )}

          {/* 异常文件警告 */}
          {anomalyResult && anomalyResult.count > 0 && (
            <div className="p-3 bg-amber-900/20 border border-amber-700/40 rounded-lg space-y-2">
              <p className="text-xs text-amber-300 font-medium">
                ⚠️ 检测到 {anomalyResult.count} 个文件的 GPS 位置与选择的「
                {tripType === "domestic" ? "国内" : "境外"}行程」不符
              </p>
              <p className="text-xs text-slate-400">
                这些文件归档时将复制到输出目录下的{" "}
                <code className="bg-slate-700 px-1 rounded text-amber-300">_待手动整理/</code>{" "}
                文件夹，可在归档完成后手动处理。
              </p>
              {anomalyResult.files.length > 0 && (
                <div className="text-xs text-slate-500 font-mono max-h-20 overflow-y-auto">
                  {anomalyResult.files.slice(0, 5).map((f, i) => (
                    <div key={i}>· {f}</div>
                  ))}
                  {anomalyResult.count > 5 && (
                    <div className="text-slate-600">...还有 {anomalyResult.count - 5} 个文件</div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── POI 审核（地理编码完成后显示，可选步骤）────────── */}
      {["geocode-done", "previewing", "done"].includes(step) && poiGroups.length > 0 && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-300">
                📍 POI 审核
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                POI将作为照片的备注记录下来。你可以点击以下记录按需修改POI。
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const firstCity = poiGroups.find(g => g.city)?.city || "";
                  setNormalizeCity(firstCity);
                  setNormalizeSources([]);
                  setNormalizeCanonical("");
                  setNormalizeOpen(true);
                }}
                className="text-xs text-amber-300 hover:text-amber-200 border border-amber-700/50 px-2 py-1 rounded transition-colors"
              >
                🔗 景区归一化
              </button>
              <button
                onClick={handleLoadPoiGroups}
                disabled={poiGroupsLoading}
                className="text-xs text-slate-500 hover:text-slate-300 border border-slate-700 px-2 py-1 rounded transition-colors"
              >
                {poiGroupsLoading ? "加载中..." : "🔄 刷新"}
              </button>
            </div>
          </div>

          {/* 批量景区操作 */}
          <div className="flex items-center gap-2 flex-wrap bg-slate-800/40 border border-slate-700/40 rounded-lg px-3 py-2">
            <span className="text-xs text-slate-400">
              已选 <strong className="text-amber-300">{poiGroups.filter(g => g.selected).length}</strong> 组
            </span>
            <button
              onClick={() => setPoiGroups(prev => prev.map(g => ({ ...g, selected: true })))}
              className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 px-2 py-0.5 rounded"
            >
              全选
            </button>
            <button
              onClick={() => setPoiGroups(prev => prev.map(g => ({ ...g, selected: false })))}
              className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 px-2 py-0.5 rounded"
            >
              清空选择
            </button>
            <input
              type="text"
              value={bulkAreaDraft}
              onChange={(e) => setBulkAreaDraft(e.target.value)}
              list="area-name-options"
              placeholder="批量设置景区名（留空=清除）"
              className="flex-1 min-w-[12rem] bg-slate-700 border border-amber-600/40 rounded px-2 py-1 text-xs text-white outline-none"
            />
            <button
              onClick={handleBulkAreaSave}
              disabled={bulkAreaSaving}
              className="text-xs px-3 py-1 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded"
            >
              {bulkAreaSaving ? "应用中..." : "应用到已选"}
            </button>
            <datalist id="area-name-options">
              {Array.from(new Set(poiGroups.map(g => g.area_name).filter(Boolean))).map(name => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </div>

          {/* 分组列表 */}
          <div className="space-y-1">
            {poiGroups.map((group, idx) => (
              <div
                key={idx}
                className="bg-slate-800/50 rounded-lg overflow-hidden"
              >
              {/* 整行点击 → 展开/收起（头部纯展示，不含编辑控件） */}
              <div
                className={clsx(
                  "flex items-center gap-3 px-3 py-2 text-sm cursor-pointer transition-colors",
                  group.editing
                    ? "bg-blue-900/30 hover:bg-blue-900/40 border-l-2 border-blue-500"
                    : "hover:bg-slate-800/80"
                )}
                onClick={() => handleToggleExpand(idx)}
              >
                {/* 批量选择 */}
                <input
                  type="checkbox"
                  checked={!!group.selected}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() =>
                    setPoiGroups((prev) =>
                      prev.map((g, i) =>
                        i === idx ? { ...g, selected: !g.selected } : g
                      )
                    )
                  }
                  className="w-3.5 h-3.5 accent-amber-500 flex-shrink-0"
                  title="勾选后可批量设置景区"
                />

                {/* 序号 */}
                <span className="text-slate-600 text-xs font-mono w-5 text-right flex-shrink-0">
                  {idx + 1}
                </span>
                {/* 城市 */}
                <span className="text-slate-300 font-medium min-w-[5rem] flex-shrink-0">
                  {group.city}
                </span>

                {/* POI 展示（只读，编辑区已移到展开区） */}
                <div className="flex-1 min-w-0 flex items-center gap-2">
                  {group.area_name && (
                    <span
                      title={`景区来源：${group.area_source || "unknown"}`}
                      className="text-xs px-1.5 py-0.5 rounded border bg-amber-900/20 text-amber-300 border-amber-700/40 flex-shrink-0 max-w-[12rem] truncate"
                    >
                      🏞 {group.area_name}
                    </span>
                  )}
                  {group.poi ? (
                    <span className="text-emerald-300 truncate">{group.poi}</span>
                  ) : (
                    <span className="text-slate-500 italic">
                      （无 POI，仅显示城市）
                    </span>
                  )}
                </div>

                {/* POI 类型标签 */}
                <PoiTypeTag poiType={group.poi_type} />

                {/* 文件数（固定宽度右对齐，避免位数不同导致类型标签错位） */}
                <div className="flex-shrink-0 w-12 text-right">
                  <span className="text-xs text-slate-500">{group.file_count}张</span>
                </div>

                {/* 展开/收起指示箭头 */}
                <span className={clsx(
                  "text-xs flex-shrink-0 w-3 text-center",
                  group.editing ? "text-blue-400" : "text-slate-500"
                )}>
                  {group.editing ? "▲" : "▼"}
                </span>
              </div>

              {/* 展开区：候选POI编辑器 + 缩略图（合并显示，整行点击触发）*/}
              {group.editing && (
                <div className="px-3 pb-3 pt-2 border-t border-slate-700/30 space-y-3">
                  {/* 景区编辑器：只影响当前组文件，不写全局别名 */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400 flex-shrink-0 w-10">景区</span>
                    <input
                      type="text"
                      value={group.areaDraft ?? ""}
                      onChange={(e) =>
                        setPoiGroups((prev) =>
                          prev.map((g, i) =>
                            i === idx ? { ...g, areaDraft: e.target.value } : g
                          )
                        )
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSaveAreaGroup(idx);
                        if (e.key === "Escape") handleToggleExpand(idx);
                      }}
                      placeholder="如：三峡大坝旅游区（留空=清除）"
                      list="area-name-options"
                      className="flex-1 bg-slate-700 border border-amber-600/50 rounded px-2 py-1 text-sm text-white outline-none"
                    />
                    <button
                      onClick={() => handleSaveAreaGroup(idx)}
                      disabled={group.areaSaving}
                      className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white text-xs rounded transition-colors flex-shrink-0"
                    >
                      {group.areaSaving ? "..." : "保存景区"}
                    </button>
                    <span className="text-[10px] text-slate-500 flex-shrink-0">
                      {group.area_source || "未识别"}
                    </span>
                  </div>

                  {group.area_candidates && group.area_candidates.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="text-[10px] text-slate-500">候选：</span>
                      {group.area_candidates.map((candidate, ci) => (
                        <button
                          key={`${candidate.name}-${ci}`}
                          onClick={() =>
                            setPoiGroups((prev) =>
                              prev.map((g, i) =>
                                i === idx ? { ...g, areaDraft: candidate.name } : g
                              )
                            )
                          }
                          title={candidate.source || ""}
                          className={clsx(
                            "text-[10px] px-2 py-0.5 rounded border transition-colors",
                            (group.areaDraft ?? "") === candidate.name
                              ? "bg-amber-900/40 border-amber-600/60 text-amber-300"
                              : "bg-slate-700/60 border-slate-600 text-slate-300 hover:border-amber-500/60"
                          )}
                        >
                          {candidate.name}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* 候选 POI 编辑器 */}
                  <div className="space-y-1.5">
                    {group.loadingCandidates && (
                      <div className="text-xs text-slate-500 animate-pulse">⏳ 加载候选...</div>
                    )}
                    {group.candidates && group.candidates.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {group.candidates.map((c, ci) => {
                          const t = c.type;
                          const emoji = t.includes("风景名胜") ? "🏞️"
                            : t.includes("热点地名") || t.includes("标志") ? "📍"
                            : t.includes("自然地名") ? "🌊"
                            : t.includes("公园") ? "🌳"
                            : t.includes("博物") || t.includes("展览") || t.includes("美术") ? "🏛️"
                            : t.includes("火车站") ? "🚉"
                            : t.includes("休闲") || t.includes("度假") ? "🎪"
                            : t.includes("村庄") ? "⚠️"
                            : "📌";
                          const isSelected = group.draft === c.name;
                          return (
                            <button
                              key={ci}
                              onClick={() =>
                                setPoiGroups((prev) =>
                                  prev.map((g, i) => i === idx ? { ...g, draft: c.name } : g)
                                )
                              }
                              title={`${c.type} | ${c.distance}m`}
                              className={clsx(
                                "text-xs px-2 py-0.5 rounded-lg border transition-all",
                                isSelected
                                  ? "bg-emerald-900/40 border-emerald-600/60 text-emerald-300"
                                  : "bg-slate-700/60 border-slate-600 text-slate-300 hover:border-blue-500/60 hover:text-blue-300"
                              )}
                            >
                              {emoji} {c.name}
                              <span className="text-slate-500 ml-1">{c.distance}m</span>
                            </button>
                          );
                        })}
                        {/* 清空选项 */}
                        <button
                          onClick={() =>
                            setPoiGroups((prev) =>
                              prev.map((g, i) => i === idx ? { ...g, draft: "" } : g)
                            )
                          }
                          title="清空 POI（仅显示城市）"
                          className={clsx(
                            "text-xs px-2 py-0.5 rounded-lg border transition-all",
                            !group.draft
                              ? "bg-slate-600 border-slate-500 text-slate-200"
                              : "bg-slate-700/60 border-slate-600 text-slate-500 hover:text-slate-400"
                          )}
                        >
                          ✕ 清空
                        </button>
                      </div>
                    )}
                    {/* 自定义输入 + 保存/取消 */}
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={group.draft ?? ""}
                        onChange={(e) =>
                          setPoiGroups((prev) =>
                            prev.map((g, i) =>
                              i === idx ? { ...g, draft: e.target.value } : g
                            )
                          )
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSavePoiGroup(idx);
                          if (e.key === "Escape") handleToggleExpand(idx);
                        }}
                        placeholder={group.candidates?.length ? "或输入自定义名称..." : "输入 POI 名称（留空=仅显示城市）"}
                        className="flex-1 bg-slate-700 border border-blue-500 rounded px-2 py-1 text-sm text-white outline-none"
                      />
                      <button
                        onClick={() => handleSavePoiGroup(idx)}
                        disabled={group.saving}
                        className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded transition-colors flex-shrink-0"
                      >
                        {group.saving ? "..." : "保存"}
                      </button>
                      <button
                        onClick={() => handleToggleExpand(idx)}
                        className="px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors flex-shrink-0"
                      >
                        取消
                      </button>
                    </div>
                  </div>

                  {/* 照片级 POI：勾选后可单独修改，不影响同组其他照片 */}
                  {(group.selectedFiles?.length ?? 0) > 0 && (
                    <div className="flex items-center gap-2 flex-wrap bg-slate-900/50 border border-slate-700/40 rounded-lg px-2 py-1.5">
                      <span className="text-xs text-emerald-300">
                        已选 {group.selectedFiles?.length} 张
                      </span>
                      <input
                        type="text"
                        value={group.photoPoiDraft ?? ""}
                        onChange={(e) =>
                          setPoiGroups((prev) =>
                            prev.map((g, i) =>
                              i === idx ? { ...g, photoPoiDraft: e.target.value } : g
                            )
                          )
                        }
                        placeholder="这些照片的新 POI（留空=清除）"
                        className="flex-1 min-w-[10rem] bg-slate-700 border border-emerald-600/40 rounded px-2 py-1 text-xs text-white outline-none"
                      />
                      <button
                        onClick={() => handleSavePhotoPoi(idx)}
                        disabled={group.photoSaving}
                        className="text-xs px-2 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded"
                      >
                        {group.photoSaving ? "保存中..." : "修改所选照片"}
                      </button>
                      <button
                        onClick={() =>
                          setPoiGroups((prev) =>
                            prev.map((g, i) =>
                              i === idx ? { ...g, selectedFiles: [] } : g
                            )
                          )
                        }
                        className="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded"
                      >
                        取消选择
                      </button>
                    </div>
                  )}

                  {/* 缩略图网格（6列，展开时始终显示，无需再点一次） */}
                  {group.files && group.files.length > 0 && (
                    <div className="grid grid-cols-6 gap-1.5">
                      {group.files.map((f, fi) => (
                        <div key={fi} className="space-y-0.5">
                          <div
                            className="relative aspect-square bg-slate-900 rounded overflow-hidden border border-slate-700/40 cursor-zoom-in group/thumb"
                            title="点击查看大图"
                            onClick={() => setLightboxSrc(
                              backendUrl(`/api/media/thumbnail?path=${encodeURIComponent(f.path)}&width=1200&quality=90`)
                            )}
                          >
                            <label
                              className="absolute top-1 left-1 z-10 bg-slate-950/80 rounded p-0.5 cursor-pointer"
                              onClick={(e) => e.stopPropagation()}
                              title="勾选后可单独修改 POI"
                            >
                              <input
                                type="checkbox"
                                checked={(group.selectedFiles ?? []).includes(f.path)}
                                onChange={() =>
                                  setPoiGroups((prev) =>
                                    prev.map((g, i) => {
                                      if (i !== idx) return g;
                                      const current = g.selectedFiles ?? [];
                                      return {
                                        ...g,
                                        selectedFiles: current.includes(f.path)
                                          ? current.filter((p) => p !== f.path)
                                          : [...current, f.path],
                                      };
                                    })
                                  )
                                }
                                className="w-3.5 h-3.5 accent-emerald-500"
                              />
                            </label>
                            <img
                              src={backendUrl(`/api/media/thumbnail?path=${encodeURIComponent(f.path)}&width=120&quality=75`)}
                              alt={f.name}
                              loading="lazy"
                              className="w-full h-full object-cover group-hover/thumb:scale-105 transition-transform duration-150"
                              onError={(e) => {
                                (e.currentTarget as HTMLImageElement).style.display = "none";
                                const p = e.currentTarget.parentElement;
                                if (p) p.innerHTML = `<div class="w-full h-full flex items-center justify-center text-slate-600 text-xs">🎬</div>`;
                              }}
                            />
                          </div>
                          <p className="text-xs text-slate-600 truncate leading-tight" title={f.name}>
                            {f.name}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}

                  {group.files && group.files.length < group.file_count && (
                    <button
                      onClick={() => handleLoadMoreFiles(idx)}
                      disabled={group.loadingFiles}
                      className="w-full text-xs text-slate-500 hover:text-slate-300 py-1.5 border border-slate-700/50 hover:border-slate-600 rounded-lg transition-colors disabled:opacity-50"
                    >
                      {group.loadingFiles
                        ? "加载中..."
                        : `加载更多（还有 ${group.file_count - group.files.length} 张）`}
                    </button>
                  )}
                </div>
              )}
            </div>
            ))}
          </div>

        </div>
      )}

      {/* ── Step 3: 归档预览 ─────────────────────────────── */}
      {["geocode-done", "previewing", "done"].includes(step) && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">
              3️⃣ 行程预览
            </h2>
            {step === "geocode-done" ? (
              <button
                onClick={handlePreview}
                className="px-4 py-1.5 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-sm font-medium text-white transition-all"
              >
                📋 生成行程预览
              </button>
            ) : step === "previewing" ? (
              <span className="text-xs text-emerald-400 animate-pulse">
                生成中...
              </span>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-emerald-400">✅ 已完成</span>
                <button
                  onClick={handlePreview}
                  className="text-xs text-slate-500 hover:text-slate-300 border border-slate-700 px-2 py-1 rounded transition-colors"
                >
                  🔄 重新生成
                </button>
              </div>
            )}
          </div>

          {previewSummary && (
            <div className="grid grid-cols-4 gap-2">
              <StatBox
                value={previewSummary.total_files}
                label="总文件"
                color="text-blue-400"
              />
              <StatBox
                value={previewSummary.big_trips_created}
                label="大行程"
                color="text-purple-400"
              />
              <StatBox
                value={previewSummary.sub_trips_created}
                label="子行程"
                color="text-emerald-400"
              />
              <StatBox
                value={previewSummary.files_without_gps}
                label="无GPS文件"
                color="text-amber-400"
              />
            </div>
          )}
        </div>
      )}

      {/* ── 行程树 ────────────────────────────────────────── */}
      {step === "done" && tripStructure && (
        <div className="space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-300">
              🗂️ 行程树{" "}
              <span className="text-slate-500 font-normal">
                （{tripStructure.length} 大行程）
              </span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              按拍摄时间排序 · 点击名称可重命名 · 若需重组行程请前往「行程重建」
            </p>
          </div>

          <TripTree
            trips={tripStructure}
            onRenameBig={handleRenameBig}
            onRenameSub={handleRenameSub}
            onSplitSub={handleOpenSplit}
          />

          {/* 下一步按钮：在行程树下方，用户看完行程树后自然点击 */}
          <div className="flex justify-end pt-2">
            <button
              onClick={() => setCurrentPage("rebuilder")}
              className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 rounded-xl text-sm font-medium text-white shadow-lg shadow-emerald-500/20 transition-all"
            >
              🔧 下一步：行程重建 →
            </button>
          </div>
        </div>
      )}

      {/* ── 操作日志 ──────────────────────────────────────── */}
      {logs.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-700/30 rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-slate-500">操作日志</span>
            <button
              onClick={() => setLogs([])}
              className="text-xs text-slate-600 hover:text-slate-400"
            >
              清空
            </button>
          </div>
          <div className="space-y-0.5 max-h-28 overflow-y-auto">
            {logs.map((log, i) => (
              <div key={i} className="text-xs font-mono text-slate-400">
                {log}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 景区名归一化弹窗 ───────────────────────────────── */}
      {normalizeOpen && (() => {
        const cities = Array.from(
          new Set(poiGroups.map((g) => g.city).filter(Boolean))
        );
        const cityGroups = poiGroups.filter((g) => g.city === normalizeCity);
        const counts = new Map<string, number>();
        for (const g of cityGroups) {
          if (!g.area_name) continue;
          counts.set(g.area_name, (counts.get(g.area_name) || 0) + g.file_count);
        }
        const areas = Array.from(counts.entries());
        const allAreaNames = Array.from(
          new Set(poiGroups.map((g) => g.area_name).filter(Boolean))
        );
        return (
          <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6"
               onClick={() => setNormalizeOpen(false)}>
            <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-xl max-h-[85vh] flex flex-col"
                 onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700/60">
                <div>
                  <h3 className="text-sm font-semibold text-slate-200">🔗 景区名归一化</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    同一城市的变体名合并为规范名；别名会用于以后地理编码。
                  </p>
                </div>
                <button onClick={() => setNormalizeOpen(false)} className="text-slate-400 hover:text-white text-xl">✕</button>
              </div>

              <div className="px-5 py-3 space-y-3 overflow-y-auto">
                <label className="block text-xs text-slate-400">
                  城市
                  <select
                    value={normalizeCity}
                    onChange={(e) => {
                      setNormalizeCity(e.target.value);
                      setNormalizeSources([]);
                      setNormalizeCanonical("");
                    }}
                    className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-white"
                  >
                    {cities.map((city) => <option key={city} value={city}>{city}</option>)}
                  </select>
                </label>

                <div>
                  <div className="text-xs text-slate-400 mb-1">
                    选择要归一的变体名（当前城市的已扫描数据）
                  </div>
                  <div className="max-h-52 overflow-y-auto border border-slate-700/50 rounded divide-y divide-slate-800">
                    {areas.map(([name, count]) => (
                      <label key={name} className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-slate-800/60 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={normalizeSources.includes(name)}
                          onChange={() =>
                            setNormalizeSources((prev) =>
                              prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]
                            )
                          }
                          className="w-4 h-4 accent-amber-500"
                        />
                        <span className="text-slate-200 flex-1 truncate">{name}</span>
                        <span className="text-slate-500">{count} 张</span>
                      </label>
                    ))}
                    {areas.length === 0 && (
                      <div className="text-xs text-slate-500 p-3">该城市没有景区名</div>
                    )}
                  </div>
                </div>

                <label className="block text-xs text-slate-400">
                  规范景区名
                  <input
                    type="text"
                    value={normalizeCanonical}
                    onChange={(e) => setNormalizeCanonical(e.target.value)}
                    list="area-canonical-options"
                    placeholder="例如：三峡大坝旅游区"
                    className="mt-1 w-full bg-slate-700 border border-amber-600/40 rounded px-2 py-1.5 text-sm text-white outline-none"
                  />
                  <datalist id="area-canonical-options">
                    {allAreaNames.map((name) => <option key={name} value={name} />)}
                  </datalist>
                </label>

                <p className="text-[11px] text-amber-300/80">
                  会同时更新当前城市已扫描文件；以后地理编码遇到这些变体名会自动使用规范名。
                </p>
              </div>

              <div className="px-5 py-3 border-t border-slate-700/60 flex justify-end gap-2">
                <button
                  onClick={() => setNormalizeOpen(false)}
                  className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded"
                >
                  取消
                </button>
                <button
                  onClick={handleApplyAreaAlias}
                  disabled={normalizeSaving || normalizeSources.length === 0 || !normalizeCanonical.trim()}
                  className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs rounded"
                >
                  {normalizeSaving ? "应用中..." : "归一化并更新"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── 子行程拆分弹窗 ─────────────────────────────────── */}
      {splitTarget && (() => {
        const sub = tripStructure?.[splitTarget.bi]?.sub_trips?.[splitTarget.si];
        if (!sub) return null;
        const files = sub.files ?? [];
        const selectable = files.filter((f) => typeof f.planFileId === "number");
        const allIds = selectable.map((f) => f.planFileId!);
        const selectedCount = splitSelected.length;
        const canSplit = selectedCount > 0 && selectedCount < allIds.length;
        return (
          <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6"
               onClick={() => setSplitTarget(null)}>
            <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col"
                 onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700/60">
                <div>
                  <h3 className="text-sm font-semibold text-slate-200">
                    ✂️ 拆分「{sub.displayName}」
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    勾选要拆出的照片；剩余照片留在原名称下。
                  </p>
                </div>
                <button onClick={() => setSplitTarget(null)} className="text-slate-400 hover:text-white text-xl">✕</button>
              </div>

              <div className="flex items-center gap-2 px-5 py-2 border-b border-slate-700/40 text-xs">
                <span className="text-slate-400">已选 {selectedCount} / {allIds.length}</span>
                <button
                  onClick={() => setSplitSelected(allIds)}
                  className="px-2 py-0.5 border border-slate-600 rounded text-slate-300 hover:bg-slate-700"
                >
                  全选
                </button>
                <button
                  onClick={() => setSplitSelected([])}
                  className="px-2 py-0.5 border border-slate-600 rounded text-slate-300 hover:bg-slate-700"
                >
                  清空
                </button>
                <span className="text-slate-500 ml-auto">按景区/时间核对后再拆</span>
              </div>

              <div className="overflow-y-auto px-5 py-2 space-y-1">
                {selectable.map((f) => {
                  const id = f.planFileId!;
                  const checked = splitSelected.includes(id);
                  return (
                    <label
                      key={id}
                      className={clsx(
                        "flex items-center gap-3 px-2 py-1.5 rounded cursor-pointer border",
                        checked ? "bg-amber-900/20 border-amber-700/40" : "border-transparent hover:bg-slate-800/60"
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setSplitSelected((prev) =>
                            prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
                          )
                        }
                        className="w-4 h-4 accent-amber-500 flex-shrink-0"
                      />
                      <div className="w-10 h-10 bg-slate-800 rounded overflow-hidden flex-shrink-0">
                        <img
                          src={backendUrl(`/api/media/thumbnail?path=${encodeURIComponent(f.path)}&width=80&quality=60`)}
                          alt={f.name}
                          loading="lazy"
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-xs text-slate-200 truncate">{f.name}</div>
                        <div className="text-[10px] text-slate-500 truncate">
                          {f.datetime ? f.datetime.slice(0, 16).replace("T", " ") : "无时间"}
                          {f.areaName ? ` · ${f.areaName}` : ""}
                          {f.poi ? ` · ${f.poi}` : ""}
                        </div>
                      </div>
                    </label>
                  );
                })}
                {selectable.length === 0 && (
                  <div className="text-xs text-slate-500 py-6 text-center">
                    该子行程没有可拆分的照片
                  </div>
                )}
              </div>

              <div className="px-5 py-3 border-t border-slate-700/60 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400 flex-shrink-0">新子行程名称</span>
                  <input
                    type="text"
                    value={splitName}
                    onChange={(e) => setSplitName(e.target.value)}
                    placeholder="例如：三峡大坝"
                    className="flex-1 bg-slate-700 border border-amber-600/40 rounded px-2 py-1 text-sm text-white outline-none"
                  />
                </div>
                <div className="flex items-center justify-end gap-2">
                  <button
                    onClick={() => setSplitTarget(null)}
                    className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleSplitSub}
                    disabled={!canSplit || splitSaving}
                    className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs rounded"
                  >
                    {splitSaving ? "拆分中..." : `拆出 ${selectedCount} 张`}
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── 大图预览 Lightbox ─────────────────────────────── */}
      {lightboxSrc && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center cursor-zoom-out"
          onClick={() => setLightboxSrc(null)}
        >
          <img
            src={lightboxSrc}
            alt="大图预览"
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
          <button
            onClick={() => setLightboxSrc(null)}
            className="absolute top-4 right-5 text-white/70 hover:text-white text-3xl leading-none transition-colors"
          >
            ✕
          </button>
          <div className="absolute bottom-4 text-white/40 text-xs">
            点击任意位置关闭
          </div>
        </div>
      )}
    </div>
  );
}

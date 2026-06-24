/**
 * ScanPage.tsx
 * 扫描进度页面 + 行程树形视图
 *
 * 工作流程（3步）：
 *   1. 扫描文件夹（SSE 实时进度）
 *   2. 逆地理编码（GPS → 城市名）
 *   3. 归档预览（生成可交互行程树：重命名 / 合并子行程）
 */
import { useState, useRef } from "react";
import { useAppStore } from "@/store/appStore";
import type { BigTripData, SubTripData } from "@/store/appStore";
import clsx from "clsx";

const API = "http://localhost:17890";

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
}

interface ScanStats {
  total: number;
  withGps: number;
  withoutGps: number;
  errors: number;
  newFiles: number;
  skipped: number;
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
  poi: string;        // 当前 POI（空=仅城市级别）
  poi_type?: string;  // POI 类型字符串（新增，来自高德 place/around）
  lat?: number;       // 代表性坐标（用于候选 POI 查询）
  lon?: number;
  file_count: number;
  // 本地编辑状态
  draft?: string;     // 编辑草稿
  editing?: boolean;
  saving?: boolean;
  candidates?: PoiCandidate[] | null;  // 候选 POI 列表（按需加载）
  loadingCandidates?: boolean;
}

/** 根据 poi_type 字符串生成标签显示 */
function PoiTypeTag({ poiType }: { poiType?: string }) {
  if (!poiType) return null;
  let icon = "";
  let cls = "";
  let label = "";

  if (poiType.includes("风景名胜")) {
    icon = "🏞️"; cls = "bg-emerald-900/30 text-emerald-400 border-emerald-700/40"; label = "风景名胜";
  } else if (poiType.includes("热点地名") || poiType.includes("标志性建筑")) {
    icon = "📍"; cls = "bg-blue-900/30 text-blue-400 border-blue-700/40"; label = "热点地标";
  } else if (poiType.includes("自然地名")) {
    icon = "🌊"; cls = "bg-cyan-900/30 text-cyan-400 border-cyan-700/40"; label = "自然地名";
  } else if (poiType.includes("公园")) {
    icon = "🌳"; cls = "bg-green-900/30 text-green-400 border-green-700/40"; label = "公园";
  } else if (poiType.includes("博物馆") || poiType.includes("展览馆") || poiType.includes("美术馆")) {
    icon = "🏛️"; cls = "bg-indigo-900/30 text-indigo-400 border-indigo-700/40"; label = "文化场馆";
  } else if (poiType.includes("火车站")) {
    icon = "🚉"; cls = "bg-slate-800 text-slate-300 border-slate-600"; label = "火车站";
  } else if (poiType.includes("休闲") || poiType.includes("度假") || poiType.includes("商业街")) {
    icon = "🎪"; cls = "bg-purple-900/30 text-purple-400 border-purple-700/40"; label = "休闲";
  } else if (poiType.includes("村庄")) {
    icon = "⚠️"; cls = "bg-amber-900/30 text-amber-400 border-amber-700/40"; label = "村庄（请核实）";
  } else {
    icon = "📌"; cls = "bg-slate-800 text-slate-500 border-slate-700"; label = poiType.split(";")[0];
  }

  return (
    <span className={`flex-shrink-0 text-xs px-1.5 py-0.5 rounded border ${cls}`} title={poiType}>
      {icon} {label}
    </span>
  );
}

type FlowStep =
  | "idle"
  | "scanning"
  | "scan-done"
  | "geocoding"
  | "geocode-done"
  | "previewing"
  | "done";

// ── 进度条 ───────────────────────────────────────────────────

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="bg-slate-700 rounded-full h-2 overflow-hidden">
      <div
        className="bg-blue-500 h-2 rounded-full transition-all duration-100"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ── 统计数字格子 ─────────────────────────────────────────────

function StatBox({
  value,
  label,
  color = "text-slate-300",
}: {
  value: number | string;
  label: string;
  color?: string;
}) {
  return (
    <div className="bg-slate-800/80 rounded-lg p-3 text-center">
      <div className={clsx("text-xl font-bold font-mono", color)}>{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}

// ── 可内联编辑的文本标签 ─────────────────────────────────────

function EditableLabel({
  value,
  onSave,
  className,
  inputClassName,
}: {
  value: string;
  onSave: (newName: string) => void;
  className?: string;
  inputClassName?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDraft(value);
    setEditing(true);
    setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 10);
  };

  const confirm = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== value) onSave(trimmed);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value);
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={confirm}
        onKeyDown={(e) => {
          if (e.key === "Enter") confirm();
          if (e.key === "Escape") cancel();
        }}
        onClick={(e) => e.stopPropagation()}
        className={clsx(
          "bg-slate-700 border border-blue-500 rounded px-2 py-0.5 text-sm outline-none",
          inputClassName ?? "w-52 text-white"
        )}
      />
    );
  }

  return (
    <span
      onClick={startEdit}
      title="点击重命名（Enter 确认，Esc 取消）"
      className={clsx(
        "cursor-pointer group inline-flex items-center gap-1",
        className
      )}
    >
      {value}
      <span className="text-slate-600 group-hover:text-slate-400 text-xs transition-colors">
        ✏️
      </span>
    </span>
  );
}

// ── 缩略图面板（子行程文件预览）────────────────────────────

const THUMB_PAGE = 12; // 每次显示的缩略图数量

function SubTripThumbnails({ files }: { files: Array<{ name: string; path: string }> }) {
  const [showCount, setShowCount] = useState(THUMB_PAGE);

  if (!files || files.length === 0) {
    return (
      <div className="px-4 py-3 text-xs text-slate-600 italic">
        暂无文件信息（重新生成行程预览可获取）
      </div>
    );
  }

  const visible = files.slice(0, showCount);

  const openInFolder = (filePath: string) => {
    const electronAPI = (window as any).electronAPI;
    if (electronAPI?.showItemInFolder) {
      electronAPI.showItemInFolder(filePath);
    } else {
      alert(`文件路径：${filePath}`);
    }
  };

  return (
    <div className="px-4 pb-3 pt-2 bg-slate-950/40 space-y-3">
      {/* 操作栏 */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">
          {files.length} 个文件
          {files[0]?.name && (
            <span className="ml-2 font-mono text-slate-600">
              {files[0].name.slice(0, 30)}
              {files[0].name.length > 30 ? "..." : ""}
              {files.length > 1 ? ` 等` : ""}
            </span>
          )}
        </span>
        <button
          onClick={() => openInFolder(files[0].path)}
          title="在资源管理器中高亮显示第一张照片"
          className="text-xs text-slate-500 hover:text-blue-400 border border-slate-700 hover:border-blue-700/50 px-2 py-0.5 rounded transition-colors"
        >
          📁 在资源管理器中显示
        </button>
      </div>

      {/* 缩略图网格（4列） */}
      <div className="grid grid-cols-4 gap-2">
        {visible.map((file, i) => (
          <div
            key={i}
            className="group relative cursor-pointer"
            onClick={() => openInFolder(file.path)}
            title={file.name}
          >
            <div className="aspect-square bg-slate-800 rounded-lg overflow-hidden border border-slate-700/50 group-hover:border-blue-600/50 transition-colors">
              <img
                src={`${API}/api/media/thumbnail?path=${encodeURIComponent(file.path)}&width=160&quality=70`}
                alt={file.name}
                loading="lazy"
                className="w-full h-full object-cover"
                onError={(e) => {
                  // 加载失败（视频等）显示占位
                  const target = e.currentTarget;
                  target.style.display = "none";
                  const parent = target.parentElement;
                  if (parent) {
                    parent.innerHTML = `<div class="w-full h-full flex items-center justify-center text-2xl text-slate-600">🎬</div>`;
                  }
                }}
              />
            </div>
            <p className="mt-1 text-xs text-slate-500 truncate leading-tight">
              {file.name}
            </p>
          </div>
        ))}
      </div>

      {/* 加载更多 */}
      {files.length > showCount && (
        <button
          onClick={() => setShowCount((n) => n + THUMB_PAGE)}
          className="w-full text-xs text-slate-500 hover:text-slate-300 py-1.5 border border-slate-700/50 hover:border-slate-600 rounded-lg transition-colors"
        >
          加载更多（还有 {files.length - showCount} 个）
        </button>
      )}
    </div>
  );
}


// ── 行程树 ───────────────────────────────────────────────────

function TripTree({
  trips,
  onRenameBig,
  onRenameSub,
  onMergeSub,
}: {
  trips: BigTripData[];
  onRenameBig: (bi: number, name: string) => void;
  onRenameSub: (bi: number, si: number, name: string) => void;
  onMergeSub: (bi: number, si: number) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  // 展开缩略图预览的子行程 key 集合（格式："bi-si"）
  const [previewOpen, setPreviewOpen] = useState<Set<string>>(new Set());

  const toggle = (i: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  const togglePreview = (key: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPreviewOpen((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  if (trips.length === 0) {
    return (
      <div className="text-center py-10 text-slate-500 text-sm">
        暂无行程数据，请先完成扫描和预览
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {trips.map((big, bi) => {
        const isOpen = !collapsed.has(bi);
        return (
          <div
            key={bi}
            className="border border-slate-700/60 rounded-xl overflow-hidden"
          >
            {/* 大行程标题行 */}
            <div
              className="bg-slate-800 px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-800/80 transition-colors"
              onClick={() => toggle(bi)}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-slate-400 text-xs w-3 flex-shrink-0">
                  {isOpen ? "▼" : "▶"}
                </span>
                <span className="text-lg flex-shrink-0">📁</span>
                <EditableLabel
                  value={big.displayName || big.folder}
                  onSave={(name) => onRenameBig(bi, name)}
                  className="font-semibold text-blue-300 hover:text-blue-200 truncate"
                />
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400 flex-shrink-0 ml-4">
                {big.start_date && (
                  <span>
                    {big.start_date.slice(0, 10)} → {big.end_date?.slice(0, 10)}
                  </span>
                )}
                <span className="bg-blue-900/40 text-blue-400 px-2 py-0.5 rounded-full">
                  {big.total_files} 个文件
                </span>
                <span className="bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full">
                  {big.sub_trips.length} 子行程
                </span>
              </div>
            </div>

            {/* 子行程列表 */}
            {isOpen && (
              <div className="divide-y divide-slate-700/30">
                {big.sub_trips.length === 0 ? (
                  <div className="px-10 py-3 text-xs text-slate-500 italic">
                    无子行程
                  </div>
                ) : (
                  big.sub_trips.map((sub, si) => {
                    const previewKey = `${bi}-${si}`;
                    const isPreviewOpen = previewOpen.has(previewKey);
                    return (
                      <div key={si} className="bg-slate-900/30">
                        {/* 子行程主行 */}
                        <div className="px-4 py-2.5 flex items-center justify-between hover:bg-slate-900/50 transition-colors">
                          {/* 左侧：序号 + 图标 + 名称 + 地点 */}
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="text-slate-600 text-xs w-5 text-right font-mono flex-shrink-0">
                              {si + 1}
                            </span>
                            <span className="flex-shrink-0">📂</span>
                            <EditableLabel
                              value={sub.displayName || sub.folder}
                              onSave={(name) => onRenameSub(bi, si, name)}
                              className="text-sm text-emerald-300 hover:text-emerald-200 font-medium"
                            />
                            {sub.location && (
                              <span className="text-xs bg-slate-700/80 text-slate-300 px-2 py-0.5 rounded-full flex-shrink-0">
                                📍 {sub.location}
                              </span>
                            )}
                          </div>

                          {/* 右侧：日期 + 文件数 + 按钮 */}
                          <div className="flex items-center gap-2 text-xs text-slate-400 flex-shrink-0 ml-4">
                            {sub.start_date && (
                              <span>
                                {sub.start_date.slice(5, 10)} →{" "}
                                {sub.end_date?.slice(5, 10)}
                              </span>
                            )}
                            <span>{sub.file_count} 个文件</span>

                            {/* 缩略图预览按钮 */}
                            <button
                              onClick={(e) => togglePreview(previewKey, e)}
                              title={isPreviewOpen ? "收起预览" : "展开预览缩略图"}
                              className={clsx(
                                "px-2 py-0.5 border rounded text-xs transition-colors",
                                isPreviewOpen
                                  ? "bg-blue-900/40 border-blue-700/50 text-blue-400"
                                  : "bg-slate-700 border-slate-600 text-slate-400 hover:bg-slate-600 hover:text-slate-200"
                              )}
                            >
                              {isPreviewOpen ? "🙈 收起" : "🖼️ 预览"}
                            </button>

                            {/* 合并按钮 */}
                            {si < big.sub_trips.length - 1 && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onMergeSub(bi, si);
                                }}
                                title={`与下一子行程「${
                                  big.sub_trips[si + 1].displayName ||
                                  big.sub_trips[si + 1].folder
                                }」合并`}
                                className="px-2 py-0.5 bg-slate-700 hover:bg-amber-800/50 border border-slate-600 hover:border-amber-600/60 rounded text-slate-400 hover:text-amber-300 transition-colors"
                              >
                                合并↓
                              </button>
                            )}
                          </div>
                        </div>

                        {/* 缩略图预览面板 */}
                        {isPreviewOpen && (
                          <SubTripThumbnails files={sub.files || []} />
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
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
    addLog(`开始扫描：${sourceFolderPath}`);

    if (clearBeforeScan) {
      try {
        await fetch(`${API}/api/scan/clear`, { method: "DELETE" });
        addLog("已清空旧扫描数据");
      } catch (e) {
        addLog(`清空失败: ${e}`);
      }
    }

    try {
      const response = await fetch(`${API}/api/scan`, {
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
                };
                setScanStats(stats);
                addLog(
                  `扫描完成：共 ${stats.total} 个文件，新增 ${stats.newFiles}，有 GPS ${stats.withGps}`
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
      const res = await fetch(`${API}/api/scan/geocode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trip_type: tripType }),
      });
      const data = await res.json();
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
      const res = await fetch(`${API}/api/scan/geocode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trip_type: tripType, force_repoi: true }),
      });
      const data = await res.json();
      if (data.success) {
        setRepoiResult({ updated: data.updated, api_calls: data.api_calls || 0 });
        addLog(`补充 POI 完成：更新 ${data.updated} 个文件，调用高德 API ${data.api_calls || 0} 次`);
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

  // ── POI 审核：加载分组 ─────────────────────────────────────

  const handleLoadPoiGroups = async () => {
    setPoiGroupsLoading(true);
    try {
      const params = new URLSearchParams();
      if (sourceFolderPath) params.set("folder_path", sourceFolderPath);
      const res = await fetch(`${API}/api/scan/geocoded?${params}`);
      const json = await res.json();
      if (json.success) {
        setPoiGroups(json.data.groups.map((g: PoiGroup) => ({
          ...g,
          draft: g.poi,
          editing: false,
          saving: false,
        })));
      }
    } catch (e) {
      console.error("加载 POI 分组失败:", e);
    } finally {
      setPoiGroupsLoading(false);
    }
  };

  // ── POI 审核：进入编辑 + 加载候选 ────────────────────────────

  const handleStartEditPoi = async (idx: number) => {
    const group = poiGroups[idx];
    // 设置编辑状态 + 开始加载候选
    setPoiGroups((prev) =>
      prev.map((g, i) =>
        i === idx ? { ...g, editing: true, draft: g.poi, loadingCandidates: true, candidates: null } : g
      )
    );
    // 如果有坐标，按需拉取候选
    if (group.lat && group.lon) {
      try {
        const res = await fetch(
          `${API}/api/scan/poi-candidates?lat=${group.lat}&lon=${group.lon}`
        );
        const data = await res.json();
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
    } else {
      setPoiGroups((prev) =>
        prev.map((g, i) => i === idx ? { ...g, loadingCandidates: false, candidates: [] } : g)
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
      const res = await fetch(`${API}/api/scan/poi-group`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          province: group.province,
          city: group.city,
          old_poi: group.poi,
          new_poi: group.draft ?? "",
        }),
      });
      const json = await res.json();
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

  // ── 归档预览 ───────────────────────────────────────────────

  const handlePreview = async () => {
    if (!sourceFolderPath || !outputFolderPath) return;
    setStep("previewing");
    addLog("生成归档预览...");

    try {
      const res = await fetch(`${API}/api/archive/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: sourceFolderPath,
          output_path: outputFolderPath,
          options: {
            big_trip_threshold_days: settings.bigTripThresholdDays,
            small_trip_threshold_hours: settings.smallTripThresholdHours,
          },
        }),
      });

      const json = await res.json();
      if (json.success && json.data) {
        const s = json.data.summary;
        setPreviewSummary(s);

        // 构建文件映射：大行程文件夹::子行程文件夹 → 文件列表
        const fileMap = new Map<string, Array<{ name: string; path: string }>>();
        for (const p of json.data.preview as any[]) {
          const key = `${p.big_trip_folder}::${p.sub_trip_folder}`;
          if (!fileMap.has(key)) fileMap.set(key, []);
          fileMap.get(key)!.push({ name: p.file_name, path: p.original_path });
        }

        // 将后端结构转为可编辑本地结构（含文件列表）
        const parsed: BigTripData[] = (json.data.trips_structure as any[]).map(
          (big) => ({
            folder: big.folder,
            displayName: big.folder,
            start_date: big.start_date,
            end_date: big.end_date,
            total_files: big.total_files,
            sub_trips: (big.sub_trips as any[]).map((sub) => ({
              folder: sub.folder,
              displayName: sub.folder,
              location: sub.location || "",
              start_date: sub.start_date,
              end_date: sub.end_date,
              file_count: sub.file_count,
              files: fileMap.get(`${big.folder}::${sub.folder}`) || [],
            })),
          })
        );

        setTripStructure(parsed);
        addLog(
          `预览完成：${s.big_trips_created} 大行程，${s.sub_trips_created} 子行程，共 ${s.total_files} 个文件`
        );
        setStep("done");
      } else {
        addLog(`预览失败: ${JSON.stringify(json)}`);
        setStep("geocode-done");
      }
    } catch (e) {
      addLog(`预览请求失败: ${e}`);
      setStep("geocode-done");
    }
  };

  // ── 行程编辑 ───────────────────────────────────────────────

  const handleRenameBig = (bi: number, name: string) => {
    if (!tripStructure) return;
    setTripStructure(
      tripStructure.map((big, i) =>
        i === bi ? { ...big, displayName: name } : big
      )
    );
    addLog(`重命名大行程 → "${name}"`);
  };

  const handleRenameSub = (bi: number, si: number, name: string) => {
    if (!tripStructure) return;
    setTripStructure(
      tripStructure.map((big, i) =>
        i !== bi
          ? big
          : {
              ...big,
              sub_trips: big.sub_trips.map((sub, j) =>
                j === si ? { ...sub, displayName: name } : sub
              ),
            }
      )
    );
    addLog(`重命名子行程 → "${name}"`);
  };

  const handleMergeSub = (bi: number, si: number) => {
    if (!tripStructure) return;
    const big = tripStructure[bi];
    if (si >= big.sub_trips.length - 1) return;

    const a = big.sub_trips[si];
    const b = big.sub_trips[si + 1];

    const merged: SubTripData = {
      folder: a.folder,
      displayName: `${a.displayName} + ${b.displayName}`,
      location: [a.location, b.location].filter(Boolean).join(" / "),
      start_date: a.start_date,
      end_date: b.end_date,
      file_count: a.file_count + b.file_count,
    };

    setTripStructure(
      tripStructure.map((bt, i) =>
        i !== bi
          ? bt
          : {
              ...bt,
              sub_trips: [
                ...bt.sub_trips.slice(0, si),
                merged,
                ...bt.sub_trips.slice(si + 2),
              ],
            }
      )
    );
    addLog(`合并子行程：「${a.displayName}」+「${b.displayName}」`);
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
    <div className="p-6 max-w-4xl mx-auto space-y-5">
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
              ✅ 已补充 {repoiResult.updated} 个文件的景点 POI（高德 API {repoiResult.api_calls} 次）
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
          <div className="grid grid-cols-5 gap-2">
            <StatBox value={scanStats.total} label="总文件" color="text-blue-400" />
            <StatBox value={scanStats.newFiles} label="新增" color="text-emerald-400" />
            <StatBox value={scanStats.withGps} label="有GPS" color="text-emerald-400" />
            <StatBox value={scanStats.withoutGps} label="无GPS" color="text-amber-400" />
            <StatBox value={scanStats.errors} label="错误" color="text-red-400" />
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
                    { value: "abroad",   icon: "🌍", label: "境外行程", desc: "离线库（英文地名）" },
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
                ⚠️ 地理编码使用高德地图 API，对境外 GPS 坐标会返回错误或空结果。如有境外照片，请选择「境外」或「混合」行程。
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
                📍 POI 审核（可选）
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                高德识别到的景点地名，可手动修改后用于归档备注和文件夹命名
              </p>
            </div>
            <button
              onClick={handleLoadPoiGroups}
              disabled={poiGroupsLoading}
              className="text-xs text-slate-500 hover:text-slate-300 border border-slate-700 px-2 py-1 rounded transition-colors"
            >
              {poiGroupsLoading ? "加载中..." : "🔄 刷新"}
            </button>
          </div>

          {/* 分组列表 */}
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {poiGroups.map((group, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 px-3 py-2 bg-slate-800/50 rounded-lg text-sm"
              >
                {/* 城市 */}
                <span className="text-slate-300 font-medium min-w-[5rem] flex-shrink-0">
                  {group.city}
                </span>

                {/* POI 编辑区 */}
                <div className="flex-1 min-w-0">
                  {group.editing ? (
                    <div className="space-y-1.5">
                      {/* 候选 chips（按需加载）*/}
                      {group.loadingCandidates && (
                        <div className="text-xs text-slate-500 animate-pulse">⏳ 加载候选...</div>
                      )}
                      {group.candidates && group.candidates.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {group.candidates.map((c, ci) => {
                            // 提取 type emoji
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
                      {/* 自定义输入 */}
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
                          if (e.key === "Escape")
                            setPoiGroups((prev) =>
                              prev.map((g, i) =>
                                i === idx ? { ...g, editing: false, draft: g.poi } : g
                              )
                            );
                        }}
                        placeholder={group.candidates?.length ? "或输入自定义名称..." : "输入 POI 名称（留空=仅显示城市）"}
                        autoFocus={!group.candidates}
                        className="w-full bg-slate-700 border border-blue-500 rounded px-2 py-0.5 text-sm text-white outline-none"
                      />
                    </div>
                  ) : (
                    <span
                      onClick={() => handleStartEditPoi(idx)}
                      className="cursor-pointer hover:text-blue-300 transition-colors"
                    >
                      {group.poi ? (
                        <span className="text-emerald-300">{group.poi}</span>
                      ) : (
                        <span className="text-slate-500 italic">
                          （无 POI，仅显示城市）
                        </span>
                      )}
                      <span className="text-slate-600 hover:text-slate-400 text-xs ml-1.5">
                        ✏️
                      </span>
                    </span>
                  )}
                </div>

                {/* POI 类型标签 */}
                <PoiTypeTag poiType={group.poi_type} />

                {/* 文件数 */}
                <span className="text-xs text-slate-500 flex-shrink-0">
                  {group.file_count} 张
                </span>

                {/* 操作按钮 */}
                {group.editing && (
                  <div className="flex gap-1 flex-shrink-0">
                    <button
                      onClick={() => handleSavePoiGroup(idx)}
                      disabled={group.saving}
                      className="px-2 py-0.5 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded transition-colors"
                    >
                      {group.saving ? "..." : "保存"}
                    </button>
                    <button
                      onClick={() =>
                        setPoiGroups((prev) =>
                          prev.map((g, i) =>
                            i === idx
                              ? { ...g, editing: false, draft: g.poi }
                              : g
                          )
                        )
                      }
                      className="px-2 py-0.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors"
                    >
                      取消
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>

          <p className="text-xs text-slate-600">
            修改 POI 后会立即保存到数据库，归档备注格式：省份/城市/POI
          </p>
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
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-300">
                🗂️ 行程树{" "}
                <span className="text-slate-500 font-normal">
                  （{tripStructure.length} 大行程）
                </span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                点击名称可重命名 · 点击「合并↓」可合并相邻子行程
              </p>
            </div>
            <button
              onClick={() => setCurrentPage("archive")}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium text-white shadow-lg shadow-blue-500/20 transition-all"
            >
              📦 下一步：归档 →
            </button>
          </div>

          <TripTree
            trips={tripStructure}
            onRenameBig={handleRenameBig}
            onRenameSub={handleRenameSub}
            onMergeSub={handleMergeSub}
          />
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
    </div>
  );
}

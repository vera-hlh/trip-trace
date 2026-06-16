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

  const toggle = (i: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

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
                  big.sub_trips.map((sub, si) => (
                    <div
                      key={si}
                      className="px-4 py-2.5 flex items-center justify-between bg-slate-900/30 hover:bg-slate-900/50 transition-colors"
                    >
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

                      {/* 右侧：日期 + 文件数 + 合并按钮 */}
                      <div className="flex items-center gap-3 text-xs text-slate-400 flex-shrink-0 ml-4">
                        {sub.start_date && (
                          <span>
                            {sub.start_date.slice(5, 10)} →{" "}
                            {sub.end_date?.slice(5, 10)}
                          </span>
                        )}
                        <span>{sub.file_count} 个文件</span>

                        {/* 合并按钮（仅非最后一个子行程显示） */}
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
                  ))
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
  } = useAppStore();

  // 流程步骤
  const [step, setStep] = useState<FlowStep>(
    tripStructure ? "done" : "idle"
  );

  // 扫描状态
  const [scanEvents, setScanEvents] = useState<ScanEvent[]>([]);
  const [scanStats, setScanStats] = useState<ScanStats | null>(null);
  const [clearBeforeScan, setClearBeforeScan] = useState(false);

  // 地理编码状态
  const [geocodeResult, setGeocodeResult] = useState<{
    updated: number;
    errors: number;
  } | null>(null);

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
    addLog("开始逆地理编码...");
    try {
      const res = await fetch(`${API}/api/scan/geocode`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setGeocodeResult({ updated: data.updated, errors: data.errors || 0 });
        addLog(`地理编码完成：更新 ${data.updated} 个文件`);
        setStep("geocode-done");
      } else {
        addLog(`地理编码失败: ${JSON.stringify(data)}`);
        setStep("scan-done");
      }
    } catch (e) {
      addLog(`地理编码请求失败: ${e}`);
      setStep("scan-done");
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

        // 将后端结构转为可编辑本地结构
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
                  <span className="text-slate-500">✅ 勾选：</span>
                  更换了源文件夹、或想重新整理之前的扫描结果时使用
                </div>
                <div>
                  <span className="text-slate-500">⬜ 不勾选（默认）：</span>
                  增量扫描新照片，已有记录直接跳过，适合在原文件夹新增了照片后补扫
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
          ) : (
            <p className="text-xs text-slate-500">
              将 GPS 坐标转换为城市/省份名称，用于行程命名和归档文件夹
            </p>
          )}
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

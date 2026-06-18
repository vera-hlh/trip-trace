/**
 * ArchivePage.tsx
 * 归档预览 & 执行页面
 *
 * 功能：
 *   1. 展示来自 ScanPage 的行程树（用户已重命名/合并的版本）
 *   2. 参数配置面板（备注写入、备注模板）
 *   3. 确认后执行归档（SSE 实时进度）
 *   4. 完成摘要 + 打开输出目录
 */
import { useState } from "react";
import { useAppStore } from "@/store/appStore";
import type { BigTripData } from "@/store/appStore";
import clsx from "clsx";

const API = "http://localhost:17890";

// ── 类型定义 ─────────────────────────────────────────────────

interface ExecuteEvent {
  type: string;
  current?: number;
  total?: number;
  file?: string;
  target_folder?: string;
  reason?: string;
  message?: string;
  success?: boolean;
  // complete
  copied?: number;
  skipped?: number;
  errors?: number;
  remarks_written?: number;
  output_path?: string;
}

interface ExecuteStats {
  total: number;
  copied: number;
  skipped: number;
  errors: number;
  remarksWritten: number;
  outputPath: string;
}

type PageStep = "review" | "executing" | "done";

// ── 辅助：构建 trip_overrides（只包含被用户修改过的条目）──────

function buildTripOverrides(trips: BigTripData[]) {
  return trips
    .map((big) => {
      const subOverrides = big.sub_trips
        .filter((sub) => sub.displayName !== sub.folder)
        .map((sub) => ({
          original_folder: sub.folder,
          display_name: sub.displayName,
        }));

      if (big.displayName === big.folder && subOverrides.length === 0) {
        return null; // 未修改，跳过
      }

      return {
        original_folder: big.folder,
        display_name: big.displayName,
        sub_overrides: subOverrides,
      };
    })
    .filter(Boolean);
}

// ── 进度条 ───────────────────────────────────────────────────

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-slate-400">
        <span>{pct}%</span>
        <span>
          {value}/{max}
        </span>
      </div>
      <div className="bg-slate-700 rounded-full h-3 overflow-hidden">
        <div
          className="bg-emerald-500 h-3 rounded-full transition-all duration-150"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── 行程预览（只读，不可编辑） ────────────────────────────────

function TripPreview({ trips }: { trips: BigTripData[] }) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const toggle = (i: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  const totalFiles = trips.reduce((s, b) => s + b.total_files, 0);
  const totalSubs = trips.reduce((s, b) => s + b.sub_trips.length, 0);

  return (
    <div className="space-y-3">
      {/* 摘要 */}
      <div className="grid grid-cols-3 gap-3 text-center">
        {[
          { v: trips.length, l: "大行程", c: "text-blue-400" },
          { v: totalSubs, l: "子行程", c: "text-emerald-400" },
          { v: totalFiles, l: "总文件数", c: "text-slate-300" },
        ].map(({ v, l, c }) => (
          <div
            key={l}
            className="bg-slate-800/60 border border-slate-700/40 rounded-xl p-3"
          >
            <div className={clsx("text-2xl font-bold font-mono", c)}>{v}</div>
            <div className="text-xs text-slate-500 mt-0.5">{l}</div>
          </div>
        ))}
      </div>

      {/* 行程树 */}
      <div className="space-y-2">
        {trips.map((big, bi) => {
          const isOpen = !collapsed.has(bi);
          const isRenamed = big.displayName !== big.folder;
          return (
            <div
              key={bi}
              className="border border-slate-700/50 rounded-xl overflow-hidden"
            >
              <div
                className="bg-slate-800 px-4 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-800/80"
                onClick={() => toggle(bi)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-slate-500 text-xs">{isOpen ? "▼" : "▶"}</span>
                  <span>📁</span>
                  <span className="text-blue-300 font-semibold text-sm truncate">
                    {big.displayName}
                  </span>
                  {isRenamed && (
                    <span className="text-xs text-amber-400 bg-amber-900/30 border border-amber-700/40 px-1.5 py-0.5 rounded flex-shrink-0">
                      已重命名
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 flex-shrink-0 ml-3">
                  <span>{big.total_files} 个文件</span>
                  {big.start_date && (
                    <span>
                      {big.start_date.slice(0, 10)} → {big.end_date?.slice(0, 10)}
                    </span>
                  )}
                </div>
              </div>

              {isOpen && big.sub_trips.length > 0 && (
                <div className="divide-y divide-slate-700/30">
                  {big.sub_trips.map((sub, si) => {
                    const subRenamed = sub.displayName !== sub.folder;
                    return (
                      <div
                        key={si}
                        className="px-4 py-2 flex items-center justify-between bg-slate-900/30 text-sm"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-slate-600 text-xs w-4 text-right font-mono">
                            {si + 1}
                          </span>
                          <span>📂</span>
                          <span className="text-emerald-300 font-medium truncate">
                            {sub.displayName}
                          </span>
                          {sub.location && (
                            <span className="text-xs text-slate-400 bg-slate-700/60 px-1.5 py-0.5 rounded-full flex-shrink-0">
                              📍 {sub.location}
                            </span>
                          )}
                          {subRenamed && (
                            <span className="text-xs text-amber-400/70 flex-shrink-0">
                              ✏️
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-500 flex-shrink-0 ml-3">
                          <span>{sub.file_count} 个文件</span>
                          {sub.start_date && (
                            <span>
                              {sub.start_date.slice(5, 10)} →{" "}
                              {sub.end_date?.slice(5, 10)}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── 主页面 ───────────────────────────────────────────────────

export default function ArchivePage() {
  const {
    tripStructure,
    sourceFolderPath,
    outputFolderPath,
    settings,
    setCurrentPage,
  } = useAppStore();

  // 参数
  const [writeRemarks, setWriteRemarks] = useState(false);
  const [remarkTemplate, setRemarkTemplate] = useState(
    "地点: {province}/{city}/{township}/{poi}"
  );
  const [confirmed, setConfirmed] = useState(false);

  // 执行状态
  const [step, setStep] = useState<PageStep>("review");
  const [events, setEvents] = useState<ExecuteEvent[]>([]);
  const [stats, setStats] = useState<ExecuteStats | null>(null);

  const fatalEvent = events.find((e) => e.type === "fatal_error");
  const lastProgress = [...events]
    .reverse()
    .find((e) => e.type === "progress" || e.type === "skip");
  const errorEvents = events.filter((e) => e.type === "error");

  // ── 执行归档 ─────────────────────────────────────────────

  const handleExecute = async () => {
    if (!sourceFolderPath || !outputFolderPath || !tripStructure) return;

    setStep("executing");
    setEvents([]);
    setStats(null);

    const overrides = buildTripOverrides(tripStructure);

    try {
      const response = await fetch(`${API}/api/archive/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: sourceFolderPath,
          output_path: outputFolderPath,
          options: {
            big_trip_threshold_days: settings.bigTripThresholdDays,
            small_trip_threshold_hours: settings.smallTripThresholdHours,
          },
          write_remarks: writeRemarks,
          remark_template: remarkTemplate,
          trip_overrides: overrides,
        }),
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
              const ev: ExecuteEvent = JSON.parse(line.slice(6));
              setEvents((prev) => [...prev.slice(-500), ev]);

              if (ev.type === "complete") {
                setStats({
                  total: ev.total || 0,
                  copied: ev.copied || 0,
                  skipped: ev.skipped || 0,
                  errors: ev.errors || 0,
                  remarksWritten: ev.remarks_written || 0,
                  outputPath: ev.output_path || outputFolderPath,
                });
                setStep("done");
              }
            } catch {}
          }
        }
      }
    } catch (e) {
      setEvents((prev) => [
        ...prev,
        { type: "fatal_error", message: String(e) },
      ]);
      setStep("review");
    }
  };

  // ── 打开输出目录 ─────────────────────────────────────────

  const handleOpenOutput = () => {
    const electronAPI = (window as any).electronAPI;
    if (electronAPI?.openPath) {
      electronAPI.openPath(outputFolderPath);
    } else {
      alert(`归档已完成，请手动打开：${outputFolderPath}`);
    }
  };

  // ── 前置检查 ─────────────────────────────────────────────

  if (!tripStructure || tripStructure.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <div className="text-5xl mb-4 opacity-30">📦</div>
        <h1 className="text-xl font-bold text-slate-300 mb-2">需要先完成扫描</h1>
        <p className="text-sm text-slate-500 max-w-sm mb-6">
          请先在「扫描」页面完成文件扫描、地理编码和行程预览，再来这里执行归档。
        </p>
        <button
          onClick={() => setCurrentPage("scan")}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium text-white transition-all"
        >
          🔍 前往扫描页面 →
        </button>
      </div>
    );
  }

  // ── 渲染 ─────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5">
      {/* 页头 */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">📦 归档预览 & 执行</h1>
          <p className="text-xs text-slate-400 mt-1 font-mono break-all">
            {sourceFolderPath} → {outputFolderPath}
          </p>
        </div>
        {step === "done" && (
          <button
            onClick={() => setStep("review")}
            className="flex-shrink-0 text-xs text-slate-500 hover:text-slate-300 border border-slate-700 px-3 py-1.5 rounded-lg transition-colors"
          >
            🔄 重新归档
          </button>
        )}
      </div>

      {/* ── 审阅行程树 ────────────────────────────────────── */}
      {step !== "done" && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">
            🗂️ 行程结构预览
          </h2>
          <TripPreview trips={tripStructure} />
          <p className="text-xs text-slate-500">
            如需修改行程名称或合并子行程，请返回{" "}
            <button
              onClick={() => setCurrentPage("scan")}
              className="text-blue-400 hover:underline"
            >
              扫描页面
            </button>{" "}
            编辑后再来这里。
          </p>
        </div>
      )}

      {/* ── 参数配置 ─────────────────────────────────────── */}
      {step === "review" && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">⚙️ 归档参数</h2>

          {/* 参数汇总（只读） */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-800/60 rounded-lg p-3">
              <div className="text-xs text-slate-500 mb-1">大行程阈值</div>
              <div className="text-sm text-blue-400 font-medium">
                {settings.bigTripThresholdDays} 天
              </div>
            </div>
            <div className="bg-slate-800/60 rounded-lg p-3">
              <div className="text-xs text-slate-500 mb-1">子行程阈值</div>
              <div className="text-sm text-blue-400 font-medium">
                {settings.smallTripThresholdHours} 小时
              </div>
            </div>
            <div className="bg-slate-800/60 rounded-lg p-3 col-span-2">
              <div className="text-xs text-slate-500 mb-1">归档模式</div>
              <div className="text-sm text-emerald-400 font-medium">
                复制模式（原文件不删除）
              </div>
            </div>
          </div>

          {/* 备注写入 */}
          <div className="space-y-3 border-t border-slate-700/40 pt-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={writeRemarks}
                onChange={(e) => setWriteRemarks(e.target.checked)}
                className="accent-blue-500 w-4 h-4"
              />
              <div>
                <div className="text-sm text-slate-300 font-medium">
                  写入备注到文件 EXIF
                </div>
                <div className="text-xs text-slate-500">
                  将地理位置信息写入照片 UserComment / 视频 ©cmt 标签
                </div>
              </div>
            </label>

            {writeRemarks && (
              <div className="ml-7 space-y-2">
                <label className="block text-xs text-slate-400">备注模板：</label>
                <input
                  type="text"
                  value={remarkTemplate}
                  onChange={(e) => setRemarkTemplate(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
                />
                <p className="text-xs text-slate-500">
                  可用占位符：{"{country} {province} {city} {district} {trip_name} {sub_trip_name}"}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 确认执行 ─────────────────────────────────────── */}
      {step === "review" && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-4">
          <div className="p-3 bg-amber-900/20 border border-amber-700/40 rounded-lg text-xs text-amber-300 leading-relaxed">
            ⚠️{" "}
            <strong>即将执行归档：</strong>
            将把 {sourceFolderPath} 中的所有照片/视频
            <strong>复制</strong>到 {outputFolderPath}，按行程结构整理。
            原文件不会被删除。
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="accent-blue-500 w-4 h-4"
            />
            <span className="text-sm text-slate-300">
              我已确认归档参数，开始执行
            </span>
          </label>

          <button
            onClick={handleExecute}
            disabled={!confirmed}
            className={clsx(
              "w-full py-3 rounded-xl font-medium text-sm transition-all",
              confirmed
                ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-500/20"
                : "bg-slate-800 text-slate-500 cursor-not-allowed"
            )}
          >
            🚀 开始归档
          </button>
        </div>
      )}

      {/* ── 执行进度 ─────────────────────────────────────── */}
      {step === "executing" && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">
              ⏳ 归档中...
            </h2>
            <span className="text-xs text-slate-500 animate-pulse">
              请勿关闭程序
            </span>
          </div>

          {lastProgress?.total && (
            <ProgressBar
              value={lastProgress.current || 0}
              max={lastProgress.total}
            />
          )}

          {lastProgress && (
            <div className="text-xs text-slate-400 font-mono truncate">
              📄 {lastProgress.file}
              {lastProgress.target_folder && (
                <span className="text-slate-500 ml-2">
                  → {lastProgress.target_folder}
                </span>
              )}
            </div>
          )}

          {errorEvents.length > 0 && (
            <div className="p-3 bg-red-900/20 border border-red-700/40 rounded-lg">
              <div className="text-xs text-red-400 mb-1">
                ⚠️ {errorEvents.length} 个文件复制失败
              </div>
              {errorEvents.slice(0, 3).map((e, i) => (
                <div key={i} className="text-xs text-red-300/70 font-mono truncate">
                  {e.file}: {e.message}
                </div>
              ))}
            </div>
          )}

          {fatalEvent && (
            <div className="p-3 bg-red-900/30 border border-red-600/50 rounded-lg text-xs text-red-300">
              ❌ 致命错误：{fatalEvent.message}
            </div>
          )}
        </div>
      )}

      {/* ── 完成结果 ─────────────────────────────────────── */}
      {step === "done" && stats && (
        <div className="space-y-4">
          <div className="bg-emerald-900/20 border border-emerald-700/40 rounded-xl p-5">
            <h2 className="text-lg font-bold text-emerald-400 mb-4">
              ✅ 归档完成！
            </h2>
            <div className="grid grid-cols-4 gap-3 text-center mb-4">
              {[
                { v: stats.copied, l: "已复制", c: "text-emerald-400" },
                { v: stats.skipped, l: "已跳过", c: "text-slate-400" },
                { v: stats.errors, l: "失败", c: stats.errors > 0 ? "text-red-400" : "text-slate-500" },
                { v: stats.remarksWritten, l: "备注写入", c: "text-blue-400" },
              ].map(({ v, l, c }) => (
                <div
                  key={l}
                  className="bg-slate-800/60 border border-slate-700/40 rounded-lg p-3"
                >
                  <div className={clsx("text-2xl font-bold font-mono", c)}>
                    {v}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">{l}</div>
                </div>
              ))}
            </div>

            <div className="text-xs text-slate-400 font-mono break-all mb-4">
              📂 输出目录：{stats.outputPath}
            </div>

            <div className="flex gap-3">
              <button
                onClick={handleOpenOutput}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium text-white transition-all"
              >
                📂 打开输出目录
              </button>
              <button
                onClick={() => setCurrentPage("map")}
                className="flex-1 py-2.5 bg-slate-700 hover:bg-slate-600 rounded-xl text-sm font-medium text-slate-300 transition-all"
              >
                🗺️ 查看行程地图 →
              </button>
            </div>
          </div>

          {/* 错误详情 */}
          {stats.errors > 0 && errorEvents.length > 0 && (
            <div className="bg-red-900/20 border border-red-700/40 rounded-xl p-4">
              <h3 className="text-xs font-semibold text-red-400 mb-2">
                ⚠️ {stats.errors} 个文件失败：
              </h3>
              <div className="space-y-0.5 max-h-32 overflow-y-auto">
                {errorEvents.map((e, i) => (
                  <div key={i} className="text-xs font-mono text-red-300/70 truncate">
                    {e.file}: {e.message}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

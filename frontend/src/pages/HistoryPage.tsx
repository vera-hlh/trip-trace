/**
 * HistoryPage.tsx
 * 归档操作记录页面
 *
 * 展示每次归档操作的统计信息：
 * 时间、文件数量、行程数、耗时、API 调用次数、状态
 */
import { useEffect, useState } from "react";
import { useAppStore } from "@/store/appStore";
import clsx from "clsx";

const API = "http://localhost:17890";

// ── 类型 ─────────────────────────────────────────────────────

interface ArchiveLog {
  id: number;
  created_at: string;
  source_folder: string;
  output_folder: string;
  photo_count: number;
  video_count: number;
  copied_count: number;
  skipped_count: number;
  error_count: number;
  big_trips_count: number;
  sub_trips_count: number;
  api_calls_used: number;
  duration_sec: number;
  status: "success" | "partial" | "failed";
  trip_log_generated: boolean;
  remarks_written: number;
}

// ── 状态徽章 ─────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map = {
    success: { text: "成功", cls: "bg-emerald-900/40 text-emerald-400 border-emerald-700/50" },
    partial: { text: "部分成功", cls: "bg-amber-900/40 text-amber-400 border-amber-700/50" },
    failed:  { text: "失败", cls: "bg-red-900/40 text-red-400 border-red-700/50" },
  };
  const s = map[status as keyof typeof map] ?? map.success;
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded-full border font-medium", s.cls)}>
      {s.text}
    </span>
  );
}

// ── 格式化工具 ───────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function shortenPath(path: string, maxLen = 40): string {
  if (!path || path.length <= maxLen) return path;
  const parts = path.replace(/\\/g, "/").split("/");
  const last = parts[parts.length - 1];
  if (last.length >= maxLen - 5) return `.../${last}`;
  const head = path.slice(0, maxLen - last.length - 5);
  return `${head}.../${last}`;
}

// ── 单条记录卡片 ─────────────────────────────────────────────

function LogCard({ log, idx }: { log: ArchiveLog; idx: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl overflow-hidden">
      {/* 标题行 */}
      <div
        className="flex items-center gap-4 px-5 py-3.5 cursor-pointer hover:bg-slate-800/40 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {/* 序号 */}
        <span className="text-slate-600 text-xs font-mono w-5 text-right flex-shrink-0">
          {idx}
        </span>

        {/* 时间 */}
        <span className="text-slate-300 text-sm flex-shrink-0">
          {formatDate(log.created_at)}
        </span>

        {/* 文件夹名（截短） */}
        <span
          className="text-slate-400 text-xs font-mono flex-1 truncate"
          title={log.source_folder}
        >
          {shortenPath(log.source_folder)}
        </span>

        {/* 统计 */}
        <div className="flex items-center gap-3 text-xs text-slate-400 flex-shrink-0">
          <span>📷 {log.photo_count + log.video_count}</span>
          <span>🗂️ {log.big_trips_count}行程</span>
          <span>⏱ {formatDuration(log.duration_sec)}</span>
        </div>

        {/* 状态 */}
        <StatusBadge status={log.status} />

        {/* 展开箭头 */}
        <span className="text-slate-600 text-xs ml-1">{expanded ? "▲" : "▼"}</span>
      </div>

      {/* 详细内容 */}
      {expanded && (
        <div className="px-5 pb-4 border-t border-slate-700/30 pt-4 space-y-4">
          {/* 路径 */}
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div>
              <div className="text-slate-500 mb-1">源文件夹</div>
              <div className="text-slate-300 font-mono break-all">{log.source_folder}</div>
            </div>
            <div>
              <div className="text-slate-500 mb-1">输出目录</div>
              <div className="text-slate-300 font-mono break-all">{log.output_folder}</div>
            </div>
          </div>

          {/* 统计格 */}
          <div className="grid grid-cols-5 gap-2">
            {[
              { v: log.photo_count, l: "照片", c: "text-blue-400" },
              { v: log.video_count, l: "视频", c: "text-purple-400" },
              { v: log.copied_count, l: "已复制", c: "text-emerald-400" },
              { v: log.skipped_count, l: "已跳过", c: "text-slate-400" },
              { v: log.error_count, l: "失败", c: log.error_count > 0 ? "text-red-400" : "text-slate-600" },
            ].map(({ v, l, c }) => (
              <div key={l} className="bg-slate-800/60 rounded-lg p-3 text-center">
                <div className={clsx("text-lg font-bold font-mono", c)}>{v}</div>
                <div className="text-xs text-slate-500 mt-0.5">{l}</div>
              </div>
            ))}
          </div>

          {/* 行程统计 */}
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <span>🗂️ <strong className="text-slate-200">{log.big_trips_count}</strong> 大行程</span>
            <span>📂 <strong className="text-slate-200">{log.sub_trips_count}</strong> 子行程</span>
            <span>⏱ 耗时 <strong className="text-slate-200">{formatDuration(log.duration_sec)}</strong></span>
            {log.api_calls_used > 0 && (
              <span>🌍 高德 API <strong className="text-slate-200">{log.api_calls_used}</strong> 次</span>
            )}
            {log.remarks_written > 0 && (
              <span>✍️ 备注写入 <strong className="text-slate-200">{log.remarks_written}</strong> 个</span>
            )}
            {log.trip_log_generated && (
              <span className="text-emerald-400">📄 已生成 trip_log.md</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 主页面 ───────────────────────────────────────────────────

export default function HistoryPage() {
  const { setCurrentPage } = useAppStore();
  const [logs, setLogs] = useState<ArchiveLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadLogs = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API}/api/archive/logs?limit=50`);
      const json = await res.json();
      if (json.success) {
        setLogs(json.data.logs);
      } else {
        setError("加载失败");
      }
    } catch (e) {
      setError(`加载失败：${e}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  // ── 统计汇总 ─────────────────────────────────────────────

  const totalFiles = logs.reduce((s, l) => s + l.photo_count + l.video_count, 0);
  const totalCopied = logs.reduce((s, l) => s + l.copied_count, 0);
  const totalApiCalls = logs.reduce((s, l) => s + l.api_calls_used, 0);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">📋 操作记录</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            每次确认归档后自动记录，共 {logs.length} 条
          </p>
        </div>
        <button
          onClick={loadLogs}
          disabled={loading}
          className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-600 px-3 py-1.5 rounded-lg transition-colors"
        >
          {loading ? "加载中..." : "🔄 刷新"}
        </button>
      </div>

      {/* 汇总统计 */}
      {logs.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { v: totalFiles, l: "累计处理文件", c: "text-blue-400" },
            { v: totalCopied, l: "累计复制文件", c: "text-emerald-400" },
            { v: totalApiCalls, l: "累计 API 调用", c: "text-purple-400" },
          ].map(({ v, l, c }) => (
            <div key={l} className="bg-slate-900/60 border border-slate-700/40 rounded-xl p-4 text-center">
              <div className={clsx("text-2xl font-bold font-mono", c)}>{v}</div>
              <div className="text-xs text-slate-500 mt-1">{l}</div>
            </div>
          ))}
        </div>
      )}

      {/* 记录列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-500">
          <div className="text-center">
            <div className="text-3xl mb-3 animate-pulse">📋</div>
            <div>加载中...</div>
          </div>
        </div>
      ) : error ? (
        <div className="text-center py-16 text-red-400">{error}</div>
      ) : logs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-slate-500">
          <div className="text-5xl mb-4 opacity-30">📋</div>
          <div className="text-sm">暂无操作记录</div>
          <div className="text-xs mt-1 opacity-60">执行归档后，记录将出现在这里</div>
          <button
            onClick={() => setCurrentPage("archive")}
            className="mt-5 px-5 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm text-white transition-all"
          >
            📦 前往归档页面 →
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {logs.map((log, idx) => (
            <LogCard key={log.id} log={log} idx={logs.length - idx} />
          ))}
        </div>
      )}
    </div>
  );
}

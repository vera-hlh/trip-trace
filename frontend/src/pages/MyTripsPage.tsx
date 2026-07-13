/**
 * MyTripsPage.tsx
 * 我的旅迹：已归档大行程记录列表 + 海报预览
 *
 * 布局：左宽右窄两列
 *   左（约60%）：记录列表（每页6条）+ 两侧垂直翻页箭头 + 底部页码 + 排序切换
 *   右（约40%）：选中记录的海报预览区（阶段一为占位，阶段二接入真实海报图）
 */
import { useEffect, useState, useCallback } from "react";
import { useAppStore } from "@/store/appStore";
import clsx from "clsx";

const API = "http://localhost:17890";
const PAGE_SIZE = 6;
const MAX_PAGE_NUMBERS = 5;

// ── 类型 ─────────────────────────────────────────────────────

interface TripRecord {
  id: number;
  big_trip_name: string;
  start_date: string | null;
  end_date: string | null;
  sub_trip_count: number;
  total_files: number;
  output_folder: string;
  big_trip_folder: string;
  created_at: string;
  poster_path: string | null;
}

interface SubTripDetail {
  name: string;
  location: string;
  start_date: string | null;
  end_date: string | null;
  file_count: number;
}

type SortOption = "trip_date_desc" | "trip_date_asc" | "created_at_desc" | "created_at_asc";

const SORT_LABELS: Record<SortOption, string> = {
  trip_date_desc:  "行程日期 ↓",
  trip_date_asc:   "行程日期 ↑",
  created_at_desc: "生成时间 ↓",
  created_at_asc:  "生成时间 ↑",
};

// ── 格式化工具 ───────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return "未知";
  try {
    return iso.slice(0, 10);
  } catch {
    return "未知";
  }
}

function formatDateTime(iso: string): string {
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

function calcDays(start: string | null, end: string | null): number {
  if (!start || !end) return 0;
  try {
    const s = new Date(start);
    const e = new Date(end);
    return Math.max(1, Math.round((e.getTime() - s.getTime()) / 86400000) + 1);
  } catch {
    return 0;
  }
}

// ── 页码计算（滑动窗口，最多显示5个）─────────────────────────

function getPageNumbers(current: number, total: number, maxVisible = MAX_PAGE_NUMBERS): number[] {
  if (total <= maxVisible) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  let start = Math.max(1, current - Math.floor(maxVisible / 2));
  let end = start + maxVisible - 1;
  if (end > total) {
    end = total;
    start = end - maxVisible + 1;
  }
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

// ── 记录条目 ─────────────────────────────────────────────────

function RecordItem({
  record,
  selected,
  onClick,
}: {
  record: TripRecord;
  selected: boolean;
  onClick: () => void;
}) {
  const days = calcDays(record.start_date, record.end_date);
  return (
    <button
      onClick={onClick}
      className={clsx(
        "w-full text-left px-4 py-3 rounded-xl border transition-all",
        selected
          ? "bg-blue-900/30 border-blue-500/60 shadow-lg shadow-blue-500/10"
          : "bg-slate-800/50 border-slate-700/50 hover:border-slate-600 hover:bg-slate-800/80"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className={clsx(
            "font-medium text-sm truncate",
            selected ? "text-blue-300" : "text-slate-200"
          )}>
            📁 {record.big_trip_name}
          </div>
          <div className="text-xs text-slate-500 mt-1 flex items-center gap-2 flex-wrap">
            <span>{formatDate(record.start_date)} → {formatDate(record.end_date)}</span>
            {days > 0 && <span className="text-slate-600">· {days}天</span>}
          </div>
        </div>
        <div className="flex-shrink-0 text-right">
          <span className="text-xs bg-emerald-900/30 text-emerald-400 border border-emerald-700/40 px-2 py-0.5 rounded-full">
            {record.sub_trip_count} 子行程
          </span>
        </div>
      </div>
      <div className="text-xs text-slate-600 mt-2">
        生成于 {formatDateTime(record.created_at)}
      </div>
    </button>
  );
}

// ── 海报预览区（阶段一：占位；阶段二：接入真实海报图）──────────

function PosterPreview({ record }: { record: TripRecord | null }) {
  const [detail, setDetail] = useState<{ sub_trips: SubTripDetail[] } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!record) {
      setDetail(null);
      return;
    }
    setLoading(true);
    fetch(`${API}/api/trips/records/${record.id}`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success) setDetail(json.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [record?.id]);

  if (!record) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-slate-500 p-8">
        <div className="text-5xl mb-3 opacity-30">🗺️</div>
        <div className="text-sm">从左侧选择一条记录</div>
        <div className="text-xs mt-1 opacity-60">查看该行程的海报预览</div>
      </div>
    );
  }

  const days = calcDays(record.start_date, record.end_date);

  return (
    <div className="h-full flex flex-col p-5">
      {/* 海报占位区（阶段二将替换为真实生成的海报图片） */}
      <div className="flex-1 bg-slate-800/60 border border-slate-700/40 rounded-xl flex flex-col items-center justify-center p-6 mb-4 min-h-[280px]">
        <div className="text-4xl mb-3 opacity-40">🖼️</div>
        <div className="text-sm text-slate-500 text-center">
          海报生成功能开发中
          <div className="text-xs mt-1 opacity-60">（阶段二：自动生成行程路线海报）</div>
        </div>
      </div>

      {/* 基础信息卡片 */}
      <div className="space-y-3">
        <h3 className="text-lg font-bold text-slate-100">{record.big_trip_name}</h3>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">行程时间</div>
            <div className="text-slate-200">
              {formatDate(record.start_date)} → {formatDate(record.end_date)}
            </div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">行程天数</div>
            <div className="text-slate-200">{days} 天</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">子行程数</div>
            <div className="text-slate-200">{record.sub_trip_count} 段</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">媒体文件</div>
            <div className="text-slate-200">{record.total_files} 个</div>
          </div>
        </div>

        {/* 子行程路线列表 */}
        {loading ? (
          <div className="text-xs text-slate-500 animate-pulse py-2">加载子行程详情...</div>
        ) : detail?.sub_trips && detail.sub_trips.length > 0 ? (
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-2">子行程路线</div>
            <div className="space-y-1.5">
              {detail.sub_trips.map((sub, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-slate-600 font-mono w-4">{i + 1}</span>
                  <span className="text-emerald-300 flex-1 truncate">{sub.name}</span>
                  {sub.location && (
                    <span className="text-slate-500 truncate max-w-[100px]">📍{sub.location}</span>
                  )}
                  <span className="text-slate-600 flex-shrink-0">{sub.file_count}张</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {/* 打开归档目录 */}
        <button
          onClick={() => {
            const electronAPI = (window as any).electronAPI;
            const fullPath = `${record.output_folder}\\${record.big_trip_folder}`;
            if (electronAPI?.openPath) {
              electronAPI.openPath(fullPath);
            } else {
              alert(`归档目录：\n${fullPath}`);
            }
          }}
          className="w-full text-xs text-slate-400 hover:text-emerald-400 border border-slate-700 hover:border-emerald-700/50 rounded-lg py-2 transition-colors"
        >
          📂 打开归档目录
        </button>
      </div>
    </div>
  );
}

// ── 主页面 ───────────────────────────────────────────────────

export default function MyTripsPage() {
  const { setCurrentPage } = useAppStore();

  const [records, setRecords] = useState<TripRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState<SortOption>("trip_date_desc");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const loadRecords = useCallback(async (p: number, s: SortOption) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(p),
        page_size: String(PAGE_SIZE),
        sort: s,
      });
      const res = await fetch(`${API}/api/trips/records?${params}`);
      const json = await res.json();
      if (json.success) {
        setRecords(json.data.records);
        setPage(json.data.page);
        setTotalPages(json.data.total_pages);
        setTotal(json.data.total);
        // 默认选中第一条
        if (json.data.records.length > 0) {
          setSelectedId(json.data.records[0].id);
        } else {
          setSelectedId(null);
        }
      }
    } catch (e) {
      console.error("加载我的旅迹记录失败:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRecords(1, sort);
  }, [sort, loadRecords]);

  const goToPage = (p: number) => {
    if (p < 1 || p > totalPages || p === page) return;
    loadRecords(p, sort);
  };

  const selectedRecord = records.find((r) => r.id === selectedId) || null;
  const pageNumbers = getPageNumbers(page, totalPages);

  // ── 空状态 ───────────────────────────────────────────────

  if (!loading && total === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <div className="text-5xl mb-4 opacity-30">📔</div>
        <h1 className="text-xl font-bold text-slate-300 mb-2">还没有归档记录</h1>
        <p className="text-sm text-slate-500 max-w-sm mb-6">
          完成一次归档后，行程记录会自动出现在这里，方便你随时回顾旅程。
        </p>
        <button
          onClick={() => setCurrentPage("folder-setup")}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium text-white transition-all"
        >
          📁 开始归档 →
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">📔 我的旅迹</h1>
          <p className="text-xs text-slate-400 mt-0.5">共 {total} 条已归档行程记录</p>
        </div>
        {/* 排序切换 */}
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortOption)}
          className="text-xs bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-300 outline-none cursor-pointer"
        >
          {Object.entries(SORT_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      {/* 主体：左宽右窄两列 */}
      <div className="grid grid-cols-5 gap-5 items-start">
        {/* 左列（3/5，记录列表）*/}
        <div className="col-span-3 space-y-3">
          <div className="relative">
            {/* 左箭头 */}
            {totalPages > 1 && (
              <button
                onClick={() => goToPage(page - 1)}
                disabled={page <= 1}
                className={clsx(
                  "absolute left-[-2.25rem] top-1/2 -translate-y-1/2 z-10",
                  "w-8 h-8 rounded-full flex items-center justify-center transition-colors",
                  page <= 1
                    ? "text-slate-700 cursor-not-allowed"
                    : "text-slate-400 hover:text-blue-400 hover:bg-slate-800"
                )}
              >
                ◀
              </button>
            )}

            {/* 记录列表 */}
            <div className="space-y-2 min-h-[420px]">
              {loading ? (
                <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
                  加载中...
                </div>
              ) : (
                records.map((r) => (
                  <RecordItem
                    key={r.id}
                    record={r}
                    selected={selectedId === r.id}
                    onClick={() => setSelectedId(r.id)}
                  />
                ))
              )}
            </div>

            {/* 右箭头 */}
            {totalPages > 1 && (
              <button
                onClick={() => goToPage(page + 1)}
                disabled={page >= totalPages}
                className={clsx(
                  "absolute right-[-2.25rem] top-1/2 -translate-y-1/2 z-10",
                  "w-8 h-8 rounded-full flex items-center justify-center transition-colors",
                  page >= totalPages
                    ? "text-slate-700 cursor-not-allowed"
                    : "text-slate-400 hover:text-blue-400 hover:bg-slate-800"
                )}
              >
                ▶
              </button>
            )}
          </div>

          {/* 页码 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-end gap-1.5 pt-1">
              <span className="text-xs text-slate-600 mr-2">共 {totalPages} 页</span>
              {pageNumbers[0] > 1 && (
                <>
                  <button
                    onClick={() => goToPage(1)}
                    className="w-7 h-7 text-xs rounded-lg text-slate-400 hover:bg-slate-800 transition-colors"
                  >
                    1
                  </button>
                  {pageNumbers[0] > 2 && <span className="text-slate-600 text-xs">…</span>}
                </>
              )}
              {pageNumbers.map((p) => (
                <button
                  key={p}
                  onClick={() => goToPage(p)}
                  className={clsx(
                    "w-7 h-7 text-xs rounded-lg transition-colors",
                    p === page
                      ? "bg-blue-600 text-white font-medium"
                      : "text-slate-400 hover:bg-slate-800"
                  )}
                >
                  {p}
                </button>
              ))}
              {pageNumbers[pageNumbers.length - 1] < totalPages && (
                <>
                  {pageNumbers[pageNumbers.length - 1] < totalPages - 1 && (
                    <span className="text-slate-600 text-xs">…</span>
                  )}
                  <button
                    onClick={() => goToPage(totalPages)}
                    className="w-7 h-7 text-xs rounded-lg text-slate-400 hover:bg-slate-800 transition-colors"
                  >
                    {totalPages}
                  </button>
                </>
              )}
            </div>
          )}
        </div>

        {/* 右列（2/5，海报预览）*/}
        <div className="col-span-2 sticky top-4 bg-slate-900/60 border border-slate-700/50 rounded-xl min-h-[500px]">
          <PosterPreview record={selectedRecord} />
        </div>
      </div>
    </div>
  );
}

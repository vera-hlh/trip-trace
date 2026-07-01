/**
 * TripRebuilderPage.tsx
 * 行程重建页面
 *
 * 功能：
 *   将子行程分组到用户自定义「容器」中，生成额外目录层级
 *   三种归档模式：行程树 / 重建 / 混合
 *
 * 布局：2:1 双栏
 *   左侧 (2/3)：行程树参考（可选中子行程）
 *   右侧 (1/3)：容器管理 + 归档模式选择（sticky）
 *
 * 输出结构示例（重建模式）：
 *   大行程/
 *     └─ 漠河之行/          ← 容器层（新增）
 *          ├─ 05_漠河最北/   ← 原子行程完整保留
 *          └─ 06_漠河北红/
 */
import { useState, useRef, useEffect } from "react";
import { useAppStore } from "@/store/appStore";
import type { TripContainer, ArchiveMode } from "@/store/appStore";
import clsx from "clsx";

const API = "http://localhost:17890";

// ── ID 生成 ──────────────────────────────────────────────────
let _ctr = 0;
function genId() {
  return `c-${Date.now()}-${++_ctr}`;
}

// ── 缩略图小格（4列迷你预览）────────────────────────────────

function MiniThumbs({ files }: { files?: Array<{ name: string; path: string }> }) {
  if (!files?.length) return null;
  const visible = files.slice(0, 8);
  return (
    <div className="flex gap-1 mt-1.5 flex-wrap">
      {visible.map((f, i) => (
        <div
          key={i}
          className="w-9 h-9 bg-slate-800 rounded overflow-hidden border border-slate-700/40 flex-shrink-0"
        >
          <img
            src={`${API}/api/media/thumbnail?path=${encodeURIComponent(f.path)}&width=72&quality=55`}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
              const p = e.currentTarget.parentElement;
              if (p) p.innerHTML = `<div class="w-full h-full flex items-center justify-center text-slate-600 text-xs">🎬</div>`;
            }}
          />
        </div>
      ))}
      {files.length > 8 && (
        <div className="w-9 h-9 bg-slate-800/60 rounded border border-slate-700/40 flex items-center justify-center text-xs text-slate-500">
          +{files.length - 8}
        </div>
      )}
    </div>
  );
}

// ── 可内联编辑的标签 ────────────────────────────────────────

function InlineEdit({
  value,
  onSave,
  placeholder,
}: {
  value: string;
  onSave: (v: string) => void;
  placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          const v = draft.trim();
          if (v) onSave(v);
          setEditing(false);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const v = draft.trim();
            if (v) onSave(v);
            setEditing(false);
          }
          if (e.key === "Escape") setEditing(false);
        }}
        className="bg-slate-700 border border-blue-500 rounded px-2 py-0.5 text-sm text-white outline-none w-40"
      />
    );
  }

  return (
    <span
      onClick={() => { setDraft(value); setEditing(true); }}
      title="点击重命名"
      className="cursor-pointer hover:text-blue-300 transition-colors group"
    >
      {value}
      <span className="ml-1 text-slate-600 group-hover:text-slate-400 text-xs">✏️</span>
    </span>
  );
}

// ── 归档模式选择器 ──────────────────────────────────────────

const MODE_CONFIG: Record<
  "tree" | "rebuild" | "mixed",
  { icon: string; label: string; desc: string; color: string }
> = {
  tree: {
    icon: "🌲",
    label: "行程树",
    desc: "完全按行程树，忽略容器设置",
    color: "border-blue-600 bg-blue-900/30 text-blue-300",
  },
  rebuild: {
    icon: "📦",
    label: "重建行程",
    desc: "所有子行程必须分配到容器",
    color: "border-amber-600 bg-amber-900/30 text-amber-300",
  },
  mixed: {
    icon: "🔀",
    label: "混合",
    desc: "容器内按容器层级，其余按行程树",
    color: "border-purple-600 bg-purple-900/30 text-purple-300",
  },
};

function ModeSelector({
  mode,
  onChange,
}: {
  mode: ArchiveMode;
  onChange: (m: ArchiveMode) => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs text-slate-400 font-medium">归档模式（必选）</div>
      <div className="space-y-1.5">
        {(["tree", "rebuild", "mixed"] as const).map((m) => {
          const cfg = MODE_CONFIG[m];
          const active = mode === m;
          return (
            <button
              key={m}
              onClick={() => onChange(active ? null : m)}
              className={clsx(
                "w-full text-left px-3 py-2 rounded-lg border text-xs transition-all",
                active
                  ? cfg.color
                  : "border-slate-700/50 bg-slate-800/40 text-slate-400 hover:border-slate-600 hover:text-slate-300"
              )}
            >
              <div className="font-medium">
                {cfg.icon} {cfg.label}
              </div>
              <div className={clsx("mt-0.5 opacity-80", active ? "" : "text-slate-500")}>
                {cfg.desc}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── 主页面 ───────────────────────────────────────────────────

export default function TripRebuilderPage() {
  const {
    tripStructure,
    archiveMode,
    setArchiveMode,
    updateBigTripContainers,
    setCurrentPage,
  } = useAppStore();

  // 当前激活（右侧管理的）大行程下标
  const [activeBigIdx, setActiveBigIdx] = useState(0);
  // 当前已选中的子行程下标（仅属于 activeBigIdx）
  const [selectedSubs, setSelectedSubs] = useState<number[]>([]);
  // 移入下拉是否显示
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  // 左侧大行程是否折叠
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  // 左侧子行程缩略图是否展开
  const [thumbsOpen, setThumbsOpen] = useState<Set<string>>(new Set());
  // 容器重命名状态
  const moveMenuRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭移入下拉
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (moveMenuRef.current && !moveMenuRef.current.contains(e.target as Node)) {
        setShowMoveMenu(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── 无行程数据时的空状态 ────────────────────────────────────

  if (!tripStructure || tripStructure.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <div className="text-5xl mb-4 opacity-30">🔧</div>
        <h1 className="text-xl font-bold text-slate-300 mb-2">需要先完成行程预览</h1>
        <p className="text-sm text-slate-500 max-w-sm mb-6">
          请先在「扫描」页面完成文件扫描、地理编码和行程预览，再来这里重建行程结构。
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

  // ── 容器操作函数 ────────────────────────────────────────────

  const getContainers = (bigIdx: number): TripContainer[] =>
    tripStructure[bigIdx]?.containers || [];

  const setContainers = (bigIdx: number, containers: TripContainer[]) =>
    updateBigTripContainers(bigIdx, containers);

  /** subTripIndex -> containerDisplayName（若已分配） */
  const getAssignedMap = (bigIdx: number): Map<number, string> => {
    const map = new Map<number, string>();
    for (const c of getContainers(bigIdx)) {
      for (const idx of c.subTripIndices) {
        map.set(idx, c.displayName);
      }
    }
    return map;
  };

  /** 未分配子行程数量（仅 activeBigIdx） */
  const unassignedCount = (bigIdx: number): number => {
    const assigned = getAssignedMap(bigIdx);
    return tripStructure[bigIdx].sub_trips.filter((_, i) => !assigned.has(i)).length;
  };

  /** 全行程未分配总数（重建模式下使用） */
  const totalUnassigned = (): number =>
    tripStructure.reduce((sum, _, i) => sum + unassignedCount(i), 0);

  // 切换子行程选中
  const toggleSelect = (bigIdx: number, subIdx: number) => {
    if (bigIdx !== activeBigIdx) {
      // 切换到另一个大行程
      setActiveBigIdx(bigIdx);
      setSelectedSubs([subIdx]);
      return;
    }
    setSelectedSubs((prev) =>
      prev.includes(subIdx) ? prev.filter((i) => i !== subIdx) : [...prev, subIdx]
    );
  };

  // 移入现有容器
  const moveToContainer = (containerId: string) => {
    const containers = getContainers(activeBigIdx);
    const updated = containers.map((c) =>
      c.id === containerId
        ? { ...c, subTripIndices: [...new Set([...c.subTripIndices, ...selectedSubs])] }
        : c
    );
    setContainers(activeBigIdx, updated);
    setSelectedSubs([]);
    setShowMoveMenu(false);
  };

  // 移入新建容器
  const moveToNewContainer = () => {
    const firstIdx = selectedSubs[0];
    const firstSub = tripStructure[activeBigIdx].sub_trips[firstIdx];
    const newContainer: TripContainer = {
      id: genId(),
      displayName: firstSub?.displayName || firstSub?.folder || "新容器",
      subTripIndices: [...selectedSubs],
    };
    setContainers(activeBigIdx, [...getContainers(activeBigIdx), newContainer]);
    setSelectedSubs([]);
    setShowMoveMenu(false);
  };

  // 从容器移出
  const removeFromContainer = (bigIdx: number, containerId: string, subIdx: number) => {
    const updated = getContainers(bigIdx)
      .map((c) =>
        c.id === containerId
          ? { ...c, subTripIndices: c.subTripIndices.filter((i) => i !== subIdx) }
          : c
      )
      .filter((c) => c.subTripIndices.length > 0); // 移出后空容器自动删除
    setContainers(bigIdx, updated);
  };

  // 删除整个容器（子行程回到未分配池）
  const deleteContainer = (bigIdx: number, containerId: string) => {
    setContainers(
      bigIdx,
      getContainers(bigIdx).filter((c) => c.id !== containerId)
    );
  };

  // 重命名容器
  const renameContainer = (bigIdx: number, containerId: string, name: string) => {
    setContainers(
      bigIdx,
      getContainers(bigIdx).map((c) =>
        c.id === containerId ? { ...c, displayName: name } : c
      )
    );
  };

  // 新建空容器
  const addEmptyContainer = () => {
    const seq = getContainers(activeBigIdx).length + 1;
    const newContainer: TripContainer = {
      id: genId(),
      displayName: `容器 ${seq}`,
      subTripIndices: [],
    };
    setContainers(activeBigIdx, [...getContainers(activeBigIdx), newContainer]);
  };

  // 切换缩略图展开
  const toggleThumbs = (key: string) =>
    setThumbsOpen((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  // 验证能否前往归档
  const canProceed = archiveMode !== null &&
    (archiveMode !== "rebuild" || totalUnassigned() === 0);

  // ── 渲染 ───────────────────────────────────────────────────

  return (
    <div className="p-5 max-w-5xl mx-auto">
      {/* 页头 */}
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-slate-100">🔧 行程重建</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          将子行程分组到容器中，生成额外目录层级（可选）· 右侧选择归档模式后前往归档
        </p>
      </div>

      {/* 3:1 双栏主体 */}
      <div className="grid grid-cols-4 gap-4 items-start">

        {/* ── 左侧：行程树（3/4）─────────────────────────── */}
        <div className="col-span-3 space-y-3">
          {tripStructure.map((big, bi) => {
            const isCollapsed = collapsed.has(bi);
            const assignedMap = getAssignedMap(bi);

            return (
              <div
                key={bi}
                className={clsx(
                  "border rounded-xl overflow-hidden transition-colors",
                  bi === activeBigIdx
                    ? "border-blue-700/60"
                    : "border-slate-700/50"
                )}
              >
                {/* 大行程标题 */}
                <div
                  className={clsx(
                    "px-4 py-3 flex items-center justify-between cursor-pointer transition-colors",
                    bi === activeBigIdx ? "bg-slate-800" : "bg-slate-800/60 hover:bg-slate-800/80"
                  )}
                  onClick={() => {
                    setActiveBigIdx(bi);
                    setSelectedSubs([]);
                    setCollapsed((prev) => {
                      const next = new Set(prev);
                      next.has(bi) ? next.delete(bi) : next.add(bi);
                      return next;
                    });
                  }}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-slate-400 text-xs w-3">{isCollapsed ? "▶" : "▼"}</span>
                    <span className="text-lg flex-shrink-0">📁</span>
                    <span className="font-semibold text-blue-300 text-sm truncate">
                      {big.displayName || big.folder}
                    </span>
                    {bi === activeBigIdx && (
                      <span className="text-xs text-blue-500 bg-blue-900/30 px-1.5 py-0.5 rounded flex-shrink-0">
                        当前
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400 flex-shrink-0 ml-3">
                    {big.start_date && (
                      <span>{big.start_date.slice(0, 10)} → {big.end_date?.slice(0, 10)}</span>
                    )}
                    <span className="bg-slate-700 px-2 py-0.5 rounded-full">
                      {big.total_files} 个文件
                    </span>
                    {/* 未分配提示 */}
                    {unassignedCount(bi) < big.sub_trips.length && (
                      <span className="bg-emerald-900/40 text-emerald-400 px-2 py-0.5 rounded-full">
                        {big.sub_trips.length - unassignedCount(bi)}/{big.sub_trips.length} 已规划
                      </span>
                    )}
                  </div>
                </div>

                {/* 子行程列表 */}
                {!isCollapsed && (
                  <div className="divide-y divide-slate-700/30">
                    {big.sub_trips.map((sub, si) => {
                      const assignedContainer = assignedMap.get(si);
                      const isSelected = bi === activeBigIdx && selectedSubs.includes(si);
                      const thumbKey = `${bi}-${si}`;
                      const thumbOpen = thumbsOpen.has(thumbKey);

                      return (
                        <div
                          key={si}
                          className={clsx(
                            "transition-colors",
                            isSelected
                              ? "bg-blue-900/20"
                              : assignedContainer
                              ? "bg-emerald-900/10"
                              : "bg-slate-900/20 hover:bg-slate-900/40"
                          )}
                        >
                          <div className="px-4 py-2.5 flex items-center gap-2">
                            {/* 选择框或已分配标记 */}
                            <div className="flex-shrink-0 w-5">
                              {assignedContainer ? (
                                <span
                                  title={`已在容器「${assignedContainer}」中`}
                                  className="text-emerald-400 text-sm"
                                >
                                  ✅
                                </span>
                              ) : (
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => toggleSelect(bi, si)}
                                  onClick={(e) => e.stopPropagation()}
                                  className="accent-blue-500 w-3.5 h-3.5 cursor-pointer"
                                />
                              )}
                            </div>

                            {/* 子行程信息 */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-slate-600 text-xs font-mono w-4">
                                  {si + 1}
                                </span>
                                <span className="text-emerald-300 text-sm font-medium truncate max-w-[200px]">
                                  {sub.displayName || sub.folder}
                                </span>
                                {sub.location && (
                                  <span className="text-xs bg-slate-700/70 text-slate-300 px-1.5 py-0.5 rounded-full truncate max-w-[120px]">
                                    📍 {sub.location}
                                  </span>
                                )}
                                {assignedContainer && (
                                  <span className="text-xs text-emerald-400/70 bg-emerald-900/20 border border-emerald-700/30 px-1.5 py-0.5 rounded truncate max-w-[120px]">
                                    📦 {assignedContainer}
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* 右侧信息 + 缩略图按钮 */}
                            <div className="flex items-center gap-2 text-xs text-slate-400 flex-shrink-0">
                              {sub.start_date && (
                                <span>{sub.start_date.slice(5, 10)}</span>
                              )}
                              <span>{sub.file_count} 个</span>
                              {sub.files && sub.files.length > 0 && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleThumbs(thumbKey);
                                  }}
                                  className={clsx(
                                    "px-1.5 py-0.5 border rounded text-xs transition-colors",
                                    thumbOpen
                                      ? "bg-blue-900/40 border-blue-700/50 text-blue-400"
                                      : "bg-slate-700/50 border-slate-600 text-slate-500 hover:text-slate-300"
                                  )}
                                >
                                  🖼️
                                </button>
                              )}
                            </div>
                          </div>

                          {/* 缩略图 */}
                          {thumbOpen && sub.files && (
                            <div className="px-10 pb-2">
                              <MiniThumbs files={sub.files} />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          {/* 底部提示 */}
          <div className="text-xs text-slate-600 text-center py-2">
            💡 点击行程标题切换右侧管理对象；勾选子行程后在右侧「移入」操作
          </div>
        </div>

        {/* ── 右侧：容器管理（1/3，sticky）──────────────────── */}
        <div className="col-span-1 sticky top-4 space-y-3 max-h-[calc(100vh-7rem)] overflow-y-auto pr-1">

          {/* 归档模式选择 */}
          <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-4">
            <ModeSelector mode={archiveMode} onChange={setArchiveMode} />
          </div>

          {/* 容器管理面板 */}
          <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-4 space-y-3">

            {/* 面板标题 + 大行程切换 */}
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold text-slate-300">
                📦 容器管理
              </div>
              {/* 多大行程时显示切换器 */}
              {tripStructure.length > 1 && (
                <select
                  value={activeBigIdx}
                  onChange={(e) => {
                    setActiveBigIdx(Number(e.target.value));
                    setSelectedSubs([]);
                  }}
                  className="text-xs bg-slate-800 border border-slate-600 rounded px-1.5 py-0.5 text-slate-300 outline-none"
                >
                  {tripStructure.map((big, i) => (
                    <option key={i} value={i}>
                      {(big.displayName || big.folder).slice(0, 20)}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* 未分配警告 */}
            {archiveMode === "rebuild" && unassignedCount(activeBigIdx) > 0 && (
              <div className="text-xs text-amber-400 bg-amber-900/20 border border-amber-700/30 rounded-lg px-3 py-2">
                ⚠️ 还有 {unassignedCount(activeBigIdx)} 个子行程未分配（重建模式必须全部分配）
              </div>
            )}
            {archiveMode === "mixed" && unassignedCount(activeBigIdx) > 0 && (
              <div className="text-xs text-slate-400 bg-slate-800/50 border border-slate-700/30 rounded-lg px-3 py-2">
                ℹ️ {unassignedCount(activeBigIdx)} 个未分配子行程将按行程树原结构归档
              </div>
            )}

            {/* 已选中子行程 + 移入操作 */}
            {selectedSubs.length > 0 && (
              <div className="bg-blue-900/20 border border-blue-700/40 rounded-lg p-3 space-y-2">
                <div className="text-xs text-blue-300 font-medium">
                  已选 {selectedSubs.length} 个子行程
                </div>
                {/* 已选 chips */}
                <div className="flex flex-wrap gap-1">
                  {selectedSubs.map((si) => {
                    const sub = tripStructure[activeBigIdx].sub_trips[si];
                    return (
                      <span
                        key={si}
                        className="text-xs bg-blue-900/40 text-blue-300 border border-blue-700/40 px-2 py-0.5 rounded-full truncate max-w-[120px]"
                        title={sub.displayName || sub.folder}
                      >
                        {(sub.displayName || sub.folder).slice(0, 14)}…
                      </span>
                    );
                  })}
                </div>

                {/* 移入按钮 */}
                <div className="relative" ref={moveMenuRef}>
                  <button
                    onClick={() => setShowMoveMenu((v) => !v)}
                    className="w-full text-xs bg-blue-700 hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg transition-colors flex items-center justify-center gap-1"
                  >
                    移入容器 ▼
                  </button>
                  {showMoveMenu && (
                    <div className="absolute left-0 right-0 top-full mt-1 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-50 overflow-hidden">
                      {getContainers(activeBigIdx).map((c) => (
                        <button
                          key={c.id}
                          onClick={() => moveToContainer(c.id)}
                          className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition-colors truncate"
                        >
                          📦 {c.displayName}
                        </button>
                      ))}
                      <div className="border-t border-slate-700/50" />
                      <button
                        onClick={moveToNewContainer}
                        className="w-full text-left px-3 py-2 text-xs text-blue-400 hover:bg-slate-700 transition-colors"
                      >
                        + 移入新建容器
                      </button>
                      <button
                        onClick={() => setSelectedSubs([])}
                        className="w-full text-left px-3 py-2 text-xs text-slate-500 hover:bg-slate-700 transition-colors"
                      >
                        取消选择
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 容器列表 */}
            {getContainers(activeBigIdx).length === 0 ? (
              <div className="text-xs text-slate-600 text-center py-3 italic">
                暂无容器 — 勾选子行程后点「移入」创建
              </div>
            ) : (
              <div className="space-y-2">
                {getContainers(activeBigIdx).map((c, ci) => (
                  <div
                    key={c.id}
                    className="border border-slate-700/50 rounded-lg overflow-hidden"
                  >
                    {/* 容器标题 */}
                    <div className="bg-slate-800/80 px-3 py-2 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="text-xs text-slate-500 font-mono flex-shrink-0">
                          {ci + 1}
                        </span>
                        <InlineEdit
                          value={c.displayName}
                          onSave={(v) => renameContainer(activeBigIdx, c.id, v)}
                        />
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <span className="text-xs text-slate-500">
                          {c.subTripIndices.length}个
                        </span>
                        <button
                          onClick={() => deleteContainer(activeBigIdx, c.id)}
                          title="删除容器（子行程归还到未分配池）"
                          className="text-slate-600 hover:text-red-400 transition-colors text-xs px-1"
                        >
                          ×
                        </button>
                      </div>
                    </div>

                    {/* 容器内的子行程 */}
                    <div className="divide-y divide-slate-700/30">
                      {c.subTripIndices.map((si) => {
                        const sub = tripStructure[activeBigIdx].sub_trips[si];
                        if (!sub) return null;
                        return (
                          <div
                            key={si}
                            className="px-3 py-1.5 flex items-center justify-between bg-slate-900/30 gap-2"
                          >
                            <span
                              className="text-xs text-emerald-300/80 truncate"
                              title={sub.displayName || sub.folder}
                            >
                              {(sub.displayName || sub.folder).slice(0, 22)}
                              {(sub.displayName || sub.folder).length > 22 && "…"}
                            </span>
                            <button
                              onClick={() => removeFromContainer(activeBigIdx, c.id, si)}
                              title="移出容器"
                              className="text-xs text-slate-600 hover:text-amber-400 transition-colors flex-shrink-0"
                            >
                              ↩
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 新建空容器 */}
            <button
              onClick={addEmptyContainer}
              className="w-full text-xs text-slate-500 hover:text-slate-300 border border-slate-700/50 hover:border-slate-600 rounded-lg py-2 transition-colors"
            >
              + 新建空容器
            </button>

          </div>

          {/* 归档预览摘要 */}
          <div className="bg-slate-900/40 border border-slate-700/30 rounded-xl p-3 space-y-1.5 text-xs">
            <div className="text-slate-400 font-medium mb-1">归档预览</div>
            {tripStructure.map((big, bi) => {
              const containers = getContainers(bi);
              const unassigned = unassignedCount(bi);
              return (
                <div key={bi} className="text-slate-500 space-y-0.5">
                  <div className="text-slate-400 truncate" title={big.displayName || big.folder}>
                    📁 {(big.displayName || big.folder).slice(0, 22)}…
                  </div>
                  {containers.map((c) => (
                    <div key={c.id} className="pl-3">
                      📦 {c.displayName} ({c.subTripIndices.length}个子行程)
                    </div>
                  ))}
                  {unassigned > 0 && (
                    <div className={clsx("pl-3", archiveMode === "rebuild" ? "text-amber-500" : "text-slate-600")}>
                      {archiveMode === "rebuild" ? "⚠️" : "📂"} {unassigned}个按行程树
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* 导航按钮（上一步/下一步）*/}
          <div className="space-y-2 pb-2">
            <button
              onClick={() => setCurrentPage("archive")}
              disabled={!canProceed}
              title={
                archiveMode === null
                  ? "请先在上方选择归档模式"
                  : archiveMode === "rebuild" && totalUnassigned() > 0
                  ? `重建行程模式需所有子行程分配到容器（还有 ${totalUnassigned()} 个未分配）`
                  : "前往归档"
              }
              className={clsx(
                "w-full py-2.5 rounded-xl text-sm font-medium transition-all",
                canProceed
                  ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-500/20"
                  : "bg-slate-800 text-slate-500 cursor-not-allowed"
              )}
            >
              📦 下一步：归档 →
            </button>
            <button
              onClick={() => setCurrentPage("scan")}
              className="w-full py-2 rounded-xl text-xs text-slate-500 hover:text-slate-300 border border-slate-700/50 hover:border-slate-600 transition-colors"
            >
              ← 上一步：扫描
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}

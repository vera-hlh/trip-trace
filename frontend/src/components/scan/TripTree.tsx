import { useState } from "react";
import clsx from "clsx";
import type { BigTripData } from "@/store/appStore";
import { EditableLabel } from "./EditableLabel";
import { SubTripThumbnails } from "./SubTripThumbnails";

/** 扫描结果行程树：大行程 → 子行程 → 缩略图 */
export function TripTree({
  trips,
  onRenameBig,
  onRenameSub,
}: {
  trips: BigTripData[];
  onRenameBig: (bi: number, name: string) => void;
  onRenameSub: (bi: number, si: number, name: string) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
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
                        <div className="px-4 py-2.5 flex items-center justify-between hover:bg-slate-900/50 transition-colors">
                          <div className="flex items-center gap-2 min-w-0 overflow-hidden">
                            <span className="text-slate-600 text-xs w-5 text-right font-mono flex-shrink-0">
                              {si + 1}
                            </span>
                            <span className="flex-shrink-0">📂</span>
                            <div
                              className="max-w-[220px] overflow-hidden flex-shrink-0"
                              title={sub.displayName || sub.folder}
                            >
                              <EditableLabel
                                value={sub.displayName || sub.folder}
                                onSave={(name) => onRenameSub(bi, si, name)}
                                className="text-sm text-emerald-300 hover:text-emerald-200 font-medium truncate block max-w-full"
                              />
                            </div>
                            {sub.location && (
                              <span
                                title={sub.location}
                                className="text-xs bg-slate-700/80 text-slate-300 px-2 py-0.5 rounded-full flex-shrink-0 max-w-[130px] truncate"
                              >
                                📍 {sub.location}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2 text-xs text-slate-400 flex-shrink-0 ml-4">
                            {sub.start_date && (
                              <span>
                                {sub.start_date.slice(5, 10)} →{" "}
                                {sub.end_date?.slice(5, 10)}
                              </span>
                            )}
                            <span>{sub.file_count} 个文件</span>

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
                          </div>
                        </div>

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

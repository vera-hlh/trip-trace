import { useState } from "react";
import { backendUrl } from "@/api/backend";

const THUMB_PAGE = 12;

/** 子行程文件缩略图面板 */
export function SubTripThumbnails({ files }: { files: Array<{ name: string; path: string }> }) {
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
                src={backendUrl(`/api/media/thumbnail?path=${encodeURIComponent(file.path)}&width=120&quality=75`)}
                alt={file.name}
                loading="lazy"
                className="w-full h-full object-cover"
                onError={(e) => {
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

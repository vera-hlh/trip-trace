/**
 * PlaceholderPage.tsx
 * 占位页面，用于 Week 8-9 尚未开发的页面
 * （Week 7 ScanPage 已实现，移至 ScanPage.tsx）
 */
import { useAppStore, AppPage } from "@/store/appStore";
import clsx from "clsx";

interface PlaceholderPageProps {
  icon: string;
  title: string;
  week: string;
  desc: string;
  prevPage?: { id: AppPage; label: string };
}

export function PlaceholderPage({ icon, title, week, desc, prevPage }: PlaceholderPageProps) {
  const { setCurrentPage } = useAppStore();

  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <div className="text-6xl mb-4 opacity-40">{icon}</div>
      <h1 className="text-xl font-bold text-slate-300 mb-1">{title}</h1>
      <span className="text-xs px-3 py-1 bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-full mb-3">
        开发中 · {week}
      </span>
      <p className="text-sm text-slate-500 max-w-sm leading-relaxed mb-8">{desc}</p>

      {prevPage && (
        <button
          onClick={() => setCurrentPage(prevPage.id)}
          className={clsx(
            "px-6 py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700",
            "rounded-xl text-sm text-slate-300 transition-colors"
          )}
        >
          ← 返回{prevPage.label}
        </button>
      )}
    </div>
  );
}

// ── 各页占位组件 ─────────────────────────────────────────────

export function ArchivePage() {
  return (
    <PlaceholderPage
      icon="📦"
      title="归档预览 & 执行"
      week="Week 8"
      desc="归档预览确认界面、参数配置面板（时间阈值/备注模板）、执行归档（复制模式）+ 进度显示。"
      prevPage={{ id: "scan", label: "扫描" }}
    />
  );
}

export function MapPage() {
  return (
    <PlaceholderPage
      icon="🗺️"
      title="行程地图"
      week="Week 9"
      desc="Folium HTML 地图内嵌（路径 + 热点）、热点点击查看该地照片。"
      prevPage={{ id: "archive", label: "归档" }}
    />
  );
}

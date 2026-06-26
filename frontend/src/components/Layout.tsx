/**
 * Layout.tsx
 * 主界面布局：左侧侧边栏导航 + 右侧内容区
 */
import { ReactNode } from "react";
import { useAppStore, AppPage } from "@/store/appStore";
import clsx from "clsx";

// ── 导航项配置 ───────────────────────────────────────────────
interface NavItem {
  id: AppPage;
  label: string;
  icon: string;
  /** true = 下方分隔线 */
  dividerAfter?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { id: "home",         label: "主页",       icon: "🏠" },
  { id: "folder-setup", label: "选择文件夹", icon: "📁" },
  { id: "scan",         label: "扫描",       icon: "🔍" },
  { id: "rebuilder",    label: "行程重建",   icon: "🔧" },
  { id: "archive",      label: "归档",       icon: "📦" },
  { id: "map",          label: "地图",       icon: "🗺️", dividerAfter: true },
  { id: "history",      label: "操作记录",   icon: "📋" },
  { id: "test",         label: "测试控制台", icon: "🧪" },
];

// ── 侧边栏 ───────────────────────────────────────────────────
function Sidebar() {
  const { currentPage, setCurrentPage, backendReady } = useAppStore();

  return (
    <aside className="w-52 flex-shrink-0 bg-slate-900 border-r border-slate-700/60 flex flex-col h-full">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-slate-700/60">
        <div className="text-base font-bold text-white leading-tight">旅迹</div>
        <div className="text-xs text-slate-400 tracking-widest mt-0.5">TripTrace</div>
      </div>

      {/* 导航列表 */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <div key={item.id}>
            <button
              onClick={() => setCurrentPage(item.id)}
              className={clsx(
                "w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors",
                currentPage === item.id
                  ? "bg-blue-600/20 text-blue-400 font-medium border-r-2 border-blue-500"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              )}
            >
              <span className="text-base w-5 text-center flex-shrink-0">{item.icon}</span>
              <span>{item.label}</span>
            </button>
            {item.dividerAfter && (
              <div className="mx-4 my-2 border-t border-slate-700/50" />
            )}
          </div>
        ))}
      </nav>

      {/* 底部：后端状态指示 */}
      <div className="px-4 py-3 border-t border-slate-700/60">
        <div className="flex items-center gap-2 text-xs">
          <span
            className={clsx(
              "w-2 h-2 rounded-full flex-shrink-0",
              backendReady ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]" : "bg-red-500"
            )}
          />
          <span className={backendReady ? "text-emerald-400" : "text-red-400"}>
            {backendReady ? "后端已连接" : "后端未连接"}
          </span>
        </div>
        <div className="text-xs text-slate-600 mt-1">v0.8.0 · Phase 4</div>
      </div>
    </aside>
  );
}

// ── 主布局 ───────────────────────────────────────────────────
interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

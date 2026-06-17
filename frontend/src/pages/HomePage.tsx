/**
 * HomePage.tsx
 * 主页：欢迎界面 + 快速入口 + 后端状态
 */
import { useEffect, useCallback } from "react";
import { useAppStore } from "@/store/appStore";
import clsx from "clsx";

const BACKEND_URL = "http://localhost:17890";

// ── 状态卡片 ─────────────────────────────────────────────────
interface StatCardProps {
  icon: string;
  label: string;
  value: string | number;
  color?: "blue" | "emerald" | "purple" | "amber";
}

function StatCard({ icon, label, value, color = "blue" }: StatCardProps) {
  const colorMap = {
    blue:    "text-blue-400",
    emerald: "text-emerald-400",
    purple:  "text-purple-400",
    amber:   "text-amber-400",
  };
  return (
    <div className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-4 flex flex-col gap-1">
      <div className="text-xl">{icon}</div>
      <div className={clsx("text-2xl font-bold font-mono", colorMap[color])}>{value}</div>
      <div className="text-xs text-slate-400">{label}</div>
    </div>
  );
}

// ── 快速入口卡片 ─────────────────────────────────────────────
interface QuickCardProps {
  icon: string;
  title: string;
  desc: string;
  onClick: () => void;
  disabled?: boolean;
  badge?: string;
}

function QuickCard({ icon, title, desc, onClick, disabled, badge }: QuickCardProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "text-left p-5 rounded-2xl border transition-all group",
        disabled
          ? "bg-slate-800/30 border-slate-700/30 opacity-40 cursor-not-allowed"
          : "bg-slate-800/60 border-slate-700/50 hover:border-blue-500/50 hover:bg-slate-800 cursor-pointer"
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <span className="text-2xl">{icon}</span>
        {badge && (
          <span className="text-xs px-2 py-0.5 bg-blue-600/30 text-blue-400 rounded-full border border-blue-500/30">
            {badge}
          </span>
        )}
      </div>
      <div className="font-medium text-slate-200 text-sm group-hover:text-white transition-colors">
        {title}
      </div>
      <div className="text-xs text-slate-500 mt-0.5 leading-relaxed">{desc}</div>
    </button>
  );
}

// ── 主页面 ───────────────────────────────────────────────────
export default function HomePage() {
  const {
    backendReady,
    setBackendReady,
    setCurrentPage,
    sourceFolderPath,
    outputFolderPath,
  } = useAppStore();

  // 检查后端连接
  const checkBackend = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(3000) });
      const ok = res.ok;
      setBackendReady(ok);
    } catch {
      setBackendReady(false);
    }
  }, [setBackendReady]);

  // 挂载时检查，之后每 10s 轮询一次
  useEffect(() => {
    checkBackend();
    const timer = setInterval(checkBackend, 10_000);
    return () => clearInterval(timer);
  }, [checkBackend]);

  const hasConfig = Boolean(sourceFolderPath && outputFolderPath);

  return (
    <div className="p-8 max-w-3xl mx-auto">
      {/* 页头 */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-slate-100 tracking-tight">旅迹 · TripTrace</h1>
        <p className="text-slate-400 mt-2 text-sm leading-relaxed">
          旅行照片 / 视频智能归档工具 · 按行程自动整理，保留美好记忆
        </p>
      </div>

      {/* 后端状态横幅 */}
      <div
        className={clsx(
          "mb-8 p-4 rounded-xl border flex items-center gap-3 text-sm",
          backendReady
            ? "bg-emerald-900/20 border-emerald-700/40 text-emerald-300"
            : "bg-red-900/20 border-red-700/40 text-red-300"
        )}
      >
        <span
          className={clsx(
            "w-2.5 h-2.5 rounded-full flex-shrink-0 animate-pulse",
            backendReady ? "bg-emerald-400" : "bg-red-500"
          )}
        />
        <span className="flex-1">
          {backendReady
            ? "✅ 后端服务已连接（localhost:17890）"
            : "❌ 后端服务未连接 · 请启动 Python 后端：cd backend && .venv\\Scripts\\python.exe uvicorn_config.py"}
        </span>
        <button
          onClick={checkBackend}
          className="text-xs opacity-60 hover:opacity-100 transition-opacity underline"
        >
          重新检测
        </button>
      </div>

      {/* 快速入口 */}
      <div className="mb-8">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          快速开始
        </h2>
        <div className="grid grid-cols-2 gap-4">
          <QuickCard
            icon="📁"
            title="选择文件夹"
            desc="设置照片源目录和归档输出目录"
            onClick={() => setCurrentPage("folder-setup")}
            badge={hasConfig ? "已配置" : "必须"}
          />
          <QuickCard
            icon="🔍"
            title="扫描文件夹"
            desc="读取照片元数据、GPS 信息，识别行程"
            onClick={() => setCurrentPage("scan")}
            disabled={!hasConfig || !backendReady}
          />
          <QuickCard
            icon="📦"
            title="归档预览"
            desc="查看行程切分结果，确认后执行归档"
            onClick={() => setCurrentPage("archive")}
            disabled={!hasConfig || !backendReady}
          />
          <QuickCard
            icon="🗺️"
            title="行程地图"
            desc="在地图上可视化旅行轨迹与热点"
            onClick={() => setCurrentPage("map")}
            disabled={!backendReady}
          />
        </div>
      </div>

      {/* 工作流程提示 */}
      {!hasConfig && (
        <div className="p-4 bg-blue-900/20 border border-blue-700/40 rounded-xl text-sm text-blue-300">
          <span className="font-medium">🚀 开始使用：</span>
          先点击「选择文件夹」配置源目录和输出目录，然后进行扫描和归档。
        </div>
      )}

      {/* 开发工具 */}
      <div className="mt-8 pt-6 border-t border-slate-700/40">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          开发工具
        </h2>
        <button
          onClick={() => setCurrentPage("test")}
          className="w-full text-left p-4 rounded-xl bg-slate-800/40 border border-slate-700/40 hover:border-slate-600 transition-colors"
        >
          <span className="text-sm text-slate-400">🧪 后端 API 测试控制台</span>
          <span className="text-xs text-slate-600 ml-2">Phase 2 验证工具</span>
        </button>
      </div>
    </div>
  );
}

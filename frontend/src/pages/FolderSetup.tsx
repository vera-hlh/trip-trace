/**
 * FolderSetup.tsx
 * 文件夹选择页面
 * - 源文件夹（照片/视频所在目录）
 * - 输出目录（归档后存放位置）
 * - 调用 Electron IPC 打开系统文件夹对话框
 */
import { useState } from "react";
import { useAppStore } from "@/store/appStore";
import clsx from "clsx";

// ── 工具函数 ─────────────────────────────────────────────────

/** 判断是否为有效绝对路径（Windows 或 Unix） */
function isAbsolutePath(p: string): boolean {
  if (!p || p.trim() === "") return false;
  if (/^[a-zA-Z]:[\\\/]/.test(p)) return true;
  if (p.startsWith("/")) return true;
  return false;
}

/**
 * 调用 Electron / 浏览器文件夹选择器
 * 返回 { path, isFullPath } 或 null（用户取消）
 */
async function pickFolder(
  type: "source" | "save"
): Promise<{ path: string; isFullPath: boolean } | null> {
  const electronAPI = (window as any).electronAPI;
  if (electronAPI) {
    try {
      const path: string | null =
        type === "save"
          ? await electronAPI.openSaveDialog()
          : await electronAPI.openFolderDialog();
      if (path) return { path, isFullPath: true };
      return null; // 用户取消
    } catch (e) {
      console.warn("Electron 对话框失败:", e);
    }
  }

  // 浏览器降级：showDirectoryPicker（仅能获取文件夹名，无完整路径）
  if ("showDirectoryPicker" in window) {
    try {
      const handle = await (window as any).showDirectoryPicker({ mode: "read" });
      return { path: handle.name, isFullPath: false };
    } catch (e: any) {
      if (e?.name !== "AbortError") console.warn("showDirectoryPicker 失败:", e);
    }
  }
  return null;
}

// ── 单行路径输入组件 ─────────────────────────────────────────
interface PathInputProps {
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
  onPick: () => void;
  valid: boolean | null; // null=未填写, true=有效, false=无效
  icon: string;
}

function PathInput({ label, hint, value, onChange, onPick, valid, icon }: PathInputProps) {
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm font-medium text-slate-300">
        <span>{icon}</span>
        {label}
      </label>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={hint}
          className={clsx(
            "flex-1 bg-slate-800 border rounded-lg px-4 py-3 text-sm text-slate-200 placeholder-slate-500",
            "focus:outline-none focus:ring-2 transition-all",
            valid === false
              ? "border-red-500/60 focus:ring-red-500/30"
              : valid === true
              ? "border-emerald-500/60 focus:ring-emerald-500/30"
              : "border-slate-600 focus:ring-blue-500/30 focus:border-blue-500/60"
          )}
          spellCheck={false}
        />
        <button
          onClick={onPick}
          title="浏览文件夹"
          className="px-4 py-3 bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg text-base transition-colors flex-shrink-0"
        >
          📂
        </button>
      </div>
      {valid === false && value.trim() !== "" && (
        <p className="text-xs text-red-400">请输入有效的绝对路径（如 C:\Users\...\Photos）</p>
      )}
    </div>
  );
}

// ── 主页面 ───────────────────────────────────────────────────
export default function FolderSetup() {
  const {
    sourceFolderPath,
    outputFolderPath,
    setSourceFolderPath,
    setOutputFolderPath,
    setCurrentPage,
  } = useAppStore();

  const [pickerNote, setPickerNote] = useState<string>("");
  const [saved, setSaved] = useState(false);

  // 是否有效
  const sourceValid = sourceFolderPath.trim() === "" ? null : isAbsolutePath(sourceFolderPath);
  const outputValid = outputFolderPath.trim() === "" ? null : isAbsolutePath(outputFolderPath);

  const canProceed =
    isAbsolutePath(sourceFolderPath) && isAbsolutePath(outputFolderPath);

  // ── 处理文件夹选择 ─────────────────────────────────────────
  const handlePickSource = async () => {
    setPickerNote("");
    const result = await pickFolder("source");
    if (!result) return;
    if (result.isFullPath) {
      setSourceFolderPath(result.path);
    } else {
      setPickerNote(
        `📂 浏览器模式仅能获取文件夹名"${result.path}"，请手动填写完整路径（如 C:\\Users\\...\\${result.path}）`
      );
    }
  };

  const handlePickOutput = async () => {
    setPickerNote("");
    const result = await pickFolder("save");
    if (!result) return;
    if (result.isFullPath) {
      setOutputFolderPath(result.path);
    } else {
      setPickerNote(
        `📂 浏览器模式仅能获取文件夹名"${result.path}"，请手动填写完整路径`
      );
    }
  };

  // ── 保存并跳转 ─────────────────────────────────────────────
  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const handleGoScan = () => {
    setCurrentPage("scan");
  };

  return (
    <div className="p-8 max-w-2xl mx-auto">
      {/* 页头 */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-100">📁 选择文件夹</h1>
        <p className="text-slate-400 mt-1 text-sm">
          设置照片/视频源目录和归档输出目录，路径会自动保存。
        </p>
      </div>

      {/* 表单卡片 */}
      <div className="bg-slate-900/60 border border-slate-700/60 rounded-2xl p-6 space-y-6">
        <PathInput
          icon="📷"
          label="照片 / 视频源文件夹"
          hint="C:\Users\...\旅行照片"
          value={sourceFolderPath}
          onChange={(v) => { setSourceFolderPath(v); setPickerNote(""); }}
          onPick={handlePickSource}
          valid={sourceValid}
        />

        <PathInput
          icon="📦"
          label="归档输出目录"
          hint="C:\Users\...\照片归档"
          value={outputFolderPath}
          onChange={(v) => { setOutputFolderPath(v); setPickerNote(""); }}
          onPick={handlePickOutput}
          valid={outputValid}
        />

        {/* 浏览器模式提示 */}
        {pickerNote && (
          <div className="p-3 bg-amber-900/30 border border-amber-700/60 rounded-lg text-xs text-amber-300 leading-relaxed">
            {pickerNote}
          </div>
        )}

        {/* 说明 */}
        <div className="p-4 bg-slate-800/60 rounded-xl text-xs text-slate-400 space-y-1.5 leading-relaxed">
          <div>
            <span className="text-slate-300 font-medium">源文件夹：</span>
            存放原始照片/视频的目录（支持子文件夹递归扫描）
          </div>
          <div>
            <span className="text-slate-300 font-medium">输出目录：</span>
            归档后文件将复制到此处，原文件不会被删除（默认复制模式）
          </div>
          <div>
            <span className="text-slate-300 font-medium">注意：</span>
            归档预览为虚拟操作，<span className="text-emerald-400 font-medium">不会</span>
            创建文件夹或复制文件，确认后才执行
          </div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="mt-6 flex gap-3">
        <button
          onClick={handleSave}
          disabled={!canProceed}
          className={clsx(
            "flex-1 py-3 rounded-xl font-medium text-sm transition-all",
            saved
              ? "bg-emerald-600 text-white"
              : canProceed
              ? "bg-slate-700 hover:bg-slate-600 text-slate-200"
              : "bg-slate-800 text-slate-500 cursor-not-allowed"
          )}
        >
          {saved ? "✅ 已保存" : "💾 保存配置"}
        </button>

        <button
          onClick={handleGoScan}
          disabled={!canProceed}
          className={clsx(
            "flex-1 py-3 rounded-xl font-medium text-sm transition-all",
            canProceed
              ? "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20"
              : "bg-slate-800 text-slate-500 cursor-not-allowed"
          )}
        >
          🔍 下一步：扫描文件夹 →
        </button>
      </div>

      {!canProceed && (sourceFolderPath || outputFolderPath) && (
        <p className="text-xs text-slate-500 mt-3 text-center">
          请确保两个路径均为有效的绝对路径后继续
        </p>
      )}
    </div>
  );
}

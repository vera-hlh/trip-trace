/**
 * TripTrace 后端 API 测试控制台
 *
 * 功能：
 * - 扫描文件夹（SSE 实时进度）
 * - 查看扫描状态统计
 * - 归档预览（行程切分结果 + 文件列表）
 * - 完整 JSON 调试输出
 * - 详细参数配置
 */
import { useState, useRef } from "react";

const API = "http://localhost:17890";

// ============================================================
// 类型定义
// ============================================================

interface ScanEvent {
  type: string;
  current?: number;
  total?: number;
  total_files?: number;  // complete 事件中的总文件数
  file?: string;
  file_type?: string;
  has_gps?: boolean;
  datetime?: string;
  error?: string | null;
  message?: string;
  with_gps?: number;
  without_gps?: number;
  errors?: number;
  new_files?: number;
  skipped?: number;
}

interface SubTripInfo {
  folder: string;
  location: string;
  start_date: string | null;
  end_date: string | null;
  file_count: number;
}

interface BigTripInfo {
  folder: string;
  start_date: string | null;
  end_date: string | null;
  total_files: number;
  sub_trips: SubTripInfo[];
}

interface ArchivePreviewData {
  trips_structure: BigTripInfo[];
  summary: {
    total_files: number;
    big_trips_created: number;
    sub_trips_created: number;
    files_without_gps: number;
    files_needing_review: number;
    message?: string;
  };
  preview: Array<{
    original_path: string;
    target_path: string;
    big_trip_folder: string;
    sub_trip_folder: string;
    file_name: string;
  }>;
}

// ============================================================
// 主组件
// ============================================================

// ============================================================
// 文件夹选择器辅助函数
// ============================================================

/** 判断路径是否是绝对路径（Windows 或 Unix 格式）*/
function isAbsolutePath(p: string): boolean {
  if (!p || p.trim() === "") return false;
  // Windows: C:\ D:\ 等
  if (/^[a-zA-Z]:[\\\/]/.test(p)) return true;
  // Unix/Mac: /Users/ /home/ 等
  if (p.startsWith("/")) return true;
  return false;
}

/**
 * 打开系统原生文件夹选择窗口
 *
 * 返回值说明：
 *  - { path: string, isFullPath: true }  → Electron 模式，完整绝对路径，可直接使用
 *  - { path: string, isFullPath: false } → 浏览器模式，仅文件夹名，需用户手动补全
 *  - null → 用户取消 或 环境不支持
 */
async function openFolderPicker(): Promise<{ path: string; isFullPath: boolean } | null> {
  // 方式 1：Electron IPC（仅在 Electron 容器内有效，返回完整路径）
  const electronAPI = (window as any).electronAPI;
  if (electronAPI?.openFolderDialog) {
    try {
      const path: string | null = await electronAPI.openFolderDialog();
      if (path) return { path, isFullPath: true };
    } catch (e) {
      console.warn("Electron 文件夹对话框失败:", e);
    }
  }

  // 方式 2：Web File System Access API
  // ⚠️ 浏览器安全限制：此 API 只能获取文件夹名称，无法获取完整绝对路径
  // 完整路径只有在 Electron 模式下才能获取
  if ("showDirectoryPicker" in window) {
    try {
      const handle = await (window as any).showDirectoryPicker({ mode: "read" });
      return { path: handle.name, isFullPath: false };
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        console.warn("showDirectoryPicker 失败:", e);
      }
      return null; // 用户取消
    }
  }

  return null; // 环境不支持
}

/**
 * 根据已有路径推断父目录，拼接新的文件夹名称
 * 例：当前路径 "C:\Users\Eva\Pictures\旧文件夹"，新选择文件夹名 "新文件夹"
 *     → 推断为 "C:\Users\Eva\Pictures\新文件夹"
 */
function inferFullPath(existingPath: string, folderName: string): string {
  if (!existingPath || !isAbsolutePath(existingPath)) {
    return folderName;
  }
  const sep = existingPath.includes("\\") ? "\\" : "/";
  const parts = existingPath.split(sep).filter(Boolean);
  const parentParts = parts.slice(0, -1);
  const parent = parentParts.join(sep);
  const prefix = parent.length <= 2 ? parent + sep : parent;
  return prefix + sep + folderName;
}

export default function TestConsole() {
  // 参数状态
  const [folderPath, setFolderPath] = useState(
    "C:\\Users\\Microsoft\\Pictures\\20230712 照片整理"
  );
  const [outputPath, setOutputPath] = useState(
    "C:\\Users\\Microsoft\\Pictures\\归档测试"
  );
  const [bigTripDays, setBigTripDays] = useState(30);
  const [smallTripHours, setSmallTripHours] = useState(2.0);
  const [clearBeforeScan, setClearBeforeScan] = useState(false);
  const [pickerNote, setPickerNote] = useState<string>("");

  // 运行状态
  const [scanning, setScanning] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [geocoding, setGeocoding] = useState(false);

  // 展开的子行程（存 folder 名称）
  const [expandedTrips, setExpandedTrips] = useState<Set<string>>(new Set());
  const toggleTrip = (folder: string) => {
    setExpandedTrips(prev => {
      const next = new Set(prev);
      next.has(folder) ? next.delete(folder) : next.add(folder);
      return next;
    });
  };

  // 选择源文件夹
  const handleSelectFolder = async () => {
    const result = await openFolderPicker();
    if (result === null) return;

    const { path, isFullPath } = result;

    if (isFullPath) {
      // Electron 模式：完整路径，直接使用
      setFolderPath(path);
      setPickerNote("");
    } else {
      // 浏览器模式：只能获取文件夹名，自动推断完整路径
      const guessed = inferFullPath(folderPath, path);
      if (isAbsolutePath(guessed)) {
        // 推断成功，直接填入并提示
        setFolderPath(guessed);
        setPickerNote(
          `📂 已根据当前路径推断为"${guessed}"，如不正确请手动修改`
        );
      } else {
        // 无法推断，让用户补全
        setPickerNote(
          `📂 选中了文件夹"${path}"。请在上方输入框中输入完整路径（如 C:\\Users\\...\\${path}）`
        );
      }
    }
  };

  // 选择输出目录
  const handleSelectOutput = async () => {
    const result = await openFolderPicker();
    if (result === null) return;

    const { path, isFullPath } = result;

    if (isFullPath) {
      setOutputPath(path);
      setPickerNote("");
    } else {
      const guessed = inferFullPath(outputPath, path);
      if (isAbsolutePath(guessed)) {
        setOutputPath(guessed);
        setPickerNote(
          `📂 已根据当前路径推断为"${guessed}"，如不正确请手动修改`
        );
      } else {
        setPickerNote(
          `📂 选中了文件夹"${path}"。请输入完整路径（如 C:\\Users\\...\\${path}）`
        );
      }
    }
  };

  // 结果状态
  const [scanEvents, setScanEvents] = useState<ScanEvent[]>([]);
  const [scanStatus, setScanStatus] = useState<object | null>(null);
  const [previewData, setPreviewData] = useState<ArchivePreviewData | null>(null);
  const [previewRaw, setPreviewRaw] = useState<string>("");
  const [debugLog, setDebugLog] = useState<string[]>([]);

  const eventsEndRef = useRef<HTMLDivElement>(null);

  const addLog = (msg: string) => {
    const ts = new Date().toLocaleTimeString();
    setDebugLog((prev) => [`[${ts}] ${msg}`, ...prev.slice(0, 200)]);
  };

  // ============================================================
  // 扫描操作
  // ============================================================

  const handleScan = async () => {
    if (!folderPath) return;

    // 验证：必须是绝对路径，防止使用浏览器文件夹选择器返回的不完整路径
    if (!isAbsolutePath(folderPath)) {
      setPickerNote(
        `❌ 路径"${folderPath}"不是有效的绝对路径。请输入完整路径（如 C:\\Users\\Eva\\Pictures\\云南旅行）`
      );
      addLog(`❌ 扫描终止：路径不是绝对路径 → "${folderPath}"`);
      return;
    }

    setScanning(true);
    setScanEvents([]);
    addLog(`开始扫描: ${folderPath}`);

    // 可选：先清空已有扫描数据
    if (clearBeforeScan) {
      try {
        await fetch(`${API}/api/scan/clear`, { method: "DELETE" });
        addLog("已清空旧扫描数据");
      } catch (e) {
        addLog(`清空失败: ${e}`);
      }
    }

    try {
      const response = await fetch(`${API}/api/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_path: folderPath, options: {} }),
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
              const event: ScanEvent = JSON.parse(line.slice(6));
              setScanEvents((prev) => [...prev.slice(-500), event]); // 最多保留 500 条

              if (event.type === "complete") {
                addLog(
                  `扫描完成: ${event.total_files || 0} 个文件，${event.with_gps} 有GPS，${event.without_gps} 无GPS，${event.errors} 错误`
                );
              } else if (event.type === "error") {
                addLog(`扫描错误: ${event.file} - ${event.message}`);
              }
            } catch {}
          }
        }
      }
    } catch (e) {
      addLog(`扫描失败: ${e}`);
    } finally {
      setScanning(false);
      // 扫描完成后自动刷新状态
      await fetchScanStatus();
    }
  };

  // ============================================================
  // 扫描状态
  // ============================================================

  const fetchScanStatus = async () => {
    try {
      // 获取整体数据库状态
      const res = await fetch(`${API}/api/scan/status`);
      const data = await res.json();
      setScanStatus(data);

      // 同时统计当前文件夹在数据库中的记录数
      if (folderPath && isAbsolutePath(folderPath)) {
        try {
          const previewRes = await fetch(`${API}/api/archive/preview`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              folder_path: folderPath,
              output_path: folderPath + "_归档",
              options: { big_trip_threshold_days: 999, small_trip_threshold_hours: 0.01 },
            }),
          });
          if (previewRes.ok) {
            const previewData = await previewRes.json();
            const folderCount = previewData?.data?.summary?.total_files ?? 0;
            const folderGps = previewData?.data?.summary?.files_without_gps !== undefined
              ? folderCount - previewData.data.summary.files_without_gps
              : "?";
            addLog(
              `状态(DB全部): 共 ${data.total_files} 个文件 | ` +
              `当前文件夹已扫描: ${folderCount} 个文件（${folderGps} 有GPS）`
            );
          } else {
            addLog(`状态: DB共 ${data.total_files} 个文件，${data.with_gps} 有GPS，${data.photos} 照片，${data.videos} 视频`);
          }
        } catch {
          addLog(`状态: DB共 ${data.total_files} 个文件，${data.with_gps} 有GPS，${data.photos} 照片，${data.videos} 视频`);
        }
      } else {
        addLog(`状态: DB共 ${data.total_files} 个文件，${data.with_gps} 有GPS，${data.photos} 照片，${data.videos} 视频`);
      }
    } catch (e) {
      addLog(`获取状态失败: ${e}`);
    }
  };

  // ============================================================
  // 归档预览
  // ============================================================

  const handlePreview = async () => {
    if (!folderPath || !outputPath) return;
    setPreviewing(true);
    setPreviewData(null);
    addLog(`生成归档预览: ${folderPath} → ${outputPath}`);
    addLog(`参数: 大行程阈值=${bigTripDays}天，小行程阈值=${smallTripHours}小时`);

    try {
      const res = await fetch(`${API}/api/archive/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: folderPath,
          output_path: outputPath,
          options: {
            big_trip_threshold_days: bigTripDays,
            small_trip_threshold_hours: smallTripHours,
          },
        }),
      });

      const json = await res.json();
      setPreviewRaw(JSON.stringify(json, null, 2));

      if (json.success && json.data) {
        setPreviewData(json.data);
        const s = json.data.summary;
        addLog(
          `预览完成: ${s.total_files} 个文件 → ${s.big_trips_created} 大行程，${s.sub_trips_created} 子行程`
        );
        if (s.message) addLog(`提示: ${s.message}`);
      } else {
        addLog(`预览失败: ${JSON.stringify(json)}`);
      }
    } catch (e) {
      addLog(`预览请求失败: ${e}`);
    } finally {
      setPreviewing(false);
    }
  };

  // ============================================================
  // 逆地理编码
  // ============================================================

  const handleGeocode = async () => {
    setGeocoding(true);
    addLog("开始逆地理编码（将 GPS 坐标转为城市名）...");
    try {
      const res = await fetch(`${API}/api/scan/geocode`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        addLog(`地理编码完成: 更新 ${data.updated} 个文件（共处理 ${data.total_processed} 个）`);
      } else {
        addLog(`地理编码失败: ${JSON.stringify(data)}`);
      }
    } catch (e) {
      addLog(`地理编码请求失败: ${e}`);
    } finally {
      setGeocoding(false);
    }
  };

  // ============================================================
  // 渲染
  // ============================================================

  const completedEvent = scanEvents.find((e) => e.type === "complete");
  const progressEvents = scanEvents.filter((e) => e.type === "progress");
  const errorEvents = scanEvents.filter((e) => e.type === "error");
  const lastProgress = progressEvents[progressEvents.length - 1];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4">
      <div className="max-w-7xl mx-auto">
        {/* 标题 */}
        <div className="mb-6 border-b border-gray-700 pb-4">
          <h1 className="text-2xl font-bold text-blue-400">
            🧪 TripTrace 后端 API 测试控制台
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            后端地址: {API} &nbsp;|&nbsp; Phase 2 验证工具
          </p>
        </div>

        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：参数配置 + 操作按钮 */}
          <div className="col-span-4 space-y-4">
            {/* 参数配置 */}
            <div className="bg-gray-800 rounded-lg p-4 space-y-3">
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
                📁 文件夹配置
              </h2>

              {/* 照片源文件夹 */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  照片源文件夹路径
                </label>
                <div className="flex gap-1.5">
                  <input
                    type="text"
                    value={folderPath}
                    onChange={(e) => { setFolderPath(e.target.value); setPickerNote(""); }}
                    className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500 min-w-0"
                    placeholder="C:\Users\...\Photos"
                  />
                  <button
                    onClick={handleSelectFolder}
                    title="选择文件夹"
                    className="px-3 py-2 bg-gray-700 hover:bg-blue-600 border border-gray-600 hover:border-blue-500 rounded text-sm transition flex-shrink-0"
                  >
                    📂
                  </button>
                </div>
              </div>

              {/* 归档输出目录 */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  归档输出目录
                </label>
                <div className="flex gap-1.5">
                  <input
                    type="text"
                    value={outputPath}
                    onChange={(e) => { setOutputPath(e.target.value); setPickerNote(""); }}
                    className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500 min-w-0"
                    placeholder="C:\Users\...\归档"
                  />
                  <button
                    onClick={handleSelectOutput}
                    title="选择文件夹"
                    className="px-3 py-2 bg-gray-700 hover:bg-blue-600 border border-gray-600 hover:border-blue-500 rounded text-sm transition flex-shrink-0"
                  >
                    📂
                  </button>
                </div>
              </div>

              {/* 文件夹选择提示（浏览器模式无法获取完整路径时显示） */}
              {pickerNote && (
                <div className="p-2.5 bg-amber-900/30 border border-amber-700 rounded text-xs text-amber-300 leading-relaxed">
                  {pickerNote}
                </div>
              )}

              {/* 浏览器模式操作说明 */}
              <div className="text-xs text-gray-500 leading-relaxed space-y-1 pt-1 border-t border-gray-700">
                <div>💡 <span className="text-gray-400">📂 按钮</span>：浏览器模式下只能推断父目录，若路径有误请直接在输入框手动修改</div>
                <div>🔒 <span className="text-gray-400">归档预览</span>：纯虚拟操作，<strong className="text-emerald-400">不会</strong>创建文件夹或复制文件</div>
              </div>
            </div>

            {/* 归档算法参数 */}
            <div className="bg-gray-800 rounded-lg p-4 space-y-3">
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
                ⚙️ 归档算法参数
              </h2>

              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  大行程时间阈值（天）: <span className="text-blue-400 font-bold">{bigTripDays}</span>
                </label>
                <input
                  type="range"
                  min={7}
                  max={90}
                  value={bigTripDays}
                  onChange={(e) => setBigTripDays(Number(e.target.value))}
                  className="w-full accent-blue-500"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>7天</span><span>90天</span>
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  小行程时间阈值（小时）: <span className="text-blue-400 font-bold">{smallTripHours}</span>
                </label>
                <input
                  type="range"
                  min={0.5}
                  max={12}
                  step={0.5}
                  value={smallTripHours}
                  onChange={(e) => setSmallTripHours(Number(e.target.value))}
                  className="w-full accent-blue-500"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>0.5h</span><span>12h</span>
                </div>
              </div>

              <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={clearBeforeScan}
                  onChange={(e) => setClearBeforeScan(e.target.checked)}
                  className="accent-blue-500"
                />
                扫描前清空旧数据
              </label>
            </div>

            {/* 操作按钮 */}
            <div className="space-y-2">
              <button
                onClick={handleScan}
                disabled={scanning || !folderPath}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-medium text-sm transition"
              >
                {scanning ? "⏳ 扫描中..." : "🔍 扫描文件夹"}
              </button>

              <button
                onClick={fetchScanStatus}
                className="w-full py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition"
              >
                📊 查询扫描状态
              </button>

              <button
                onClick={handlePreview}
                disabled={previewing || !folderPath || !outputPath}
                className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-medium text-sm transition"
              >
                {previewing ? "⏳ 生成中..." : "📋 归档预览"}
              </button>

              <button
                onClick={handleGeocode}
                disabled={geocoding}
                className="w-full py-2.5 bg-purple-700 hover:bg-purple-600 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-medium text-sm transition"
                title="将扫描结果中的 GPS 坐标转为城市/省份名称，需要先完成扫描"
              >
                {geocoding ? "⏳ 地理编码中..." : "🌍 逆地理编码"}
              </button>
            </div>

            {/* 扫描状态卡片 */}
            {scanStatus && (
              <div className="bg-gray-800 rounded-lg p-4">
                <h3 className="text-xs font-semibold text-gray-400 mb-2 uppercase">数据库状态</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {Object.entries(scanStatus as object).map(([k, v]) => (
                    <div key={k} className="bg-gray-900 rounded px-2 py-1">
                      <div className="text-xs text-gray-500">{k}</div>
                      <div className="text-blue-300 font-mono">{String(v)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 右侧：结果面板 */}
          <div className="col-span-8 space-y-4">

            {/* 扫描进度 */}
            {(scanning || scanEvents.length > 0) && (
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-semibold text-gray-300">
                    🔄 扫描进度
                  </h2>
                  {lastProgress && (
                    <span className="text-xs text-gray-400">
                      {lastProgress.current}/{lastProgress.total}
                    </span>
                  )}
                </div>

                {/* 进度条 */}
                {lastProgress && lastProgress.total && (
                  <div className="mb-3">
                    <div className="bg-gray-700 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-blue-500 h-2 rounded-full transition-all"
                        style={{ width: `${(lastProgress.current! / lastProgress.total) * 100}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* 完成摘要 */}
                {completedEvent && (
                  <div className="mb-3 p-3 bg-emerald-900/30 border border-emerald-700 rounded text-sm">
                    <span className="text-emerald-400 font-semibold">✅ 扫描完成 </span>
                    <span className="text-gray-300">
                      共 {completedEvent.total_files} 个文件 · 有GPS: {completedEvent.with_gps} ·
                      无GPS: {completedEvent.without_gps} · 错误: {completedEvent.errors} ·
                      新增: {completedEvent.new_files} · 跳过(已有): {completedEvent.skipped}
                    </span>
                  </div>
                )}

                {/* 错误列表 */}
                {errorEvents.length > 0 && (
                  <div className="mb-3 p-3 bg-red-900/20 border border-red-800 rounded text-xs">
                    <div className="text-red-400 font-semibold mb-1">
                      ⚠️ {errorEvents.length} 个文件处理失败
                    </div>
                    {errorEvents.slice(0, 5).map((e, i) => (
                      <div key={i} className="text-red-300/70 truncate">
                        {e.file}: {e.message}
                      </div>
                    ))}
                    {errorEvents.length > 5 && (
                      <div className="text-red-400/50">...还有 {errorEvents.length - 5} 条</div>
                    )}
                  </div>
                )}

                {/* 最新进度行 */}
                {lastProgress && !completedEvent && (
                  <div className="text-xs text-gray-400 font-mono truncate">
                    📄 {lastProgress.file}
                    <span className={`ml-2 ${lastProgress.has_gps ? "text-emerald-400" : "text-gray-500"}`}>
                      {lastProgress.has_gps ? "GPS✓" : "无GPS"}
                    </span>
                    {lastProgress.datetime && (
                      <span className="ml-2 text-gray-500">{lastProgress.datetime?.slice(0, 16)}</span>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* 归档预览结果 */}
            {previewData && (
              <div className="bg-gray-800 rounded-lg p-4">
                <h2 className="text-sm font-semibold text-gray-300 mb-3">
                  📋 归档预览结果
                </h2>

                {/* 摘要 */}
                <div className="mb-4 grid grid-cols-5 gap-2 text-center">
                  {[
                    { label: "总文件", value: previewData.summary.total_files, color: "blue" },
                    { label: "大行程", value: previewData.summary.big_trips_created, color: "purple" },
                    { label: "子行程", value: previewData.summary.sub_trips_created, color: "emerald" },
                    { label: "无GPS", value: previewData.summary.files_without_gps, color: "yellow" },
                    { label: "待审核", value: previewData.summary.files_needing_review, color: "red" },
                  ].map((item) => (
                    <div key={item.label} className="bg-gray-900 rounded p-2">
                      <div className={`text-xl font-bold text-${item.color}-400`}>{item.value}</div>
                      <div className="text-xs text-gray-500">{item.label}</div>
                    </div>
                  ))}
                </div>

                {previewData.summary.message && (
                  <div className="mb-3 p-2 bg-yellow-900/30 border border-yellow-700 rounded text-xs text-yellow-300">
                    ⚠️ {previewData.summary.message}
                  </div>
                )}

                {/* 行程树结构 */}
                {previewData.trips_structure.length > 0 ? (
                  <div className="space-y-3">
                    {previewData.trips_structure.map((bigTrip, bi) => (
                      <div key={bi} className="border border-gray-700 rounded-lg overflow-hidden">
                        {/* 大行程标题 */}
                        <div className="bg-blue-900/40 px-4 py-2 flex items-center justify-between">
                          <div>
                            <span className="text-blue-300 font-mono font-semibold">
                              📁 {bigTrip.folder}
                            </span>
                          </div>
                          <div className="text-xs text-gray-400">
                            {bigTrip.total_files} 个文件 · {bigTrip.start_date?.slice(0, 10)} → {bigTrip.end_date?.slice(0, 10)}
                          </div>
                        </div>

                        {/* 子行程列表 */}
                        <div className="divide-y divide-gray-700/50">
                          {bigTrip.sub_trips.map((sub, si) => {
                            const tripKey = `${bigTrip.folder}/${sub.folder}`;
                            const isExpanded = expandedTrips.has(tripKey);
                            const subFiles = previewData.preview.filter(
                              p => p.sub_trip_folder === sub.folder && p.big_trip_folder === bigTrip.folder
                            );
                            return (
                              <div key={si}>
                                {/* 子行程行 */}
                                <div
                                  className="px-4 py-2 flex items-center justify-between hover:bg-gray-700/30 cursor-pointer"
                                  onClick={() => toggleTrip(tripKey)}
                                >
                                  <div className="flex items-center gap-3">
                                    <span className="text-gray-500 text-xs w-4 text-right">{si + 1}</span>
                                    <span className="text-emerald-300 font-mono text-sm">
                                      📂 {sub.folder}
                                    </span>
                                    <span className="text-xs text-gray-500 bg-gray-700 px-1.5 py-0.5 rounded">
                                      {sub.location || "未知地点"}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-3 text-xs text-gray-400">
                                    <span>{sub.file_count} 个文件 · {sub.start_date?.slice(5, 10)} → {sub.end_date?.slice(5, 10)}</span>
                                    <span className="text-gray-500">{isExpanded ? "▲" : "▼"}</span>
                                  </div>
                                </div>
                                {/* 展开的文件列表 */}
                                {isExpanded && subFiles.length > 0 && (
                                  <div className="bg-gray-900/60 px-4 py-2 border-t border-gray-700/50">
                                    <div className="text-xs text-gray-500 mb-1.5">📄 文件列表（{subFiles.length} 个）</div>
                                    <div className="space-y-0.5 max-h-48 overflow-y-auto">
                                      {subFiles.map((f, fi) => (
                                        <div key={fi} className="flex items-center gap-2 text-xs font-mono">
                                          <span className="text-gray-600 w-5 text-right">{fi + 1}.</span>
                                          <span className="text-gray-300">{f.file_name}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    暂无归档数据，请先扫描文件夹
                  </div>
                )}

                {/* 文件预览（前 20 条） */}
                {previewData.preview.length > 0 && (
                  <div className="mt-4">
                    <h3 className="text-xs font-semibold text-gray-400 mb-2 uppercase">
                      文件移动预览（前 20 条，共 {previewData.preview.length} 条）
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs font-mono">
                        <thead>
                          <tr className="text-gray-500 border-b border-gray-700">
                            <th className="text-left py-1 pr-4">文件名</th>
                            <th className="text-left py-1 pr-4">目标路径（截取）</th>
                          </tr>
                        </thead>
                        <tbody>
                          {previewData.preview.slice(0, 20).map((item, i) => (
                            <tr key={i} className="border-b border-gray-700/30 hover:bg-gray-700/20">
                              <td className="py-1 pr-4 text-gray-300 truncate max-w-xs">{item.file_name}</td>
                              <td className="py-1 text-emerald-400 truncate max-w-md" title={item.target_path}>
                                ...{item.big_trip_folder}/{item.sub_trip_folder}/{item.file_name}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 调试日志 */}
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold text-gray-300">🔧 调试日志</h2>
                <button
                  onClick={() => setDebugLog([])}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  清空
                </button>
              </div>
              <div className="bg-gray-900 rounded p-3 h-32 overflow-y-auto font-mono text-xs">
                {debugLog.length === 0 ? (
                  <span className="text-gray-600">日志为空，执行操作后显示</span>
                ) : (
                  debugLog.map((log, i) => (
                    <div key={i} className={`${log.includes("失败") || log.includes("error") ? "text-red-400" : log.includes("完成") || log.includes("成功") ? "text-emerald-400" : "text-gray-400"}`}>
                      {log}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* 原始 JSON 输出（调试用） */}
            {previewRaw && (
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-gray-300">📄 原始 JSON 响应</h2>
                  <button
                    onClick={() => setPreviewRaw("")}
                    className="text-xs text-gray-500 hover:text-gray-300"
                  >
                    清空
                  </button>
                </div>
                <pre className="bg-gray-900 rounded p-3 text-xs text-gray-300 overflow-auto max-h-64 font-mono">
                  {previewRaw}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * MapPage.tsx
 * 行程地图页面
 *
 * 功能：
 *   1. 调用 /api/map/html 获取 Folium HTML，嵌入 <iframe>
 *   2. 地图中城市热点点击 → 接收 postMessage → 右侧显示该城市照片
 *   3. 照片缩略图通过 /api/media/thumbnail 加载
 *   4. 点击照片 → 通过 Electron IPC 用系统程序打开
 */
import { useEffect, useState, useCallback } from "react";
import { useAppStore } from "@/store/appStore";
import clsx from "clsx";

const API = "http://localhost:17890";
const THUMB_WIDTH = 160; // 缩略图宽度 px

// ── 类型 ─────────────────────────────────────────────────────

interface HotspotInfo {
  city: string;
  province: string;
  lat: number;
  lng: number;
  total: number;
}

interface PhotoFile {
  id: number;
  file_name: string;
  file_type: "photo" | "video";
  original_path: string;
  current_path: string | null;
  datetime_original: string | null;
  city: string | null;
  province: string | null;
}

// ── 缩略图卡片 ───────────────────────────────────────────────

function PhotoCard({
  photo,
  onOpen,
}: {
  photo: PhotoFile;
  onOpen: (path: string) => void;
}) {
  const filePath = photo.current_path || photo.original_path;
  const isVideo = photo.file_type === "video";
  const thumbUrl =
    `${API}/api/media/thumbnail?path=${encodeURIComponent(filePath)}&width=${THUMB_WIDTH}&quality=70`;

  const date = photo.datetime_original
    ? photo.datetime_original.slice(0, 10)
    : "";

  return (
    <button
      onClick={() => onOpen(filePath)}
      title={`${photo.file_name}\n${date}`}
      className="relative group rounded-lg overflow-hidden bg-slate-800 border border-slate-700/50 hover:border-blue-500/50 transition-all aspect-square"
    >
      {isVideo ? (
        <div className="w-full h-full flex flex-col items-center justify-center bg-slate-800">
          <span className="text-2xl">🎬</span>
          <span className="text-xs text-slate-400 mt-1 px-1 truncate max-w-full">
            {photo.file_name}
          </span>
        </div>
      ) : (
        <img
          src={thumbUrl}
          alt={photo.file_name}
          loading="lazy"
          className="w-full h-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src =
              "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'><rect fill='%231e293b' width='100%25' height='100%25'/></svg>";
          }}
        />
      )}

      {/* 悬停遮罩 */}
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all flex items-end">
        <div className="w-full px-1.5 py-1 bg-gradient-to-t from-black/70 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="text-xs text-white truncate">{photo.file_name}</div>
          {date && <div className="text-xs text-slate-300">{date}</div>}
        </div>
      </div>

      {/* 视频徽章 */}
      {isVideo && (
        <div className="absolute top-1 right-1 bg-black/60 text-white text-xs px-1 rounded">
          VIDEO
        </div>
      )}
    </button>
  );
}

// ── 照片侧边栏 ───────────────────────────────────────────────

function PhotoSidebar({
  hotspot,
  photos,
  loading,
  onClose,
  onOpen,
}: {
  hotspot: HotspotInfo;
  photos: PhotoFile[];
  loading: boolean;
  onClose: () => void;
  onOpen: (path: string) => void;
}) {
  return (
    <div className="h-full flex flex-col bg-slate-900 border-l border-slate-700/50">
      {/* 标题 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50 flex-shrink-0">
        <div>
          <div className="text-sm font-semibold text-slate-200">
            📍 {hotspot.city}
          </div>
          {hotspot.province && (
            <div className="text-xs text-slate-400 mt-0.5">{hotspot.province}</div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">{hotspot.total} 张</span>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-lg leading-none transition-colors"
          >
            ✕
          </button>
        </div>
      </div>

      {/* 照片网格 */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            <div className="text-center space-y-2">
              <div className="animate-pulse text-2xl">🖼️</div>
              <div>加载中...</div>
            </div>
          </div>
        ) : photos.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm text-center">
            <div>暂无照片数据</div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              {photos.map((photo) => (
                <PhotoCard key={photo.id} photo={photo} onOpen={onOpen} />
              ))}
            </div>
            {hotspot.total > photos.length && (
              <div className="text-center text-xs text-slate-500 mt-3">
                显示前 {photos.length} 张，共 {hotspot.total} 张
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── 主页面 ───────────────────────────────────────────────────

export default function MapPage() {
  const { sourceFolderPath, setCurrentPage } = useAppStore();

  const [mapHtml, setMapHtml] = useState<string>("");
  const [mapLoading, setMapLoading] = useState(true);
  const [mapError, setMapError] = useState<string>("");

  const [hotspot, setHotspot] = useState<HotspotInfo | null>(null);
  const [photos, setPhotos] = useState<PhotoFile[]>([]);
  const [photosLoading, setPhotosLoading] = useState(false);

  // ── 加载地图 HTML ───────────────────────────────────────────

  const loadMap = useCallback(async () => {
    setMapLoading(true);
    setMapError("");
    try {
      const params = new URLSearchParams();
      if (sourceFolderPath) params.set("folder_path", sourceFolderPath);
      const res = await fetch(`${API}/api/map/html?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const html = await res.text();
      setMapHtml(html);
    } catch (e) {
      setMapError(`地图加载失败：${e}`);
    } finally {
      setMapLoading(false);
    }
  }, [sourceFolderPath]);

  useEffect(() => {
    loadMap();
  }, [loadMap]);

  // ── 监听 iframe postMessage ─────────────────────────────────

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type !== "tripmap_click") return;
      const { city, province, lat, lng, total } = e.data as HotspotInfo & {
        type: string;
      };
      setHotspot({ city, province, lat, lng, total });
      loadCityPhotos(city, province);
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [sourceFolderPath]);

  // ── 加载城市照片 ────────────────────────────────────────────

  const loadCityPhotos = async (city: string, province: string) => {
    setPhotosLoading(true);
    setPhotos([]);
    try {
      const params = new URLSearchParams({ city, limit: "60" });
      if (sourceFolderPath) params.set("folder_path", sourceFolderPath);
      const res = await fetch(`${API}/api/map/photos?${params}`);
      const json = await res.json();
      if (json.success) {
        setPhotos(json.data.files);
      }
    } catch (e) {
      console.error("加载城市照片失败:", e);
    } finally {
      setPhotosLoading(false);
    }
  };

  // ── 打开照片 ────────────────────────────────────────────────

  const handleOpenPhoto = (filePath: string) => {
    const electronAPI = (window as any).electronAPI;
    if (electronAPI?.openPath) {
      electronAPI.openPath(filePath);
    } else {
      alert(`文件路径：\n${filePath}`);
    }
  };

  // ── 渲染 ─────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      {/* 页头 */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-slate-700/50 flex-shrink-0 bg-slate-900/60">
        <div>
          <h1 className="text-base font-bold text-slate-100">🗺️ 行程地图</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {sourceFolderPath ? (
              <span className="font-mono">{sourceFolderPath}</span>
            ) : (
              "显示所有已扫描的 GPS 照片位置"
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadMap}
            disabled={mapLoading}
            className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-600 px-3 py-1.5 rounded-lg transition-colors"
          >
            {mapLoading ? "⏳ 加载中..." : "🔄 刷新地图"}
          </button>
          <button
            onClick={() => setCurrentPage("archive")}
            className="text-xs text-slate-500 hover:text-slate-300 px-3 py-1.5 transition-colors"
          >
            ← 返回归档
          </button>
        </div>
      </div>

      {/* 主体：地图 + 可选侧边栏 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 地图区 */}
        <div
          className={clsx(
            "flex-1 relative overflow-hidden transition-all duration-300",
            hotspot ? "basis-[62%]" : "basis-full"
          )}
        >
          {mapLoading && (
            <div className="absolute inset-0 bg-slate-900 flex flex-col items-center justify-center z-10 text-slate-400">
              <div className="text-4xl mb-3 animate-pulse">🗺️</div>
              <div className="text-sm">正在生成地图...</div>
              <div className="text-xs mt-1 opacity-50">首次生成需要几秒钟</div>
            </div>
          )}

          {mapError && (
            <div className="absolute inset-0 bg-slate-900 flex flex-col items-center justify-center z-10">
              <div className="text-4xl mb-3">❌</div>
              <div className="text-sm text-red-400">{mapError}</div>
              <button
                onClick={loadMap}
                className="mt-4 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-300 transition-colors"
              >
                重试
              </button>
            </div>
          )}

          {mapHtml && !mapLoading && (
            <iframe
              srcDoc={mapHtml}
              title="TripTrace 行程地图"
              className="w-full h-full border-0"
              sandbox="allow-scripts allow-same-origin"
            />
          )}

          {/* 提示（无地图时） */}
          {!mapHtml && !mapLoading && !mapError && (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500">
              <div className="text-5xl mb-3 opacity-30">🗺️</div>
              <div className="text-sm">暂无地图数据</div>
              <div className="text-xs mt-1 opacity-60">
                请先在扫描页面完成扫描和逆地理编码
              </div>
              <button
                onClick={() => setCurrentPage("scan")}
                className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm text-white transition-all"
              >
                🔍 前往扫描页面 →
              </button>
            </div>
          )}
        </div>

        {/* 照片侧边栏（点击热点后显示） */}
        {hotspot && (
          <div className="w-[38%] flex-shrink-0 overflow-hidden">
            <PhotoSidebar
              hotspot={hotspot}
              photos={photos}
              loading={photosLoading}
              onClose={() => {
                setHotspot(null);
                setPhotos([]);
              }}
              onOpen={handleOpenPhoto}
            />
          </div>
        )}
      </div>
    </div>
  );
}

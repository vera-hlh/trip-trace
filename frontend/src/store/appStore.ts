/**
 * appStore.ts
 * 全局状态管理（Zustand）
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type AppPage =
  | "home"
  | "folder-setup"
  | "scan"
  | "archive"
  | "map"
  | "history"
  | "test";

export interface AppSettings {
  bigTripThresholdDays: number;
  smallTripThresholdHours: number;
  copyMode: boolean; // true=复制, false=移动
}

// ── 行程树数据结构（来自 archive/preview，可用户编辑）────────

export interface SubTripFileItem {
  name: string;   // 文件名（如 IMG_20250201_143440.jpg）
  path: string;   // 完整原始路径（用于缩略图请求）
}

export interface SubTripData {
  folder: string;      // 原始文件夹名（后端生成）
  displayName: string; // 用户可编辑显示名称
  location: string;
  start_date: string | null;
  end_date: string | null;
  file_count: number;
  files?: SubTripFileItem[];  // 文件列表（缩略图预览用）
}

export interface BigTripData {
  folder: string;      // 原始文件夹名（后端生成）
  displayName: string; // 用户可编辑显示名称
  start_date: string | null;
  end_date: string | null;
  total_files: number;
  sub_trips: SubTripData[];
}

// ── State 接口 ────────────────────────────────────────────────

interface AppState {
  // 页面导航
  currentPage: AppPage;
  setCurrentPage: (page: AppPage) => void;

  // 文件夹路径（持久化）
  sourceFolderPath: string;
  outputFolderPath: string;
  setSourceFolderPath: (path: string) => void;
  setOutputFolderPath: (path: string) => void;

  // 归档参数（持久化）
  settings: AppSettings;
  updateSettings: (patch: Partial<AppSettings>) => void;

  // 行程树（持久化 - 用户可能已编辑重命名/合并）
  tripStructure: BigTripData[] | null;
  setTripStructure: (trips: BigTripData[] | null) => void;

  // 行程类型（持久化 - 影响地理编码策略和异常文件处理）
  tripType: "domestic" | "abroad" | "mixed";
  setTripType: (type: "domestic" | "abroad" | "mixed") => void;

  // 后端连接状态（不持久化，运行时检测）
  backendReady: boolean;
  setBackendReady: (ready: boolean) => void;
}

// ── Store 实例 ────────────────────────────────────────────────

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // 导航
      currentPage: "home",
      setCurrentPage: (page) => set({ currentPage: page }),

      // 路径
      sourceFolderPath: "",
      outputFolderPath: "",
      setSourceFolderPath: (path) => set({ sourceFolderPath: path }),
      setOutputFolderPath: (path) => set({ outputFolderPath: path }),

      // 归档参数
      settings: {
        bigTripThresholdDays: 30,
        smallTripThresholdHours: 2,
        copyMode: true,
      },
      updateSettings: (patch) =>
        set((s) => ({ settings: { ...s.settings, ...patch } })),

      // 行程树
      tripStructure: null,
      setTripStructure: (trips) => set({ tripStructure: trips }),

      // 行程类型
      tripType: "domestic" as const,
      setTripType: (type) => set({ tripType: type }),

      // 后端状态
      backendReady: false,
      setBackendReady: (ready) => set({ backendReady: ready }),
    }),
    {
      name: "trip-trace-app",
      partialize: (s) => ({
        sourceFolderPath: s.sourceFolderPath,
        outputFolderPath: s.outputFolderPath,
        settings: s.settings,
        tripStructure: s.tripStructure,
        tripType: s.tripType,
      }),
    }
  )
);

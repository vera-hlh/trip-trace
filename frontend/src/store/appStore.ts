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
  | "test";

export interface AppSettings {
  bigTripThresholdDays: number;
  smallTripThresholdHours: number;
  copyMode: boolean; // true=复制, false=移动
}

interface AppState {
  // 页面导航
  currentPage: AppPage;
  setCurrentPage: (page: AppPage) => void;

  // 文件夹路径
  sourceFolderPath: string;
  outputFolderPath: string;
  setSourceFolderPath: (path: string) => void;
  setOutputFolderPath: (path: string) => void;

  // 归档参数
  settings: AppSettings;
  updateSettings: (patch: Partial<AppSettings>) => void;

  // 后端状态
  backendReady: boolean;
  setBackendReady: (ready: boolean) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // 导航
      currentPage: "home",
      setCurrentPage: (page) => set({ currentPage: page }),

      // 路径（持久化）
      sourceFolderPath: "",
      outputFolderPath: "",
      setSourceFolderPath: (path) => set({ sourceFolderPath: path }),
      setOutputFolderPath: (path) => set({ outputFolderPath: path }),

      // 归档参数（持久化）
      settings: {
        bigTripThresholdDays: 30,
        smallTripThresholdHours: 2,
        copyMode: true,
      },
      updateSettings: (patch) =>
        set((s) => ({ settings: { ...s.settings, ...patch } })),

      // 后端状态（不持久化）
      backendReady: false,
      setBackendReady: (ready) => set({ backendReady: ready }),
    }),
    {
      name: "trip-trace-app",
      // 只持久化路径和参数，不持久化 UI 状态
      partialize: (s) => ({
        sourceFolderPath: s.sourceFolderPath,
        outputFolderPath: s.outputFolderPath,
        settings: s.settings,
      }),
    }
  )
);

import { contextBridge, ipcRenderer } from "electron";

/**
 * electronAPI — 暴露给渲染进程的安全 API
 * 通过 contextBridge 隔离，渲染进程只能调用白名单方法
 */
contextBridge.exposeInMainWorld("electronAPI", {
  /** 打开系统文件夹选择对话框（返回完整路径或 null） */
  openFolderDialog: (): Promise<string | null> =>
    ipcRenderer.invoke("open-folder-dialog"),

  /** 打开归档输出目录对话框（支持新建文件夹，返回完整路径或 null） */
  openSaveDialog: (): Promise<string | null> =>
    ipcRenderer.invoke("open-save-dialog"),

  /** 用系统默认程序打开文件/文件夹 */
  openPath: (filePath: string): Promise<void> =>
    ipcRenderer.invoke("open-path", filePath),

  /** 在文件管理器中高亮显示文件 */
  showItemInFolder: (filePath: string): Promise<void> =>
    ipcRenderer.invoke("show-item-in-folder", filePath),
});

// 类型声明，供 TypeScript 渲染进程代码提示
export type ElectronAPI = {
  openFolderDialog: () => Promise<string | null>;
  openSaveDialog: () => Promise<string | null>;
  openPath: (filePath: string) => Promise<void>;
  showItemInFolder: (filePath: string) => Promise<void>;
};

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  openFolderDialog: () => ipcRenderer.invoke("open-folder-dialog"),
  openSaveDialog: () => ipcRenderer.invoke("open-save-dialog"),
});

import { app, BrowserWindow, ipcMain, dialog } from "electron";
import { join } from "path";
import { spawn, ChildProcess } from "child_process";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const BACKEND_PORT = 17890;
const isDev = !app.isPackaged;

/** 启动 Python 后端子进程 */
function startBackend() {
  const backendPath = isDev
    ? null // 开发模式下手动启动后端
    : join(process.resourcesPath, "backend", "trip-trace-backend.exe");

  if (!isDev && backendPath) {
    backendProcess = spawn(backendPath, [], {
      env: { ...process.env, TRIPRACE_BACKEND_PORT: String(BACKEND_PORT) },
    });
    backendProcess.stdout?.on("data", (d) => console.log("[Backend]", d.toString()));
    backendProcess.stderr?.on("data", (d) => console.error("[Backend]", d.toString()));
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: "旅迹 · TripTrace",
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      // 允许加载本地 folium HTML 地图
      webSecurity: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(join(__dirname, "../dist/index.html"));
  }
}

// IPC: 打开文件夹选择对话框
ipcMain.handle("open-folder-dialog", async () => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    properties: ["openDirectory"],
    title: "选择照片/视频文件夹",
  });
  return result.filePaths[0] ?? null;
});

// IPC: 打开保存目录对话框
ipcMain.handle("open-save-dialog", async () => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    properties: ["openDirectory", "createDirectory"],
    title: "选择归档输出目录",
  });
  return result.filePaths[0] ?? null;
});

app.whenReady().then(() => {
  startBackend();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  backendProcess?.kill();
  if (process.platform !== "darwin") app.quit();
});

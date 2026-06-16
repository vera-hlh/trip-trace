import { app, BrowserWindow, ipcMain, dialog, shell } from "electron";
import { join } from "path";
import { spawn, ChildProcess } from "child_process";
import http from "http";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const BACKEND_PORT = 17890;
const isDev = !app.isPackaged;

// ── 后端健康检测 ──────────────────────────────────────────────

/**
 * 轮询后端 /health 接口，直到成功或超时
 * @param maxWaitMs 最长等待毫秒数（默认 30s）
 * @param intervalMs 轮询间隔（默认 500ms）
 */
function waitForBackend(maxWaitMs = 30_000, intervalMs = 500): Promise<boolean> {
  return new Promise((resolve) => {
    const start = Date.now();

    function check() {
      const req = http.get(
        `http://127.0.0.1:${BACKEND_PORT}/health`,
        { timeout: 2000 },
        (res) => {
          if (res.statusCode === 200) {
            resolve(true);
          } else {
            retry();
          }
        }
      );
      req.on("error", retry);
      req.on("timeout", () => { req.destroy(); retry(); });
    }

    function retry() {
      if (Date.now() - start >= maxWaitMs) {
        resolve(false); // 超时
      } else {
        setTimeout(check, intervalMs);
      }
    }

    check();
  });
}

// ── 启动 Python 后端子进程（仅生产模式）────────────────────────

function startBackend() {
  if (isDev) {
    console.log("[Electron] 开发模式：请手动启动后端");
    return;
  }

  const backendExe = join(process.resourcesPath, "backend", "trip-trace-backend.exe");

  console.log("[Electron] 启动后端子进程:", backendExe);
  backendProcess = spawn(backendExe, [], {
    env: {
      ...process.env,
      TRIPRACE_BACKEND_PORT: String(BACKEND_PORT),
    },
    detached: false,
  });

  backendProcess.stdout?.on("data", (d: Buffer) =>
    console.log("[Backend]", d.toString().trim())
  );
  backendProcess.stderr?.on("data", (d: Buffer) =>
    console.error("[Backend ERR]", d.toString().trim())
  );
  backendProcess.on("exit", (code, signal) =>
    console.log(`[Backend] 进程退出 code=${code} signal=${signal}`)
  );
}

// ── 创建主窗口 ────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    title: "旅迹 · TripTrace",
    backgroundColor: "#0f172a", // slate-950，避免白色闪烁
    show: false,               // 等内容加载完再显示
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false,      // 允许加载本地 folium HTML 地图
    },
  });

  // 内容就绪后再显示，避免白屏
  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(join(__dirname, "../dist/index.html"));
  }
}

// ── IPC 处理器 ────────────────────────────────────────────────

// 打开源文件夹选择对话框
ipcMain.handle("open-folder-dialog", async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"],
    title: "选择照片/视频文件夹",
  });
  return result.canceled ? null : (result.filePaths[0] ?? null);
});

// 打开归档输出目录对话框（支持新建文件夹）
ipcMain.handle("open-save-dialog", async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory", "createDirectory"],
    title: "选择归档输出目录",
  });
  return result.canceled ? null : (result.filePaths[0] ?? null);
});

// 用系统默认程序打开路径（文件/文件夹）
ipcMain.handle("open-path", async (_event, filePath: string) => {
  await shell.openPath(filePath);
});

// 在文件管理器中显示文件
ipcMain.handle("show-item-in-folder", (_event, filePath: string) => {
  shell.showItemInFolder(filePath);
});

// ── 应用生命周期 ──────────────────────────────────────────────

app.whenReady().then(async () => {
  startBackend();

  // 生产模式：等待后端就绪再显示主窗口
  if (!isDev) {
    console.log("[Electron] 等待后端服务就绪...");
    const ready = await waitForBackend(30_000);
    if (!ready) {
      console.warn("[Electron] 后端启动超时，仍然打开窗口");
    } else {
      console.log("[Electron] 后端已就绪");
    }
  }

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  // 终止后端子进程
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
    console.log("[Electron] 已终止后端子进程");
  }
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
});

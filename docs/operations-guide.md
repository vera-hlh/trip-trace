# TripTrace 开发与验证操作指引

**最后更新**：2026-11-20  
**适用**：本机 Windows 开发、前后端启动、隔离数据库测试、前端手工验证。

> 这是一份操作手册，不是设计文档。设计/里程碑见 [2026-11-12 分析报告与实施计划](2026-11-12-analysis-and-plan.md)。

---

## 1. 环境

- 项目：`C:\Dev\trip-trace`
- 后端：`backend\.venv\Scripts\python.exe`
- 前端：`frontend`
- 后端端口：`17890`
- 前端端口：`5173`

---

## 2. 快速启动（两个 PowerShell 窗口）

### 窗口 1：后端

```powershell
cd C:\Dev\trip-trace\backend
.\.venv\Scripts\python.exe uvicorn_config.py
```

看到类似输出即成功：

```text
Uvicorn running on http://127.0.0.1:17890
```

窗口保持打开。

### 窗口 2：前端 Electron

```powershell
cd C:\Dev\trip-trace\frontend
npm run dev
```

如果 `npm` 被执行策略拦截：

```powershell
npm.cmd run dev
```

或：

```powershell
cmd /c npm run dev
```

必须用 `npm run dev` 做完整界面验证；`npm run dev:renderer` 只开浏览器，没有 Electron 文件夹选择对话框。

---

## 3. 使用隔离数据库（推荐测试用）

在**启动后端的同一个窗口**里，先设置环境变量，再启动：

```powershell
$env:TRIPRACE_DB_PATH = "C:\TripTrace-Test\phase2-test.sqlite"
cd C:\Dev\trip-trace\backend
.\.venv\Scripts\python.exe uvicorn_config.py
```

要点：

- 环境变量只对当前 PowerShell 窗口生效；
- 必须在启动后端之前设置；
- 换了 `TRIPRACE_DB_PATH` 必须重启后端；
- 不设置时，默认使用 `%APPDATA%\TripTrace\triprace.sqlite`；
- 旧数据库会自动补新字段，但旧记录不会自动回填景区。

---

## 4. 正确停止与端口清理

### 4.1 优先方式

在窗口里按 `Ctrl+C`，等待进程退出。

### 4.2 直接关窗口

一般也能结束进程；偶尔会留下孤儿进程占端口。检查：

```powershell
Get-NetTCPConnection -LocalPort 17890,5173 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess
```

没有输出说明端口已释放。

### 4.3 端口被占用

先确认进程是不是 TripTrace 的：

```powershell
$pid = (Get-NetTCPConnection -LocalPort 17890 -State Listen -ErrorAction SilentlyContinue).OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId=$pid" |
  Select-Object ProcessId, Name, CommandLine
```

`CommandLine` 包含 `uvicorn_config.py` 或 `C:\Dev\trip-trace\backend` 才停：

```powershell
Stop-Process -Id $pid
```

前端 5173 同理。

> 不要使用 `Get-Process python | Stop-Process -Force` 或 `Get-Process node | Stop-Process -Force`，会误杀其他项目。

---

## 5. 前端验证流程（Phase 1b / 2a）

### 5.1 准备

```powershell
$test = "C:\TripTrace-Test"
New-Item -ItemType Directory -Force "$test\src", "$test\out" | Out-Null
```

建议先用少量文件测归档/清理；扫描和地理编码可以用完整宜昌样本。

### 5.2 启动

按第 2、3 节启动后端（隔离 DB）和 Electron。

### 5.3 扫描与地理编码

1. 源目录选宜昌样本；
2. 输出目录选 `C:\TripTrace-Test\out`；
3. 扫描；
4. 选择「国内行程」；
5. 执行地理编码。

宜昌样本参考结果：

- 302 个媒体文件；
- 301 个有 GPS；
- 约 27 次高德调用；
- 1 个大行程；
- 约 13 个子行程。

### 5.4 景区审核

在 POI 审核区检查：

- 行首是否显示 `🏞 景区名`；
- 展开后是否有候选景区按钮；
- 勾选多个 POI 组后，输入景区名，点「应用到已选」；
- 批量设置后输入框应清空；
- 超过 6 张照片时，点「加载更多」；
- 勾选单张/多张照片，输入新 POI，点「修改所选照片」；
- POI 分组刷新后，日志应出现「POI 分组已刷新：N 组」。

### 5.5 行程预览

生成行程预览后，宜昌样本应大致出现：

| 子行程 | 文件数 |
|---|---:|
| 南岳衡山风景名胜区 | 5 + 67 |
| 南岳里庙会文化美食街区 | 7 |
| 株洲伽蓝庙 | 14 |
| 松山湖旅游度假区宜昌展厅 | 3 |
| 坛子岭风景区 | 5 |
| 三峡大坝旅游区 | 1 |
| 清江画廊旅游度假区 | 60 |
| 听风谷 | 22 |
| 三峡人家风景区 | 98 |
| 湖南烈士公园 | 1 |

重点确认：

- 听风谷是否独立；
- 三峡人家、清江画廊是否分开；
- 坛子岭/三峡大坝是否仍分开（已知待归一化）。

### 5.6 手动拆分子行程

1. 在行程树找到要拆的子行程；
2. 点「✂️ 拆分」；
3. 勾选要拆出的照片（可看文件名、时间、景区、POI）；
4. 输入新子行程名称；
5. 点「拆出 N 张」；
6. 剩余照片保留原名称，可继续拆。

注意：

- 至少要选 1 张，不能选完全部；
- 拆分后目标路径和方案版本会自动更新；
- 当前是“选中/剩余”两组，拆 3 组需要重复操作；
- 拆分只影响方案，不复制文件。

### 5.7 归档/清理（只对副本）

不要直接对真实原目录执行清理。使用 `C:\TripTrace-Test\src` 的副本：

1. 扫描副本；
2. 生成方案；
3. 执行归档到 `C:\TripTrace-Test\out`；
4. 检查目录、`trip_log.md`、备注；
5. 清理时确认进入回收站；
6. 检查目标文件仍在。

---

## 6. 当前功能状态

| 功能 | 状态 |
|---|---|
| 扫描/EXIF/GPS/HEIC/视频时间 | ✅ |
| 国内高德 / 境外 Nominatim | ✅ |
| 景区候选：AOI + 父级 POI 链 | ✅ |
| 景区显示/单组修改/批量修改 | ✅ |
| 照片级 POI 修改/加载更多 | ✅ |
| 景区边界自动切分 | ✅ |
| 手动拆分 UI | ✅（选中/剩余两组合并，可重复拆） |
| 景区名归一化/别名 | ⏳ 未做 |
| LLM 辅助 | ⏳ 未做 |
| 公共 Overpass | ⚠️ 不稳定，常 502 |

---

## 7. 已知问题（不是崩溃）

- 坛子岭风景区 与 三峡大坝旅游区 仍可能拆成两个子行程；
- 松山湖旅游度假区宜昌展厅 3 张是 API 返回，暂保留；
- 部分城区/道路无景区，按城市/时间切分；
- 公共 Overpass 超时/502 时会退避 10 分钟，境外景点可能为空；
- `planId` 不跨应用重启持久化，重启后需重新生成方案；
- 还没有 `DELETE` 方案、按时间拆分、执行幂等；
- 图片备注使用 Pillow 重编码，可能有质量损失；
- 旧数据不会自动补 `area_name`，需要重新地理编码或手动设置。

---

## 8. 常见错误

### `npm.ps1` 无法加载，禁止运行脚本

用：

```powershell
npm.cmd run dev
```

或只对当前用户放开：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### `__dirname is not defined`

已在 `frontend/package.json` 移除 `"type": "module"` 修复；更新代码后重启 `npm run dev`。

### DevTools 的 Autofill 报错

```text
Request Autofill.enable failed
Request Autofill.setAddresses failed
```

是 Electron DevTools 的无害提示，不是应用错误。默认已不自动打开 DevTools；需要时：

```powershell
$env:TRIPRACE_DEVTOOLS = "1"
npm run dev
```

### 端口被占用

见第 4.3 节，只停 TripTrace 自己的进程。

### 改了 `TRIPRACE_DB_PATH` 但没生效

确认：

- 变量和后端启动在同一个 PowerShell 窗口；
- 设置后重启了后端；
- 没有使用 `scripts/start-dev.ps1`（它会用默认 DB）。

### 景区为空

- 旧数据没有 `area_name`；
- 重新地理编码或手动设置；
- 城区/道路点可能确实没有景区候选。

### 前端改了代码但没变化

- 页面 `.tsx` 通常 Vite HMR 自动刷新；
- Electron 主进程/preload 改动需重启 `npm run dev`；
- 后端 `.env`/DB 路径改动需重启后端。

---

## 9. 常用命令

```powershell
# 后端
cd C:\Dev\trip-trace\backend
.\.venv\Scripts\python.exe uvicorn_config.py

# 前端
cd C:\Dev\trip-trace\frontend
npm run dev

# 健康检查
Invoke-WebRequest http://127.0.0.1:17890/health

# 端口检查
Get-NetTCPConnection -LocalPort 17890,5173 -State Listen -ErrorAction SilentlyContinue

# 后端测试
cd C:\Dev\trip-trace
backend\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider --basetemp .pytest-tmp

# 前端类型检查
cd frontend
npx tsc --noEmit

# 渲染端构建
npx vite build --mode renderer
```

---

## 10. 相关文档

- [M7 验证计划与记录](2026-11-13-m7-validation.md)
- [东北边境真实样本验证](2026-11-14-real-sample-validation.md)
- [越南游轮真实样本验证](2026-11-14-vietnam-sample-validation.md)
- [高德 AOI / 父级 POI 实验](2026-11-16-amap-aoi-spike.md)
- [Phase 1：景区字段与候选](2026-11-18-phase1-area.md)
- [Phase 2：景区边界切分](2026-11-20-phase2-area-segmentation.md)
- [Overpass 境外景点后续事项](2026-11-13-overpass-followup.md)

# TripTrace 项目交接文档 - Phase 4 主体完成

> 更新时间：2026-06-26（最新，含行程重建功能）

---

## 项目概述

**旅迹 · TripTrace**：Windows 桌面工具，用于智能整理旅行照片/视频
- GitHub：https://github.com/vera-hlh/trip-trace
- 本地路径：`C:\Dev\trip-trace`
- 技术栈：Electron + React + TypeScript + Tailwind CSS / Python FastAPI + SQLite

---

## 当前完成进度（最新）

### ✅ Phase 1~3 全部完成（见历史记录）

### ✅ Phase 3 扩展：高德 API + POI 集成

| 功能 | 状态 | 说明 |
|---|---|---|
| 高德 API 接入 | ✅ | `.env` 配置，三层逆地理编码策略 |
| POI 旅行类型过滤 | ✅ | 13种旅行相关类型（含火车站150200、乡镇190106），优先级排序 |
| WGS-84 坐标系修复 | ✅ | `coordsys=gps` + EXIF GPSMapDatum 自动检测 + GCJ-02 逆转换 |
| **township 乡镇字段** | ✅ | 高德 `addressComponent.township` 提取（精确行政区划，不依赖搜索半径）|
| **2000m 搜索半径** | ✅ | 从 1000m 扩大到 2000m，适应地广人稀地区 |
| POI 审核 UI | ✅ | 地理编码后自动加载可编辑 POI 分组 |

### ✅ Phase 4 功能强化（P0+P1 全部完成）

| 功能 | 状态 | 说明 |
|---|---|---|
| 跳过已有 city 的文件 | ✅ | `city IS NULL` 才触发地理编码（有city=已处理） |
| 数据库 user_id 字段 | ✅ | 多用户预留，默认 "local" |
| ArchiveLog 操作记录 | ✅ | 每次归档自动写入本地日志 |
| 归档时生成 trip_log.md | ✅ | 每个大行程文件夹自动生成行程摘要 |
| 操作记录页面（HistoryPage）| ✅ | 侧边栏「📋 操作记录」 |
| **best_location_label** | ✅ | 归档命名优先级：POI > 乡镇 > 区县 > 城市 |
| **子行程命名改进** | ✅ | 单日：`01_北极镇_0201`；多日：`05_延边_0205-0206` |
| **大行程命名新格式** | ✅ | `{year}_{省市}_{天数}天_{MMDD}-{MMDD}`（智能省市拼接+截断） |
| **备注模板更新** | ✅ | 默认：`地点: {province}/{city}/{township}/{poi}` |
| GPS-less 文件时间推断 | ✅ | ±2h内有GPS文件则自动推断位置 |
| 国内/境外/混合行程类型 | ✅ | 选择类型 + 异常文件路由到 `_待手动整理/` |
| 子行程缩略图预览 | ✅ | Grid 4列预览 + 在资源管理器中显示 |
| POI 候选列表 | ✅ | 点击编辑时显示附近5个候选（一键选择） |
| POI 类型标签 | ✅ | 风景名胜/热点地标/自然地名/公园/文化场馆/火车站 等 |
| force_repoi 补充 POI | ✅ | 独立工具栏始终可见，自动在地理编码后触发 |
| 归档后删除原文件 | ✅ | 复选框 + 二次确认弹窗 + 自动 cleanup |
| POI 审核复制文件名 | ✅ | 浏览器模式下可复制代表性文件名 |
| mutagen + httpx 安装 | ✅ | 视频时间戳 + 高德API 依赖 |

---

## 开发环境启动

```powershell
# 后端（终端1）
cd C:\Dev\trip-trace\backend
.venv\Scripts\python.exe uvicorn_config.py

# 前端（终端2）
cd C:\Dev\trip-trace\frontend
npm run dev:renderer   # http://localhost:5173/
```

**注意**：
- 每次重启后端后，先等待 `Application startup complete.` 再操作
- 前端若提示「后端服务未连接」是**正常**的，需要先启动后端
- `npm run dev:renderer` = 只启 Vite+React（不启 Electron），浏览器直接访问即可调试

---

## 测试步骤（分步执行，避免超时）

```powershell
# 高德 API 地理编码测试（关键！需等待约60秒）
# Step 1: 清空并扫描
Invoke-WebRequest -Uri "http://localhost:17890/api/scan/clear" -Method DELETE | Out-Null
$b = '{"folder_path":"C:\\Users\\Microsoft\\Desktop\\我的不动产\\Eva\\相册工具\\测试文件夹（东北）","options":{}}'
Invoke-WebRequest -Uri "http://localhost:17890/api/scan" -Method POST -ContentType "application/json" -Body $b | Out-Null
Write-Host "扫描完成，等待..."

# Step 2: 地理编码（单独运行，超时设180秒）
$r = Invoke-WebRequest -Uri "http://localhost:17890/api/scan/geocode" -Method POST -TimeoutSec 180
$r.Content | ConvertFrom-Json

# Step 3: 查看地理编码分组（验证 township 效果）
$r = Invoke-WebRequest -Uri "http://localhost:17890/api/scan/geocoded"
($r.Content | ConvertFrom-Json).data.groups | Format-Table province, city, poi, file_count

# Step 4: 归档预览（验证子行程命名）
$b2 = '{"folder_path":"C:\\Users\\Microsoft\\Desktop\\我的不动产\\Eva\\相册工具\\测试文件夹（东北）","output_path":"X:\\test","options":{"big_trip_threshold_days":30,"small_trip_threshold_hours":2.0}}'
$r = Invoke-WebRequest -Uri "http://localhost:17890/api/archive/preview" -Method POST -ContentType "application/json" -Body $b2
$data = ($r.Content | ConvertFrom-Json).data
foreach ($big in $data.trips_structure) {
    Write-Host "📁 $($big.folder)"
    foreach ($sub in $big.sub_trips) { Write-Host "   $($sub.folder) - $($sub.location)" }
}
```

---

## 关键 API 接口（完整列表）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 健康检查 |
| POST | /api/scan | 扫描文件夹（SSE）|
| DELETE | /api/scan/clear | 清空扫描数据 |
| POST | /api/scan/geocode | 逆地理编码（含高德 township+POI；force_repoi=true 可补充 POI）|
| GET | /api/scan/geocoded | POI 分组汇总（审核用）|
| GET | /api/scan/poi-candidates | 按坐标查附近候选 POI（lat/lon 参数）|
| PUT | /api/scan/poi-group | 批量更新 POI 名称 |
| POST | /api/archive/preview | 归档预览 |
| POST | /api/archive/execute | 执行归档（SSE+写日志+生成trip_log.md）|
| POST | /api/archive/cleanup | 删除源文件（confirm=true 才执行）|
| GET | /api/archive/logs | 操作记录列表 |
| GET | /api/map/html | Folium 地图 HTML |
| GET | /api/media/thumbnail | 缩略图 |

---

## 前端页面结构

```
frontend/src/pages/
├── HomePage.tsx           # 主页（后端状态+快速入口）
├── FolderSetup.tsx        # 文件夹选择
├── ScanPage.tsx           # 扫描+地理编码+POI审核+行程树（含缩略图预览）
├── TripRebuilderPage.tsx  # 行程重建（2:1双栏）← 新增
├── ArchivePage.tsx        # 归档预览+执行（含删除原文件选项+归档模式）
├── MapPage.tsx            # 行程地图
├── HistoryPage.tsx        # 操作记录
└── TestConsole.tsx        # 后端测试控制台
```

### 行程重建功能说明（TripRebuilderPage）

用于在子行程上增加额外的"容器"目录层级，适合将同一地区多个 POI 的子行程归到一个父文件夹下。

**输出结构示例**：
```
大行程/
  ├─ 01_哈尔滨_0130/        ← 普通子行程（未放入容器）
  ├─ 漠河之行/              ← 容器层（用户创建）
  │    ├─ 05_漠河最北观景台/ ← 原子行程保留完整
  │    └─ 06_漠河北红村/
  └─ 09_哈尔滨中央大街_0208/
```

**三种归档模式**（必须在行程重建页选择后才能归档）：
- 🌲 `tree`：完全按行程树，忽略容器设置
- 📦 `rebuild`：所有子行程必须分配到容器
- 🔀 `mixed`：容器内按容器层级，未分配按行程树

**状态存储**（Zustand persist）：
- `tripStructure[i].containers?: TripContainer[]` — 每个大行程的容器分组
- `archiveMode: "tree" | "rebuild" | "mixed" | null` — 归档模式

**操作流程**：勾选左侧子行程 → 右侧「移入容器▼」→ 选现有容器或新建 → 选择归档模式 → 前往归档

---

## 重要路径

- 高德 Key：`backend/.env` → `TRIPRACE_GAODE_API_KEY=bc320c4f171b8a2e0bfcb076fb65d2b0`（不要提交 git）
- 测试照片：`C:\Users\Microsoft\Desktop\我的不动产\Eva\相册工具\测试文件夹（东北）`（42个文件）
- 数据库：`C:\Dev\trip-trace\backend\triprace.sqlite`

---

## 架构决策记录

- **用户系统**：当前不建设（YAGNI原则），等有外部用户时再实现
- **API Key安全**：当前 `.env` 存储（个人用），推广时改为云端代理
- **geocode 跳过逻辑**：`city IS NULL` → 跳过（有city=已处理过，有没有POI都不重复调用）
- **GPS 推断**：±2h 内有 GPS 文件 → 自动推断位置（但不写入 GPS 坐标）
- **双层地点策略**：`addressComponent.township`（行政精确）+ POI 搜索（景点名），合并使用
- **行程树状态管理**：Zustand persist（路径/设置/行程树），行程树用户编辑后跨页面保持

---

## 待完成任务

### Phase 4 P2（进行中）
- [ ] UI 体验打磨（空状态、加载动画等）
- [ ] 归档重入保护（目标目录已存在同名文件夹时提示）
- [x] **行程重建功能**：TripRebuilderPage 已实现（2:1布局+容器管理+三种归档模式）
- [ ] **行程重建测试**：用真实数据验证容器路径生成（big/container/sub/file）

### 待验证
- [ ] 用新版代码（2000m半径+township+force_repoi）重跑东北测试集，验证：
  - `IMG_20250201_115322` → **漠河站**（火车站类型）
  - `IMG_20250201_143440` → **北极镇**（township字段）
  - `IMG_20250202_111804` → **龙江第一湾风景区**（2000m半径）

---

## 给新对话的指令模板

```
我在开发名为"旅迹 TripTrace"的 Windows 桌面照片归档工具。
项目在 C:\Dev\trip-trace，GitHub: https://github.com/vera-hlh/trip-trace。

Phase 1~4（P0+P1+行程重建）已完成，详情见 docs/handoff-phase3.md。
最新 commit: feat: 行程重建功能（TripRebuilderPage）+ 归档模式选择（tree/rebuild/mixed）

当前待做：
- Phase 4 P2 收尾：行程重建功能测试（验证 rebuild/mixed 模式容器路径生成）
- UI 体验打磨（空状态、加载动画）
- 归档重入保护

启动环境：
  后端：cd backend && .venv\Scripts\python.exe uvicorn_config.py
  前端：cd frontend && npm run dev:renderer → http://localhost:5173/
  PS执行策略（首次）：Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

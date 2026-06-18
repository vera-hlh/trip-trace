# TripTrace 项目交接文档 - Phase 3+4 完成

> 更新时间：2026-06-18（最新）

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

### ✅ Phase 4 功能强化

| 功能 | 状态 | 说明 |
|---|---|---|
| 跳过已有 city 的文件 | ✅ | `city IS NULL` 才触发地理编码（有city=已处理） |
| 数据库 user_id 字段 | ✅ | 多用户预留，默认 "local" |
| ArchiveLog 操作记录 | ✅ | 每次归档自动写入本地日志 |
| 归档时生成 trip_log.md | ✅ | 每个大行程文件夹自动生成行程摘要 |
| 操作记录页面（HistoryPage）| ✅ | 侧边栏「📋 操作记录」 |
| **best_location_label** | ✅ | 归档命名优先级：POI > 乡镇 > 区县 > 城市 |
| **子行程命名改进** | ✅ | 单日：`01_北极镇_0201`；多日：`05_延边_0205-0206` |
| **备注模板更新** | ✅ | 默认：`地点: {province}/{city}/{township}/{poi}` |
| GPS-less 文件时间推断 | ✅ | ±2h内有GPS文件则自动推断位置 |
| mutagen + httpx 安装 | ✅ | 视频时间戳 + 高德API 依赖 |

---

## ⚠️ 待验证问题（上次测试被中断）

### 1. POI 地址精确度（需重新测试验证效果）

上次因超时中断，**地理编码还未用新版代码（2000m半径+township）跑过**。需要：
1. 清空旧数据：`DELETE /api/scan/clear`
2. 重新扫描：`POST /api/scan`
3. 重新地理编码：`POST /api/scan/geocode`（**单独运行，等60秒**）
4. 查看归档预览：`POST /api/archive/preview`

期望改进效果对照（用户提供的期望）：
- `IMG_20250201_115322/120328` → **漠河站**（新加 150200 火车站类型）
- `IMG_20250201_143440` → 漠河市 **北极镇**（新加 township 字段）
- `IMG_20250202_111804` → **龙江第一湾风景区**（110200 风景名胜，2000m半径）

### 2. 大行程文件夹命名（⚠️ 未实现）

用户期望格式：`{年份}_{省份+城市}_{天数}天_{MMDD}-{MMDD}`

例：`2025_黑龙江大兴安岭·吉林延边_10天_0130-0208`

**当前格式仍是**：`2025-01_大兴安岭地区之旅`

**待实现**：修改 `archive_service.py` 中 `BigTrip.folder_name` 属性，从 sub_trips.items 收集 province+city 信息组成摘要。

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

**注意**：每次重启后端后，先等待 `Application startup complete.` 再操作。

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
| POST | /api/scan/geocode | 逆地理编码（含高德 township+POI）|
| GET | /api/scan/geocoded | POI 分组汇总（审核用）|
| PUT | /api/scan/poi-group | 批量更新 POI 名称 |
| POST | /api/archive/preview | 归档预览 |
| POST | /api/archive/execute | 执行归档（SSE+写日志+生成trip_log.md）|
| GET | /api/archive/logs | 操作记录列表 |
| GET | /api/map/html | Folium 地图 HTML |
| GET | /api/media/thumbnail | 缩略图 |

---

## 前端页面结构

```
frontend/src/pages/
├── HomePage.tsx        # 主页（后端状态+快速入口）
├── FolderSetup.tsx     # 文件夹选择
├── ScanPage.tsx        # 扫描+地理编码+POI审核+行程树
├── ArchivePage.tsx     # 归档预览+执行
├── MapPage.tsx         # 行程地图
├── HistoryPage.tsx     # 操作记录 ← 新增
└── TestConsole.tsx     # 后端测试控制台
```

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

---

## 待完成任务

### P0（立即可做）
- [ ] **大行程文件夹命名**：改为 `{year}_{province+city}_{days}天_{MMDD}-{MMDD}` 格式
  - 修改 `backend/app/services/archive_service.py` 的 `BigTrip.folder_name` 属性
  - 需从 sub_trips.items 收集 province、city、country 信息

### P1（近期）
- [ ] 验证新地理编码效果（重跑测试，看漠河站/北极镇是否正确识别）
- [ ] UI 体验打磨（空状态、加载动画等）

---

## 给新对话的指令模板

```
我在开发名为"旅迹 TripTrace"的 Windows 桌面照片归档工具。
项目在 C:\Dev\trip-trace，GitHub: https://github.com/vera-hlh/trip-trace。

Phase 1~4 已完成，详情见 docs/handoff-phase3.md。
最新 commit: 9b53176（township双层地点策略+best_location_label）

当前待做：
1. 大行程文件夹命名格式改进（{year}_{省市}_{天数}天_{MMDD}-{MMDD}）
   - 修改 backend/app/services/archive_service.py 的 BigTrip.folder_name 属性
   - 需从 sub_trips.items 收集所有文件的 province/city/country 汇总
2. 重新运行测试流程验证 township 效果（分步执行避免超时）
```

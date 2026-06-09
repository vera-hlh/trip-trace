# TripTrace 技术架构文档

> 版本：v1.0 | 最后更新：2026-06-09

---

## 一、项目概述

**项目名称**：旅迹 · TripTrace  
**目标平台**：Windows 桌面应用（Windows 10/11）  
**架构模式**：Electron（桌面容器）+ React（前端 UI）+ Python FastAPI（业务后端）  

### 核心功能矩阵

| 功能模块 | 说明 |
|---|---|
| 元数据提取 | 读取照片/视频的拍摄时间与 GPS 坐标 |
| 逆地理编码 | GPS 坐标 → 结构化地址（国家/省/市/景点） |
| 智能归档 | 按行程切分/合并文件，支持地点回归检测 |
| 备注写入 | 仅将地址信息写入文件的"备注"字段 |
| 交互式地图 | 生成路径 HTML，热点可点击查看照片 |
| MP4 导出 | 基于同数据源生成可分享的路径短视频 |
| 安全操作 | 复制优先 + 预览确认 + 撤销机制 |

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Electron 主进程                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │            React 渲染进程 (WebContents)             │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │ 文件夹选择  │  │  归档预览  │  │   地图/视频展示   │  │  │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
│                    IPC / HTTP (localhost:17890)            │
│  ┌────────────────────────────────────────────────────┐  │
│  │           Python FastAPI 子进程                     │  │
│  │  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐  │  │
│  │  │元数据提取 │ │逆地理编码 │ │智能归档 │ │视频生成  │  │  │
│  │  └─────────┘ └──────────┘ └────────┘ └─────────┘  │  │
│  │                     SQLite                          │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 三、技术选型

### 3.1 桌面框架：Electron

**选择理由**：
- 前端技术（React/TypeScript）可直接复用，开发效率高
- 内置 `WebContents` 支持完整 Chromium，可完美渲染 Folium 生成的 HTML 交互地图
- 与 Python 子进程通信成熟稳定（HTTP 本地服务）
- 社区生态丰富，AI 辅助代码质量高

### 3.2 前端：React + TypeScript + Tailwind CSS

- React 18：组件化 UI
- TypeScript：类型安全
- Tailwind CSS：快速样式
- Vite：快速构建

### 3.3 后端：Python 3.10+ + FastAPI

**选择理由**：
- Python 生态对媒体处理（PIL/ffmpeg/mutagen）支持最成熟
- FastAPI 高性能、自带 OpenAPI 文档、异步支持
- 与 Electron 通过 HTTP 解耦，便于独立测试

### 3.4 逆地理编码策略（三层优化方案）

| 优先级 | 方案 | 适用场景 | 特点 |
|---|---|---|---|
| 1（离线快速）| `reverse_geocoder` | 国际通用 | 全球覆盖，速度极快，提供国家/省市 |
| 1（离线精准）| `fast-geocn` | 中国行政区划 | 中文地名，精度高于国际方案 |
| 2（在线增强）| 高德地图 API | 需要景点 POI | 提供景点名称，**按就近聚类懒加载调用** |

**三层调用策略（POI 聚类优化方案）：**

```
第一层：网格缓存快查
  → 将 (lat, lon) 截断至小数点后 3 位（约 100m 网格）作为 key
  → 命中缓存 → 直接返回，0 次 API 调用

第二层：POI 聚类中心距离判定
  → 计算照片坐标与"当前活跃 POI 聚类中心"的距离
  → 距离 ≤ 500m 且 时间差 ≤ 行程切分阈值（默认 2h）→ 归入当前 POI，无需 API
  → 否则 → 进入第三层

第三层：高德 API 按需查询
  → 仅在切换景点时触发，结果同时更新网格缓存 + POI 聚类
  → 典型结果：1000 张照片只需 5-10 次 API 调用（取决于景点数量）
```

**POI 聚类中心动态更新**：每加入一张新照片，以加权平均更新聚类中心坐标（而非固定为第一张照片的坐标）

**注意**：`fast-geocn` 仅支持中国行政区划，国际坐标自动降级到 `reverse_geocoder`

### 3.5 数据库：SQLite + SQLAlchemy

- 嵌入式，零配置，随应用分发
- SQLAlchemy ORM 便于模型管理
- 每个项目（旅行文件夹）使用独立 SQLite 文件

---

## 四、模块详细说明

### 4.1 元数据提取模块

**职责**：读取照片/视频的拍摄时间和 GPS 坐标

**照片**（`PIL` + `piexif`）：
- 读取 EXIF `DateTimeOriginal` 作为拍摄时间
- 读取 EXIF `GPSInfo` 并转换为十进制坐标
- 注意：`DateTime`（修改时间）与 `DateTimeOriginal`（拍摄时间）不同，必须使用后者

**视频**（`mutagen` + `ffmpeg-python`）：
- MP4/MOV：读取 `©day` 标签或 `creation_time`
- **重要**：视频 `creation_time` 为 UTC 时间，需根据 GPS 坐标或用户设置的时区转换为本地时间（中国 +8h）
- 部分 iPhone 视频的 GPS 存储在 `com.apple.quicktime.location.ISO6709` 标签

**无 GPS 文件的处理策略**：
- 有时间无 GPS → 按拍摄时间归入最近的行程，展示"位置待确认"标记
- 无时间无 GPS → 归入"待分类"文件夹
- 截图、编辑图等无 EXIF 文件 → 自动识别并单独处理

### 4.2 逆地理编码模块

见 3.4 节技术选型。

**缓存机制**：
- 将（lat, lon）精度截断至小数点后 3 位（约 100m 精度）作为缓存 key
- 缓存存入 SQLite 的 `geocode_cache` 表
- 避免对附近位置的重复查询

### 4.3 智能归档算法

**行程切分规则**（优先级从高到低）：

1. **大行程边界**：两文件时间间隔 > 30 天（可配置）→ 强制切分
2. **小行程切分**：地点变化 **且** 时间间隔 > 2 小时（可配置）→ 切分
3. **同地点合并**：地点不变 → 无论时间间隔多长都合并（出差在家多天拍照）
4. **GPS 漂移过滤**：地点变化但时间间隔 < 2 小时 → 视为 GPS 漂移，合并

**地点定义**：
- 国内：以"市"级为行程切分单位（如昆明市、大理市）
- 特殊：如用户开启景点模式，以景点名为单位（石林、苍山洱海）

**地点回归处理**：
- A→B→A 模式：第二次出现 A 时，因地点不等于前一地点 B，且时间差通常 > 2h，自然切分出新行程
- 无需额外代码，算法自动处理

**文件夹命名规范**：
```
大行程：YYYY-MM_行程名
  例：2025-09_云南之旅

子行程：序号_地点名_MMDD-MMDD
  例：01_昆明_0910-0913
      02_大理_0913-0915
      05_昆明_0919-0920  ← 地点回归，独立序号
```

### 4.4 备注写入模块

**重要原则**：只写备注字段，不修改任何其他元数据（特别是拍摄时间）

**照片写入**（`piexif` 写 `XMP:Description` 和 `EXIF:UserComment`）：

```python
# 正确的 UserComment 编码（支持中文）
# 使用 undefined 编码头（8 个 0 字节）+ UTF-8 内容
encoded_remark = b"\x00\x00\x00\x00\x00\x00\x00\x00" + remark_text.encode('utf-8')
exif_dict['Exif'][piexif.ExifIFD.UserComment] = encoded_remark
```

备注格式约定：
```
地点: 中国/云南省/昆明市/石林风景区
行程: 2025-09_云南之旅 > 01_昆明_0910-0913
```

**视频写入**（`mutagen` 写 `©cmt`）：
```python
video = MP4(file_path)
video['©cmt'] = [remark_text]
video.save()
```

**手机可读性**：
- iPhone 相册：读取 `EXIF UserComment` 和 `XMP:Description`，均支持
- Android 相册：大部分支持 `XMP:Description`

### 4.5 文件安全保障机制

**操作流程**：
```
用户触发归档
    ↓
「预览模式」：生成归档计划（仅展示，不执行）
    ↓
用户审查 + 手动调整（合并/拆分行程）
    ↓
用户确认 → 执行「复制」操作（不删除原文件）
    ↓
归档完成 → 展示结果，询问"是否删除原文件"
    ↓
用户选择保留原文件 或 移入回收站
```

**操作日志**：
- 每次操作记录到 `user_adjustments` 表
- 支持导出操作报告（CSV/TXT）

### 4.6 交互式地图展示

**技术方案**：`Folium` 生成 HTML + Electron `WebContents` 内嵌展示

**功能说明**：
- 地图底图：OpenStreetMap（默认）/ 高德地图（可选）
- 路径动画：折线绘制行程路径，支持动画回放
- 热点标记：每个行程地点有可点击标记
- 热点弹窗：点击后展示该地点的缩略图轮播

**本地图片服务**：
- FastAPI 提供 `/media/thumbnail` 端点
- Electron 通过 `http://localhost:17890/media/thumbnail?path=...` 获取图片
- 支持自动压缩（宽度 ≤ 800px，JPEG 质量 75）

### 4.7 MP4 视频导出

**技术方案**：`moviepy` + 地图截图序列

**生成流程**：
```
从 SQLite 读取行程数据
    ↓
生成地图路径动画帧序列（folium → 截图）
    ↓
对每个热点：获取代表照片（最多 5 张）→ 生成照片轮播片段
    ↓
拼接：标题片段 + 路径动画 + 各地点轮播片段
    ↓
ffmpeg 合成输出 MP4（可选：添加背景音乐）
```

**与 HTML 方案的关系**：
- 两者共享同一数据源（SQLite）
- HTML 和 MP4 均可独立生成，互不依赖
- 生成 MP4 时复用 HTML 热点的图片列表数据

---

## 五、数据库设计

### 5.1 表结构

```sql
-- 媒体文件元数据
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT UNIQUE NOT NULL,
    current_path TEXT,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,          -- 'photo' | 'video'
    datetime_original TEXT,           -- ISO8601 格式，本地时间
    latitude REAL,
    longitude REAL,
    country TEXT,
    province TEXT,
    city TEXT,
    district TEXT,
    poi TEXT,                         -- 景点名称（在线模式）
    remark_written BOOLEAN DEFAULT 0,
    trip_id INTEGER,
    has_gps BOOLEAN DEFAULT 0,
    needs_review BOOLEAN DEFAULT 0,   -- 无 GPS / 无时间文件标记
    FOREIGN KEY(trip_id) REFERENCES trips(id)
);

-- 行程信息
CREATE TABLE trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_name TEXT NOT NULL,          -- 例：01_昆明_0910-0913
    display_name TEXT,                -- 用户自定义名称
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    parent_trip_id INTEGER,           -- 大行程 ID
    sequence_num INTEGER,             -- 子行程序号
    location_label TEXT,              -- 主要地点标签
    user_merged BOOLEAN DEFAULT 0,
    FOREIGN KEY(parent_trip_id) REFERENCES trips(id)
);

-- 逆地理编码缓存（网格快查，第一层缓存）
CREATE TABLE geocode_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lat_key REAL NOT NULL,            -- 精度截断至 3 位小数（约 100m 网格）
    lon_key REAL NOT NULL,
    country TEXT,
    province TEXT,
    city TEXT,
    district TEXT,
    poi TEXT,
    source TEXT,                      -- 'offline' | 'gaode'
    cached_at TEXT,
    UNIQUE(lat_key, lon_key)
);

-- POI 聚类表（第二层缓存，懒加载聚类优化）
-- 每个大行程内按时间+距离双因子聚类出的景点集群
-- API 调用次数 ≈ 景点切换次数，通常远少于照片总数
CREATE TABLE poi_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER,                  -- 关联大行程（同一行程内的 POI）
    poi_name TEXT,                    -- 景点名称（来自高德 API）
    city TEXT,                        -- 所属城市
    center_lat REAL NOT NULL,         -- 聚类中心纬度（加权平均，动态更新）
    center_lon REAL NOT NULL,         -- 聚类中心经度
    radius_m REAL DEFAULT 500,        -- 聚类半径阈值（米）
    file_count INTEGER DEFAULT 0,     -- 归入该 POI 的照片/视频数
    api_call_triggered BOOLEAN DEFAULT 1,  -- 是否触发过 API 查询（监控用）
    created_at TEXT,
    FOREIGN KEY(trip_id) REFERENCES trips(id)
);

-- 用户调整记录（支持撤销）
CREATE TABLE user_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    action TEXT NOT NULL,             -- 'move' | 'copy' | 'merge' | 'split'
    from_path TEXT,
    to_path TEXT,
    from_trip_id INTEGER,
    to_trip_id INTEGER,
    executed BOOLEAN DEFAULT 0,
    executed_at TEXT,
    rolled_back BOOLEAN DEFAULT 0
);
```

---

## 六、API 接口概览

详见 [api-design.md](api-design.md)

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/scan` | 扫描文件夹，提取元数据 |
| GET | `/api/trips` | 获取行程列表 |
| PUT | `/api/trips/{id}` | 修改行程（重命名/合并/拆分） |
| POST | `/api/archive/preview` | 预览归档方案 |
| POST | `/api/archive/execute` | 执行归档（复制模式） |
| POST | `/api/archive/cleanup` | 删除原文件（用户确认后） |
| GET | `/api/map/html/{trip_id}` | 生成交互式 HTML 地图 |
| POST | `/api/video/export` | 导出 MP4 视频 |
| GET | `/api/media/thumbnail` | 获取缩略图 |

---

## 七、前后端通信方案

### Electron 主进程 → Python 后端

```typescript
// Electron 中通过 HTTP 调用后端
const BACKEND_URL = 'http://localhost:17890'

async function callBackend(path: string, options?: RequestInit) {
  const res = await fetch(`${BACKEND_URL}${path}`, options)
  return res.json()
}
```

### Electron IPC（主进程 ↔ 渲染进程）

```typescript
// 主进程：监听文件对话框请求
ipcMain.handle('open-folder-dialog', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory'] })
  return result.filePaths[0]
})

// 渲染进程：调用
const folderPath = await window.electronAPI.openFolderDialog()
```

---

## 八、打包与分发

### 开发环境

1. Python FastAPI 服务：`uvicorn app.main:app --port 17890`
2. Electron + React：`npm run dev`（Vite + Electron）

### 生产打包

```bash
# 1. 打包 Python 后端为 exe
cd backend
pyinstaller --onefile --name trip-trace-backend main.py

# 2. 打包 Electron + React
cd frontend
npm run build
npm run package  # electron-builder
```

打包后目录结构：
```
dist/
  TripTrace Setup 1.0.0.exe   # 安装包
  win-unpacked/
    TripTrace.exe              # 主程序
    resources/
      backend/
        trip-trace-backend.exe # Python 后端
```

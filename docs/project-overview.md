# 旅迹 TripTrace · 项目总览与续做交接

> 本文档为项目**单一权威总览**，整合了原本分散在 `roadmap.md`、`handoff-phase3.md`、
> `phase2-plan.md`、`architecture.md`、`api-design.md`、`v1-delivery-plan.md`
> 以及 `CHANGELOG.md` 中的信息，供搁置后重新续做时快速掌握全貌。
>
> - 生成日期：2026-11-08
> - 代码基线：`37a792d`（`feat: 我的旅迹 - 阶段一`，已推送 origin/main）
> - 维护建议：本文件随里程碑推进更新；细节设计仍以各专项文档为准。

---

## 1. 项目目的

**旅迹（TripTrace）** 是一个 **Windows 桌面照片/视频归档工具**，解决的核心痛点是：

> 一次旅行结束，相机卡/手机里几百上千张照片混在一起，想按「行程 → 地点 → 景点」整理成有序文件夹、并让照片自带地点备注，手工做极其耗时。

TripTrace 的完整价值链路：

1. **扫描**：递归扫描指定文件夹，提取每个媒体文件的拍摄时间与 GPS 坐标。
2. **地理编码**：把 GPS 反查为「国家/省/市/区/乡镇/POI 景点」，中文地名走高德 API，境外走离线库。
3. **行程切分**：按时间间隔与地点变化，把文件自动切分成「大行程 → 子行程」树。
4. **人工校正**：用户在界面上重命名、合并子行程、审核 POI、创建容器、合并大行程。
5. **归档**：按确认后的方案复制文件到目标目录树，并可选地把地点写回照片 EXIF 备注、生成 `trip_log.md`。
6. **回看**：行程地图（Folium）、操作记录、「我的旅迹」海报列表。

**目标用户**：普通旅行者（非技术用户）—— 因此 v1.0 的完成定义是
「一个没有 Python/Node 环境的 Windows 用户，能安装、扫描、预览、调整、归档、看地图、查记录，卸载重装不丢数据」。

---

## 2. 技术架构

| 层 | 技术选型 | 说明 |
|---|---|---|
| 后端 | Python + FastAPI + Uvicorn | 监听 `127.0.0.1:17890`，本地单机服务 |
| 数据 | SQLite（SQLAlchemy async + aiosqlite） | 单文件 `triprace.sqlite`，启动时 `create_all` + 幂等 `ALTER TABLE` 迁移 |
| 媒体 | Pillow / mutagen | 缩略图生成、EXIF/视频元数据读写 |
| 地理 | reverse_geocoder / timezonefinder / 高德 API | 离线优先 + 在线增强 |
| 地图 | Folium | 生成 HTML 地图，前端 iframe 嵌入 |
| 前端 | React + TypeScript + Vite + TailwindCSS + Zustand | 单页应用；`127.0.0.1:5173`（dev） |
| 桌面 | Electron | 生产模式 `loadFile` 加载打包后的前端，拉起后端 |

**代码布局**

```
backend/
  app/
    api/        接口层：health, scan, trips, archive, map_routes, media, video, config, trip_records
    core/       database.py（引擎/会话/迁移）、config.py（settings 读 .env）
    models/     file.py, trip.py, cache.py, archive_log.py, trip_record.py
    services/   metadata_service, geocode_service, archive_service, remark_service, map_service, video_service, timezone_utils
    main.py     应用入口 + 路由注册
  tests/        单元测试
frontend/
  src/
    pages/      HomePage, FolderSetup, ScanPage, TripRebuilderPage, ArchivePage, MapPage, MyTripsPage, HistoryPage, TestConsole
    components/ Layout（侧栏导航）等
    store/      appStore.ts（Zustand，持久化）
    api/        backend.ts
  electron/     主进程
scripts/start-dev.ps1   开发一键启动（清端口 + 独立窗口显示前端错误）
docs/                   设计文档
```

**启动命令（开发）**

- 后端：`cd backend && uvicorn app.main:app --reload --port 17890`（或用 `scripts/start-dev.ps1`）
- 前端渲染进程：`cd frontend && npm run dev:renderer`
- 桌面整体：`scripts/start-dev.ps1`

**关键配置**：高德 Key 只放在 `backend/.env` 的 `TRIPRACE_GAODE_API_KEY`，不入库、不进文档（见 §7 安全事项）。

---

## 3. 实施进度

> 版本号与 `CHANGELOG.md` 对齐；「实际完成」以代码为准，不以计划为准。

### 3.1 已完成阶段

| 阶段 | 版本 | 内容 | 状态 |
|---|---|---|---|
| Phase 1 | v0.1.0 | 项目脚手架、基础架构、`/health`、双端目录结构 | ✅ 完成 |
| Phase 2 | v0.3.0 | 元数据提取、数据库、三层逆地理编码、归档切分算法、文件操作 + 备注写入 | ✅ 完成（90/90 单测） |
| Phase 3 | v0.6.0 / v0.7.0 | 前端完整 UI（React+Electron）；高德 API + POI 集成 | ✅ 完成 |
| Phase 4 | v0.8.0 | 功能强化（见下） | ✅ 基本完成 |
| Phase 5（未编号） | 未发版 | POI 审核 UI 优化、缩略图修复、行程重建、大行程合并、**我的旅迹（阶段一）** | 🔄 进行中 |

### 3.2 Phase 2 关键成果（v0.3.0）

- `metadata_service.py`：照片 EXIF、视频 ISO 6709 GPS 提取；`scan_folder()` 递归扫描。
- `timezone_utils.py`：UTC → 本地时间（基于 GPS 查时区）。
- `geocode_service.py`：**三层逆地理编码优化**
  - 第一层：网格缓存（lat/lon 截断 3 位 ≈ 100m 精度），命中即 0 调用；
  - 第二层：POI 聚类懒加载（距离 ≤ 500m 且时间差 ≤ 2h 归同一 POI）；
  - 第三层：高德 API 在线增强（仅切换景点时触发；典型 1000 张照片仅 5–10 次调用）。
- `archive_service.py`：行程切分核心（大行程边界 30 天 / 小行程地点变化+2h / 同地点合并 / GPS 漂移过滤 / A→B→A 地点回归检测）。
- `remark_service.py`：EXIF UserComment（8 字节 null 头 + UTF-8，支持中文）+ ImageDescription；视频 mutagen 标签。
- `file_utils.py`：安全复制/重命名冲突处理。

### 3.3 Phase 3 关键成果（v0.6.0 / v0.7.0）

- 前端完整 UI：HomePage / FolderSetup / ScanPage（三步工作流 + SSE 进度）/ ArchivePage / MapPage（Folium）/ TestConsole / Layout 侧栏；Zustand 持久化。
- 高德 API 接入 + POI 旅行类型过滤（13 种相关类型，含火车站、乡镇，按优先级排序）。
- **坐标系修复**：`coordsys=gps` + EXIF `GPSMapDatum` 检测 + GCJ-02 → WGS-84 逆转换。
- `township` 乡镇字段（高德 `addressComponent.township`，精确行政区划，不依赖搜索半径）。
- POI 审核 UI：地理编码后自动加载可编辑 POI 分组。

### 3.4 Phase 4 关键成果（v0.8.0）

- `best_location_label`：归档命名优先级 **POI > 乡镇 > 区县 > 城市**。
- 命名改进：子行程 `01_北极镇_0201` / `05_延边_0205-0206`；大行程 `{year}_{省市}_{天数}天_{MMDD}-{MMDD}`。
- `ArchiveLog` 模型 + 每次归档自动写入 + **操作记录页（HistoryPage）**。
- 归档自动生成 `trip_log.md`（行程摘要）。
- GPS-less 文件时间推断（±2h 内有 GPS 文件则推断其位置）。
- 国内/境外/混合行程类型 + 异常文件路由到 `_待手动整理/`。
- 子行程缩略图预览、POI 候选列表、POI 类型标签、`force_repoi` 补充 POI。
- 归档后删除原文件选项（复选框 + 二次确认 + 自动 cleanup）。
- 数据库 `user_id` 字段（多用户预留，默认 `"local"`）。

### 3.5 Phase 5（续做中，未发版）关键成果

自 v0.8.0 以来（对应 git 提交）：

- **POI 审核 UI 多轮打磨**：按最早拍摄时间排序（与行程顺序一致）、缩略图方向校正（`ImageOps.exif_transpose`）、整行点击合并展开「候选 POI + 缩略图 + 日期」、展开行高亮、文件数定宽对齐、详情/复制等交互调整。
- **修复核心 bug**：POI 聚类命中丢失 `province/district/township` 字段，导致同一 POI 被拆成多条记录。
- **扫描透明度**：`scan_folder()` 返回 `(files, skipped_dirs)`，界面提示因权限跳过的目录数。
- **行程重建**：容器分组（用户自定义额外目录层）、三种归档模式（tree/rebuild/mixed）、**大行程合并**。
- **我的旅迹（阶段一，最新）**：见 §3.6。

### 3.6 「我的旅迹」阶段一（`37a792d`，最新）

- 新增 `TripRecord` 模型：每条 = 一个已归档大行程（含子行程 JSON 快照，防止 DB 清空后无法回溯）。
- 归档执行时自动写入 `TripRecord`。
- 新增接口（`trip_records.py`）：分页列表 / 最近 N 条 / 单条详情。
- 前端：侧栏「我的旅迹」菜单、HomePage 预览版块（最新 5 条 + 进入按钮）、`MyTripsPage`（左宽右窄两列 + 分页 + 排序）。
- **阶段二（海报生成）尚未实现**：`poster_path` 字段目前为空，右侧海报区为占位。

### 3.7 未完成 / 待办（摘要，详见 `v1-delivery-plan.md`）

- 「我的旅迹」阶段二：静态行程海报生成（用户已选定方案 A = Pillow 手绘）。
- v1.0 交付计划 M0–M7 中的大部分尚未动工（安全止血、基线恢复、方案持久化、打包上线等）。
- 视频导出（`/video/export`）标为 v1.1。

---

## 4. 与原计划的偏离说明（缘由与结论）

> 本节回答「当时为什么没按原计划做」，避免续做时被旧文档误导。

### 4.1 路线图存在两套，需以 `v1-delivery-plan.md` 为准

- `roadmap.md`（v2.0）用 **Phase 1–7** 编号，且已停在「Phase 4 进行中」。
- 实际开发中又出现了「Phase 4 P0/P1/P2」与「未编号 Phase 5」的混用（见 `handoff-phase3.md`）。
- 搁置后制定的 `v1-delivery-plan.md` 改用 **M0–M7 里程碑**，并明确「先止血 → 恢复基线 → 决策架构 → 上线」。
- **结论**：`roadmap.md` 的 Phase 5/6/7 仅作历史参考；**当前唯一权威计划是 `v1-delivery-plan.md` 的 M0–M7**。Phase 5「多用户 SaaS」、Phase 6「视频生成」均已被重新定位（见 4.4 / 4.5）。

### 4.2 行程数据模型：从「持久化 Trip 表」改为「即席计算 + 前端持久化」

- **原设计**（`api-design.md`）：`/api/trips` 提供行程 CRUD（GET / PUT 重命名 / POST merge / POST split），对应 `models/trip.py` 的 `Trip` 表。
- **实际实现**：行程树由 `/api/archive/preview` **即席计算**返回；用户在界面上的重命名/合并/容器分组保存在**前端 Zustand（persist → localStorage）**；归档时一次性落盘到磁盘目录树。
- **结果**：`Trip` 表从未被写入，`/api/trips` 系列成为**死接口**（详见 §5.4）。
- **缘由**：单人本地工具，行程是「归档前的一次性预览」，无需把中间态持久化进数据库；前端持久化已满足「跨页面保持编辑」的需求。
- **结论**：`/api/trips` 应删除（`v1-delivery-plan.md §10` 已拍板「删除，只保留 plan 体系」）。「已归档行程的持久化」需求后来由 `TripRecord` + `/api/trips/records` 承接。

### 4.3 「我的旅迹」属需求新增，不在任何原路线图中

- 该功能来自 2026-07 的用户反馈（主页增加「旅迹记录」版块），**原 `roadmap.md` 完全没有**。
- 已实施「阶段一」（数据模型 + 列表 + 分页 + 排序），「阶段二」（静态行程海报）为待办。
- **结论**：续做时把它当作独立里程碑维护，不要硬塞进旧 Phase 体系。

### 4.4 多用户 / SaaS（原 Phase 5）继续搁置

- 原计划「有第 1 个真实外部用户时触发」（YAGNI）；`v1-delivery-plan.md §10` 重申「继续搁置」。
- 数据库已预留 `user_id`（默认 `"local"`），后端接口未启用鉴权。

### 4.5 视频生成（原 Phase 6 / v0.9.0）推迟到 v1.1

- 原计划 Phase 6 完成即发 v0.9.0；`v1-delivery-plan.md §10` 决定 **v1.0 不含 MP4 导出**。
- 缘由：视频管线（Playwright 截图 + moviepy + ffmpeg）约 7–10 人日，且显著增加打包体积与失败面；核心价值是归档。
- 现状：`/api/video/export` 接口存在但未打磨，前端未接入。

### 4.6 归档方向：从「按 Trip 持久化方案」改为「按 preview 结果直接执行」

- 与 4.2 同源：归档不再依赖数据库里的 Trip 记录，而是把 preview 返回的树 + 前端编辑（重命名/容器/模式）**整体回传给 `/api/archive/execute`**。
- 副作用：**方案未落盘**（刷新或换机器会丢编辑）——这正是 `v1-delivery-plan.md` M2「归档方案持久化」要解决的核心问题。

### 4.7 扫描接口返回值变更（影响测试）

- `scan_folder()` 由 `list[str]` 改为 `tuple[list[str], list[str]]`（返回媒体文件 + 因权限跳过的目录）。
- 旧测试 `tests/test_metadata.py` 仍按旧签名断言，会在 M1「基线恢复」中修复。

---

## 5. 接口功能说明

> 以**代码实际注册的路由**为准（`backend/app/main.py`）。基础地址 `http://localhost:17890`。

### 5.1 系统 / 配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查，返回 `{status, version}`；前端据此显示后端连接状态 |

### 5.2 扫描 + 地理编码（`scan.py`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/scan` | 扫描文件夹，提取元数据入库；**SSE 流式**返回进度（progress/complete，含 `skipped_dirs`） |
| GET | `/api/scan/status` | 当前库内统计（总数/有 GPS/无 GPS/待审核/视频/照片） |
| POST | `/api/scan/geocode` | 逆地理编码（GPS→地名）；`force_repoi=true` 时只补「已有城市但无 POI」的文件 |
| GET | `/api/scan/geocoded` | POI 分组汇总（审核用），按 `(province, city, poi)` 分组，附代表文件与缩略图列表 |
| GET | `/api/scan/poi-candidates` | 按 `lat/lon` 查高德附近候选 POI（前端编辑 POI 时按需加载） |
| PUT | `/api/scan/poi-group` | 批量把某组文件的 POI 改为指定名称 |
| DELETE | `/api/scan/clear` | 清空扫描数据（重新扫描前用） |

### 5.3 归档（`archive.py`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/archive/preview` | 预览归档方案（不落盘）；返回大/子行程树结构，供前端编辑 |
| POST | `/api/archive/execute` | 执行归档（**SSE 进度**）；支持重命名覆盖、容器、归档模式(tree/rebuild/mixed)、删除原文件、生成 `trip_log.md`，**并写入 `TripRecord`** |
| GET | `/api/archive/logs` | 归档操作日志列表（HistoryPage 用，来自 `ArchiveLog`） |
| POST | `/api/archive/write-remarks` | 为已归档文件写回 EXIF 备注 |
| POST | `/api/archive/cleanup` | 删除源文件（需 `confirm=true`，二次确认后调用） |

### 5.4 「我的旅迹」记录（`trip_records.py`）—— 活跃；与死接口 `trips.py` 区分

**活跃接口（供「我的旅迹」使用）：**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/trips/records` | 分页获取已归档大行程记录；`page`/`page_size`/`sort`（4 种排序） |
| GET | `/api/trips/records/recent` | 最近 N 条（主页预览，按生成时间倒序） |
| GET | `/api/trips/records/{record_id}` | 单条详情（含子行程 JSON 快照，供海报用） |

**🔴 死接口（`trips.py`，建议删除）：**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/trips` | 读取 `Trip` 表行程列表 |
| PUT | `/api/trips/{trip_id}` | 重命名行程 |
| POST | `/api/trips/merge` | 合并子行程 |

> **`/api/trips` 是什么？为什么是死接口？**
> 它是项目早期（Phase 1 脚手架阶段）按 `api-design.md` 设计的**行程持久化 CRUD** 接口，预期把行程树存进 `Trip` 表。
> 但实际方案改为「preview 即席计算 + 前端 Zustand 持久化」（见 §4.2），**`Trip` 表从未被写入过任何一行**，因此这三个接口查出来的永远是空列表。
> 前端仅在 `frontend/src/api/backend.ts:9` 残留一处未被调用的 `fetch('/api/trips')`。
> **处置**：删除 `trips.py`、`models/trip.py`、main.py 中的注册，以及 `backend.ts` 的残留函数（`v1-delivery-plan.md §10`）。

### 5.5 地图（`map_routes.py`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/map/html` | 生成 Folium 交互地图 HTML（前端 `iframe srcdoc` 嵌入） |
| GET | `/api/map/photos` | 地图热点点击后取该城市/省份的照片列表 |

> 注：`api-design.md` 里的 `/api/map/html/{parent_trip_id}`、`/api/map/locations/{parent_trip_id}` 是**旧设计**，实际已简化为按 `folder_path` 过滤。

### 5.6 媒体（`media.py`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/media/thumbnail` | 缩略图（JPEG）；`path`/`width`/`quality`；**已做 `ImageOps.exif_transpose` 方向校正** |
| GET | `/api/media/info` | 单文件元数据 |

### 5.7 视频（`video.py`）与配置（`config.py`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/video/export` | 导出 MP4（SSE）；**未打磨，v1.0 不纳入**（见 §4.5） |
| GET | `/api/config` | 读取配置 |

> 注：`api-design.md` 里的 `PUT /api/config`、`/api/scan/split` 等未实现，属旧设计残留。

---

## 6. 计划（当前唯一权威：`v1-delivery-plan.md`）

> **v1.0 完成定义**：一个没有 Python/Node 环境的 Windows 10/11 用户，能安装、扫描、预览、调整、归档、看地图、查记录，卸载重装不丢数据。
> 基线 `37a792d`；预计全职 7–9 周，业余每晚 2 小时约 3–4 个月。

| 里程碑 | 内容 | 工期 | 退出条件 |
|---|---|---|---|
| M0 | 安全止血 | 1 天 | 仓库与历史中无有效凭据；有 LICENSE；基线 tag |
| M1 | 基线恢复 | 3 天 | 全新环境可安装；pytest/tsc/build 全绿；CI 生效 |
| M2 | 归档方案持久化 | 8 天 | 界面编辑 100% 落到磁盘；方案可重放 |
| M3 | 文件安全与一致性 | 4 天 | 重名不丢文件；删除可恢复；路径不可逃逸 |
| M4 | 地理编码与媒体兼容 | 5 天 | 境外不误判中国；HEIC/视频时间正确 |
| M5 | 性能与体验 | 4 天 | 5000 文件不卡死；无 N+1；前端可维护 |
| M6 | 验证 | 5 天 | P0 用例全绿；干净虚拟机通过 |
| M7 | 打包与上线 | 5 天 | 安装包在干净机跑通；发布 v1.0.0 |

**关键路径**：M0 → M1 → M2 → M3 → M6 → M7（M4、M5 可在 M2 之后并行）。

**范围决策（已拍板，见 `v1-delivery-plan.md §10`）**

- MP4 视频导出：**v1.0 不含**，放 v1.1。
- 同名冲突策略：**保留源相对子路径 + 后缀兜底**。
- `/api/trips` 死接口：**删除**，只保留 plan（`TripRecord`）体系。
- 多用户 / SaaS：**继续搁置**。
- 自动更新：**v1.0 不做**。

---

## 7. 安全事项（域内最高优先级 · 续做第 0 步）

> ⚠️ **`docs/handoff-phase3.md` 中仍残留高德 API Key 明文**，且该文件已提交入库 → 视为**已泄露**。

**立即处置（对应 M0 安全止血）**

1. 高德控制台**删除旧 Key、新建 Key**；设置用量告警与日限额；检查旧 Key 近期调用量/账单/异常来源。
2. 新 Key **只放本机 `backend/.env`**（`TRIPRACE_GAODE_API_KEY`），不入库、不进文档/截图/提交信息；`.env.example` 只保留占位。
3. 将 `handoff-phase3.md` 中的 Key 字面量替换为 `${TRIPRACE_GAODE_API_KEY}`，并删除个人绝对路径（`C:\Users\...`）。
4. **历史清理**：先 `git bundle create` 备份 → 用 `git filter-repo`/BFG 清除历史中的 Key 与个人路径 → `git push --force-with-lease` → 重新 clone 验证无误。
5. 开启 GitHub Secret Scanning 与 Push Protection。

> 轮换完成前，不要公开仓库、不要分享安装包。

---

## 8. 续做建议（快速上手）

**最短上手路径**

1. **先跑起来（验证基线）**：`scripts/start-dev.ps1`，或分别启动后端（`uvicorn app.main:app --reload --port 17890`）与前端渲染进程（`cd frontend && npm run dev:renderer`）；确认 `/health` 正常、主页能显示。
2. **读三份文档即可上手**：本文件（全景）+ `v1-delivery-plan.md`（计划）+ `architecture.md` / `api-design.md`（细节）。
3. **按顺序续做**：M0 安全止血 → （M1 基线恢复）→ 「我的旅迹」阶段二（海报）或直接进 M2；二者可并行。

**「我的旅迹」阶段二（海报）设计要点（已决策：方案 A = Pillow 手绘）**

- 数据来源：`TripRecord.sub_trips_json`（归档时快照，避免 DB 清空后无法回溯）。
- 海报内容：大行程名、出行时间、天数、子行程及其路线。
- 生成后写入 `TripRecord.poster_path`，前端右侧海报预览区读取展示。
- 备选（当时讨论过）：对已生成的 Folium 地图截图后再叠加元素——属方案 B，未采用。

**已知待清理项（低风险）**

- `frontend/src/api/backend.ts:9` 残留一处未被调用的 `fetch('/api/trips')`。
- 根目录 `backend/test_best_label.py` 应迁入 `backend/tests/`（M1）。
- `tests/test_metadata.py`、`tests/test_archive.py` 待按新签名 / 新命名规则修复（M1）。

---

> 本文档随里程碑推进持续更新。若与专项文档冲突，**以代码与 `v1-delivery-plan.md` 为准**，并回头修正专项文档。


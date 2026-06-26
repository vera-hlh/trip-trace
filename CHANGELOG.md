# Changelog

所有重要变更记录在此文件中，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased / v0.8.x] - Phase 4 进行中

### In Progress
- Phase 4 持续迭代（UI 打磨、行程重建功能设计中）

---

## [0.8.0] - 2026-06-26（Phase 4 功能强化）

### Added

**Phase 4 核心功能**
- `best_location_label`：归档命名优先级 POI > 乡镇 > 区县 > 城市
- 子行程命名改进：单日 `01_北极镇_0201`；多日 `05_延边_0205-0206`
- 大行程文件夹新命名：`{year}_{省市}_{天数}天_{MMDD}-{MMDD}`（含智能省市拼接+截断）
- `ArchiveLog` 操作记录模型 + 每次归档自动写入
- 归档时自动生成 `trip_log.md`（行程摘要文档）
- 操作记录页面（`HistoryPage`）- 侧边栏「📋 操作记录」入口
- GPS-less 文件时间推断：±2h 内有 GPS 文件则自动推断位置
- 数据库 `user_id` 字段（多用户预留，默认 "local"）
- 跳过已有 city 的文件（`city IS NULL` 才触发地理编码）
- 国内/境外/混合行程类型选择 + 异常文件路由到 `_待手动整理/`
- 子行程缩略图预览（Grid 4列）+ 在资源管理器中显示
- POI 候选列表（点击编辑时显示附近 5 个候选，可一键选择）
- POI 类型标签（风景名胜/热点地标/自然地名/公园/文化场馆/火车站 等）
- `force_repoi`：补充景点 POI（重新处理已有城市但无 POI 的文件）
- 归档后删除原文件选项（复选框 + 二次确认弹窗 + 自动 cleanup）
- POI 审核「复制文件名」按钮（浏览器模式下可复制代表性文件名）
- 合并行程名截断 + tooltip 完整显示

### Fixed

- POI 选择改为 `type` 字段关键字匹配（修复 `typecode=None` 导致 POI 全为空的 bug）
- 加中国边界框兜底，修复边境地区（漠河北极镇）被误判为俄罗斯的问题
- `start-dev.ps1` 加入端口 5173 清理 + 独立窗口显示前端错误
- `ArchiveLog api_calls_used` 改为从 POI 聚类数估算

### Changed

- 备注模板默认值：`地点: {province}/{city}/{township}/{poi}`
- 地理编码搜索半径：从 1000m 扩大到 2000m（适应地广人稀地区）
- 扫描页：自动触发 `force_repoi` + 自动刷新预览 + 默认清空 DB

---

## [0.7.0] - 2026-06-18（Phase 3 扩展：高德 API + POI 集成）

### Added

- 高德 API 接入（`.env` 配置，三层逆地理编码策略）
- POI 旅行类型过滤（13 种旅行相关类型，含火车站 150200、乡镇 190106），优先级排序
- WGS-84 坐标系修复：`coordsys=gps` + EXIF `GPSMapDatum` 自动检测 + GCJ-02 逆转换
- `township` 乡镇字段：高德 `addressComponent.township` 提取（精确行政区划）
- POI 审核 UI：地理编码后自动加载可编辑 POI 分组
- `geocode_source` 字段精确记录高德 API 调用次数

---

## [0.6.0] - 2026-06-14（Phase 3：前端界面）

### Added

**前端完整 UI（React + Electron）**
- `HomePage`：主页，后端状态检测 + 快速入口
- `FolderSetup`：文件夹选择（源目录 + 输出目录）
- `ScanPage`：三步工作流（扫描 SSE → 地理编码 → 归档预览 + 行程树）
  - 行程树可交互：大行程/子行程内联重命名、合并子行程
  - 进度条 + 实时日志
- `ArchivePage`：归档预览 + 执行（SSE 进度流）
- `MapPage`：Folium 行程地图（iframe 嵌入）
- `TestConsole`：后端测试控制台（所有 API 端点快捷测试）
- Zustand 全局状态管理（路径/设置/行程树，含持久化）
- `Layout` 侧边栏导航（深色主题）

---

## [0.3.0] - 2026-06-11（Phase 2 完成）

### Added

**Week 2 - 元数据提取 + 数据库（25 测试）**
- `metadata_service.py`: 照片 EXIF + 视频 ISO 6709 GPS 提取
- `timezone_utils.py`: UTC→本地时间转换（基于 GPS 坐标查时区）
- `database.py`: SQLAlchemy async + SQLite 初始化
- `/api/scan`: SSE 流式扫描进度接口

**Week 3 - 逆地理编码（28 测试）**
- `geocode_service.py`: 三层优化方案
  - 第一层：网格缓存（lat/lon 截断 3 位）
  - 第二层：POI 聚类懒加载（Haversine 双因子，典型 1000 张照片只需 5-10 次 API 调用）
  - 第三层：高德 API 在线增强（可选）
- `reverse_geocoder` 集成（全球覆盖，离线）

**Week 4 - 智能归档算法（18 测试）**
- `archive_service.py`: 行程切分核心算法
  - 大行程边界（30 天）/ 小行程（地点变化+2h）/ 同地点合并 / GPS 漂移过滤
  - 地点回归自动检测（A→B→A 模式）
  - 云南旅行全程模拟测试通过（昆明×2→大理→丽江→香格里拉）
- `/api/trips`: GET/PUT/merge 行程管理接口
- `/api/archive/preview`: 归档预览接口

**Week 5 - 文件操作 + 备注写入（19 测试）**
- `remark_service.py`: 照片/视频备注写入
  - EXIF UserComment（8字节null头+UTF-8，支持中文）
  - 同时写 ImageDescription（Android 相册兼容）
  - 视频 mutagen ©cmt 标签
- `file_utils.py`: 安全文件操作（复制/重命名冲突处理/日志）
- `/api/media/thumbnail`: JPEG 缩略图（等比缩放）

**累计：90/90 测试通过**

---

## [0.1.0] - 2026-06-11（Phase 1 完成）

### Added
- 项目初始化，建立基础目录结构
- 技术架构文档 (docs/architecture.md)
- 开发路线图 (docs/roadmap.md)
- API 接口设计文档 (docs/api-design.md)
- 开发规范文档 (docs/development-guide.md)
- Python FastAPI 后端脚手架
- Electron + React 前端脚手架
- `/health` 接口返回 `{"status":"ok","version":"0.1.0","app":"TripTrace"}`
- GitHub 仓库建立（https://github.com/vera-hlh/trip-trace）

### Architecture Decisions

**逆地理编码三层优化方案（POI 聚类懒加载）**
- 第一层：`geocode_cache` 网格缓存（lat/lon 截断 3 位，约 100m 精度）
- 第二层：POI 聚类中心距离判定（距离 ≤ 500m 且时间差 ≤ 2h 则归入同一 POI）
- 第三层：仅在切换景点时触发高德 API（典型：1000 张照片仅需 5-10 次调用）

**备注编码**
- EXIF UserComment 使用 undefined 编码头（8 个 0x00 字节）+ UTF-8，支持中文

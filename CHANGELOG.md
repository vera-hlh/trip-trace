# Changelog

所有重要变更记录在此文件中，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### In Progress
- Phase 3：前端界面开发（React + Electron）

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
  - 文件夹命名：`YYYY-MM_行程名 / 序号_地点_MMDD-MMDD`
- `/api/trips`: GET/PUT/merge 行程管理接口
- `/api/archive/preview`: 归档预览接口（完整实现）

**Week 5 - 文件操作 + 备注写入（19 测试）**
- `remark_service.py`: 照片/视频备注写入
  - EXIF UserComment（8字节null头+UTF-8，支持中文）
  - 同时写 ImageDescription（Android 相册兼容）
  - 视频 mutagen ©cmt 标签
  - 备注模板格式化
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

### Architecture Decisions (已讨论确定，待 Phase 2 实现)

**逆地理编码三层优化方案（POI 聚类懒加载）**
- 第一层：`geocode_cache` 网格缓存（lat/lon 截断 3 位，约 100m 精度）
- 第二层：POI 聚类中心距离判定（距离 ≤ 500m 且时间差 ≤ 2h 则归入同一 POI）
- 第三层：仅在切换景点时触发高德 API（典型：1000 张照片仅需 5-10 次调用）
- 聚类中心以加权平均动态更新，结果存入新增 `poi_clusters` 表

**数据层次澄清**
- EXIF 元数据：照片原始拍摄时间 + GPS 坐标（只读）
- 逆地理编码结果：POI 名称/省市区（写入 SQLite，不写入 EXIF）
- 备注字段（可选写入）：地点标签写入文件备注，供手机相册读取

**备注编码修正**
- EXIF UserComment 使用 undefined 编码头（8 个 0x00 字节）+ UTF-8，支持中文
- 放弃 ASCII 编码头方案（不支持中文）

---

## [0.1.0] - 2026-06-11

### Added
- 项目骨架搭建完成（Phase 1 完成）
- Electron + React + Vite + Tailwind CSS 前端脚手架（npm install 336 个包）
- Python FastAPI 后端（虚拟环境 + FastAPI 0.136.3 + uvicorn + SQLAlchemy）
- `/health` 接口返回 `{"status":"ok","version":"0.1.0","app":"TripTrace"}`
- pip 配置国内镜像（清华大学 TUNA）
- 前后端开发服务器均可启动并联通
- GitHub 仓库建立（https://github.com/vera-hlh/trip-trace）

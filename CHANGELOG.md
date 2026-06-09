# Changelog

所有重要变更记录在此文件中，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

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

## [0.1.0] - 待发布

### Added
- 项目骨架搭建完成
- 前后端通信验证（`/health` 接口）
- GitHub 仓库建立

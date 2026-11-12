# 旅迹 · TripTrace

[![ci](https://github.com/vera-hlh/trip-trace/actions/workflows/ci.yml/badge.svg)](https://github.com/vera-hlh/trip-trace/actions/workflows/ci.yml)

> 一款 Windows 桌面工具：把旅行照片/视频按行程智能归档，并生成可点击的交互式路径地图。

---

## 项目简介

TripTrace 帮助你把多年积累的旅行素材按「行程 → 地点 → 景点」整理成有序文件夹，并可把地点信息写回照片/视频备注。v1.0 的交付范围是**稳定归档 + 交互式 HTML 地图 + 我的旅迹（含海报）**；MP4 导出安排在 v1.1。

### 核心功能

- 🗂️ **智能归档** — 按时间与地点切分大/子行程，支持地点回归、GPS 漂移过滤
- 📍 **地理位置解析** — 离线库 + 高德 Web 服务（可选 Key），支持国内/境外/混合
- ✏️ **备注写入** — 只写备注字段，不破坏拍摄时间等元数据
- 🗺️ **交互式地图** — Folium HTML，城市热点 + 轨迹，点击热点查看照片
- 📔 **我的旅迹** — 归档记录列表、分页、排序；海报生成（方案 A = Pillow 手绘）
- 🎬 **视频导出** — MP4 合成排在 v1.1，不计入 v1.0
- 🔒 **安全默认** — 默认复制 + 预览确认，不自动删除原文件

---

## 技术栈

| 层级 | 技术 |
|---|---|
| 桌面框架 | Electron + Node.js |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + Zustand |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy async |
| 数据库 | SQLite（aiosqlite） |
| 媒体处理 | Pillow、piexif、mutagen（ffmpeg/moviepy 为 v1.1 预留） |
| 地图生成 | Folium（交互式 HTML） |
| 地理编码 | reverse_geocoder（国际离线）+ 高德 Web 服务（在线增强） |
| 打包 | PyInstaller + electron-builder（v1.0 目标） |

---

## 项目结构

```
trip-trace/
├── frontend/          # Electron + React 前端
│   ├── electron/      # Electron 主进程
│   └── src/           # React 渲染进程
├── backend/           # Python FastAPI 后端
│   └── app/
│       ├── api/       # API 路由
│       ├── core/      # 核心配置与数据库
│       ├── models/    # SQLAlchemy 模型
│       ├── services/  # 业务逻辑
│       └── utils/     # 工具函数
├── docs/              # 项目文档
└── scripts/           # 开发辅助脚本
```

---

## 快速开始

### 环境要求

- Python 3.12+（开发环境为 3.12.9）
- Node.js 20+
- 可选：FFmpeg（仅 v1.1 视频导出需要）

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# 需要跑测试时：
pip install -r requirements-dev.txt

.venv\Scripts\python.exe uvicorn_config.py
```

启动后访问 <http://127.0.0.1:17890/health>。

### 前端

```powershell
cd frontend
npm ci
npm run dev            # Electron + Vite
# 或只开浏览器渲染进程：
npm run dev:renderer   # http://127.0.0.1:5173
```

### 测试

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -q
```

---

## 文档

- [2026-11-12 分析报告与实施计划](docs/2026-11-12-analysis-and-plan.md)（当前权威）
- [项目总览（历史快照）](docs/project-overview.md)
- [技术架构](docs/architecture.md)
- [API 设计](docs/api-design.md)
- [开发规范](docs/development-guide.md)
- [开发路线图（历史）](docs/roadmap.md)
- [更新日志](CHANGELOG.md)

---

## 开发状态

**v0.8.0 原型 / v1.0 开发中**（最后代码提交：2026-07-13；2026-11 起恢复维护）

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 项目初始化 | ✅ 完成 |
| Phase 2 | 后端核心模块（当前 118 项测试通过） | ✅ 完成 |
| Phase 3 | 前端界面 + 高德 POI 集成 | ✅ 完成 |
| Phase 4 | 功能强化（POI 审核 / 行程命名 / 行程重建 / 我的旅迹） | ✅ 基本完成 |
| Phase 5 | 多用户 SaaS | ⏸️ 搁置 |
| Phase 6 | 视频生成 | 📋 v1.1 |

v1.0 范围、里程碑与验收标准见 [实施计划](docs/2026-11-12-analysis-and-plan.md)。

> 安全提示：高德 Key 只放本机 `backend/.env` 的 `TRIPRACE_GAODE_API_KEY`，不要提交到 Git 或写入文档。详见 [SECURITY.md](SECURITY.md)。

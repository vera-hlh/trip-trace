# 旅迹 · TripTrace

> 一款 Windows 桌面工具，用于智能整理旅行照片与视频，生成动态路径短视频。

---

## 项目简介

TripTrace 帮助你将存储在电脑中多年的旅行素材（照片和视频）按行程智能归档，并根据 GPS 轨迹生成动态路径展示。

### 核心功能

- 🗂️ **智能归档** — 按旅行行程自动切分文件夹，支持地点回归检测
- 📍 **地理位置解析** — 离线+在线两级逆地理编码，支持国内+国际
- ✏️ **备注写入** — 将地点信息仅写入照片/视频的备注字段，不破坏其他元数据
- 🗺️ **路径展示** — 生成交互式地图 HTML（可点击热点查看照片）
- 🎬 **视频导出** — 可将路径展示导出为 MP4 视频用于分享
- 🔒 **安全操作** — 默认"复制+预览"模式，用户确认后方可执行，支持撤销

---

## 技术栈

| 层级 | 技术 |
|---|---|
| 桌面框架 | Electron + Node.js |
| 前端 | React + TypeScript + Tailwind CSS |
| 后端 | Python 3.10+ + FastAPI |
| 数据库 | SQLite (via SQLAlchemy) |
| 媒体处理 | Pillow, piexif, mutagen, ffmpeg-python, moviepy |
| 地图生成 | Folium (交互式 HTML) |
| 地理编码 | reverse_geocoder (国际离线) + fast-geocn (国内离线) + 高德地图 API (在线增强) |
| 打包 | PyInstaller (Python) + Electron Builder |

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
│       ├── core/      # 核心配置
│       ├── models/    # 数据模型
│       ├── services/  # 业务逻辑服务
│       └── utils/     # 工具函数
├── docs/              # 项目文档
└── scripts/           # 构建/开发辅助脚本
```

---

## 快速开始

### 环境要求

- Node.js 18+
- Python 3.10+
- FFmpeg（系统级安装）

### 启动开发环境

```bash
# 1. 启动 Python 后端
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 17890

# 2. 启动前端（新终端）
cd frontend
npm install
npm run dev
```

---

## 文档目录

- [技术架构文档](docs/architecture.md)
- [开发路线图](docs/roadmap.md)
- [API 接口设计](docs/api-design.md)
- [智能归档算法](docs/archive-algorithm.md)
- [开发规范](docs/development-guide.md)
- [更新日志](CHANGELOG.md)

---

## 开发状态

🚧 **当前阶段**: Phase 1 - 项目初始化

详见 [开发路线图](docs/roadmap.md)

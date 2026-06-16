# TripTrace 项目交接文档 - Phase 3 开始前

> 生成时间：2026-06-16

---

## 项目概述

**旅迹 · TripTrace**：Windows 桌面工具，用于智能整理旅行照片/视频
- GitHub：https://github.com/vera-hlh/trip-trace
- 本地路径：`C:\Dev\trip-trace`
- 技术栈：Electron + React + TypeScript + Tailwind CSS（前端）/ Python FastAPI + SQLite（后端）

---

## 当前完成进度

### ✅ Phase 1（项目初始化）- 完成
- Electron + React + Vite 前端脚手架，可运行 `npm run dev:renderer`
- Python FastAPI 后端，`/health` 接口正常
- 前后端联通验证

### ✅ Phase 2（后端核心模块）- 完成（90/90 测试通过）

| Week | 内容 | 状态 |
|---|---|---|
| Week 2 | 元数据提取（EXIF/GPS/时区） | ✅ 25测试 |
| Week 3 | 逆地理编码（离线+双语地名） | ✅ 28测试 |
| Week 4 | 智能归档算法（行程切分） | ✅ 18测试 |
| Week 5 | 文件操作+备注写入 | ✅ 19测试 |

### ✅ 额外已完成（测试控制台）
- `http://localhost:5173/test` 可访问的后端 API 测试控制台
- 功能：扫描文件夹（SSE）/ 逆地理编码 / 归档预览（含行程树、子行程文件展开）
- 中英文双语地名（`哈尔滨 (Harbin)` 格式）

---

## 开发环境启动方式

```powershell
# 方式一：一键启动脚本
cd C:\Dev\trip-trace
.\scripts\start-dev.ps1

# 方式二：手动分步
# 后端（终端1）
cd C:\Dev\trip-trace\backend
.venv\Scripts\python.exe uvicorn_config.py

# 前端（终端2）  
cd C:\Dev\trip-trace\frontend
npm run dev:renderer
# 访问：http://localhost:5173/test（测试控制台）
```

---

## 关键 API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 健康检查 |
| POST | /api/scan | 扫描文件夹（SSE 进度）|
| POST | /api/scan/geocode | 批量逆地理编码 |
| GET | /api/scan/status | 扫描统计 |
| POST | /api/archive/preview | 归档预览（虚拟，不执行）|
| GET | /api/trips | 行程列表 |
| GET | /api/media/thumbnail | 缩略图 |

---

## Phase 3 待开发内容（前端界面）

按优先级：

### Week 6：Electron 主进程 + 基础 UI
- [ ] Electron 主进程启动 Python 后端子进程（生产模式）
- [ ] 主界面布局（侧边栏导航 + 内容区）
- [ ] 文件夹选择页面（调用系统文件夹对话框 via IPC）

### Week 7：扫描进度 + 行程树
- [ ] 扫描进度页面（SSE 实时进度条）
- [ ] 行程树形视图（大行程 → 子行程）
- [ ] 支持合并/拆分/重命名行程

### Week 8：归档预览 + 执行
- [ ] 归档预览页面（确认后才执行）
- [ ] 参数配置面板（时间阈值/地点粒度/备注模板）
- [ ] 执行归档（复制模式）+ 进度显示

### Week 9：地图展示
- [ ] Folium HTML 地图内嵌（路径+热点）
- [ ] 热点点击查看该地照片

---

## 重要注意事项

### 开发习惯（避免 LLM 卡死）
1. **commit message 必须单行**：`git commit -m "短描述"` ← 不要换行
2. **curl 加超时**：`curl --max-time 10 ...`
3. **commit 和 push 分开执行**（push 网络慢时单独处理）

### 路径说明
- 后端数据库：`C:\Dev\trip-trace\backend\triprace.sqlite`
- 测试照片：`C:\Users\Microsoft\Desktop\我的不动产\Eva\相册工具\测试文件夹（东北）`
- pip 镜像已配置为清华大学 TUNA（全局生效）

### pip 安装依赖命令（已配置国内镜像，无需 -i 参数）
```bash
cd C:\Dev\trip-trace\backend
.venv\Scripts\python.exe -m pip install <包名>
```

---

## 给新对话的指令模板

```
我在开发一个名为"旅迹 TripTrace"的 Windows 桌面照片归档工具。
项目在 C:\Dev\trip-trace，GitHub 在 https://github.com/vera-hlh/trip-trace。

Phase 1+2 已完成，详情见 docs/handoff-phase3.md。
现在开始 Phase 3（前端界面开发），从 Week 6 开始：
[描述你想做的具体任务]
```

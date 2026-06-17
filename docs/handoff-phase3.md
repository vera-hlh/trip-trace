# TripTrace 项目交接文档 - Phase 3 完成 & Phase 4 规划

> 更新时间：2026-06-17

---

## 项目概述

**旅迹 · TripTrace**：Windows 桌面工具，用于智能整理旅行照片/视频
- GitHub：https://github.com/vera-hlh/trip-trace
- 本地路径：`C:\Dev\trip-trace`
- 技术栈：Electron + React + TypeScript + Tailwind CSS（前端）/ Python FastAPI + SQLite（后端）

---

## 当前完成进度总览

### ✅ Phase 1（项目初始化）- 完成
### ✅ Phase 2（后端核心模块）- 完成（90/90 测试通过）
### ✅ Phase 3（前端界面）- 完成

| Week | 内容 | 状态 |
|---|---|---|
| Week 6 | Electron 主进程 + 基础 UI | ✅ |
| Week 7 | 扫描进度 + 行程树视图 | ✅ |
| Week 8 | 归档预览 + 执行 | ✅ |
| Week 9 | 行程地图 | ✅ |

### ✅ Phase 3 扩展（POI 集成）- 完成

| 功能 | 状态 | 说明 |
|---|---|---|
| 高德 API 接入 | ✅ | `.env` 配置，三层逆地理编码策略 |
| POI 旅行类型过滤 | ✅ | 11种旅行相关类型，优先级排序 |
| 坐标系修复 | ✅ | `coordsys=gps` + EXIF GPSMapDatum 自动检测 |
| GCJ-02 逆转换 | ✅ | metadata_service 中自动识别并转换 |
| POI 层级精简 | ✅ | 国家→省份→城市→POI（去除区县层） |
| POI 审核 UI | ✅ | 地理编码后自动加载可编辑 POI 分组 |
| 批量 POI 更新接口 | ✅ | `PUT /api/scan/poi-group` |

---

## 开发环境启动方式

```powershell
# 方式一：一键启动
cd C:\Dev\trip-trace && .\scripts\start-dev.ps1

# 方式二：手动分步
# 后端（终端1）
cd C:\Dev\trip-trace\backend
.venv\Scripts\python.exe uvicorn_config.py

# 前端（终端2）
cd C:\Dev\trip-trace\frontend
npm run dev:renderer   # 访问 http://localhost:5173/
```

---

## 关键 API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 健康检查 |
| POST | /api/scan | 扫描文件夹（SSE 进度）|
| POST | /api/scan/geocode | 批量逆地理编码（含高德 POI）|
| GET | /api/scan/geocoded | 获取 POI 分组（审核用）|
| PUT | /api/scan/poi-group | 批量更新 POI 名称 |
| GET | /api/scan/status | 扫描统计 |
| POST | /api/archive/preview | 归档预览 |
| POST | /api/archive/execute | 执行归档（SSE 进度 + 重命名覆盖）|
| GET | /api/map/html | 生成 Folium 地图 HTML |
| GET | /api/map/photos | 获取城市照片列表 |
| GET | /api/media/thumbnail | 照片缩略图 |

---

## 前端文件结构

```
frontend/src/
├── App.tsx                   # 根组件（状态驱动路由）
├── store/
│   └── appStore.ts           # Zustand 全局状态
├── components/
│   └── Layout.tsx            # 主布局（侧边栏 + 内容区）
├── pages/
│   ├── HomePage.tsx          # 主页
│   ├── FolderSetup.tsx       # 文件夹选择
│   ├── ScanPage.tsx          # 扫描 + 地理编码 + POI审核 + 行程树
│   ├── ArchivePage.tsx       # 归档预览 + 执行
│   ├── MapPage.tsx           # 行程地图
│   ├── PlaceholderPage.tsx   # 占位组件
│   └── TestConsole.tsx       # 后端测试控制台
└── ...
```

---

## 架构决策记录（已讨论确认）

### 高德 API Key 安全策略
- **当前（个人使用阶段）**：Key 存于 `backend/.env`（已在 `.gitignore`），不进入代码仓库
- **未来（多用户推广时）**：迁移到云端代理服务器，Key 永不暴露给客户端
  - 用户桌面 App → 你的代理服务器（持有 Key）→ 高德 API
  - 同时实现用户账户和 API 额度管理

### 用户系统建设时机
- **结论**：现在不建设
- **原因**：当前为个人使用，用户系统（注册/登录/额度分发/管理后台）需要 3~4 周，在没有外部用户前不合算
- **触发条件**：有第 1 个真实外部用户时开始建设
- **前瞻设计**：数据库模型加 `user_id` 字段（默认 `"local"`），迁移到多用户时无需改库结构

---

## Phase 4：功能强化（当前阶段）

> **策略**：轻量、实用、低成本，先打磨单用户体验，为未来推广做好产品内容

### 优先级 P0（立即可做，成本极低）

#### P0-1：跳过已有 POI 的文件（~10分钟）
**背景**：当前 geocode 接口只跳过 `city IS NULL` 的文件，有 city 但无 POI 的文件会重复处理。  
**方案**：查询条件改为 `city IS NULL`（无城市信息的文件），已有 city 的即跳过；若要刷新 POI 可单独触发。  
**文件**：`backend/app/api/scan.py` 的 `/scan/geocode` 接口

#### P0-2：数据库模型加 user_id 字段（~30分钟）
**背景**：未来多用户时无需重构数据库。  
**方案**：`MediaFile` 等核心模型加 `user_id = Column(String, default="local", index=True)`  
**文件**：`backend/app/models/file.py`、`backend/app/models/trip.py`

### 优先级 P1（近期开发，1~2天）

#### P1-1：本地操作记录（归档日志）
**背景**：用户需要了解每次归档的消耗情况（API 调用数量是否达到预期）。  
**内容**：每次执行归档时，写入一条操作日志到本地 SQLite  
**日志字段**：

| 字段 | 说明 |
|---|---|
| id | 主键 |
| user_id | 用户（默认 "local"）|
| created_at | 归档时间 |
| source_folder | 源文件夹路径 |
| output_folder | 输出目录 |
| photo_count | 照片数量 |
| video_count | 视频数量 |
| folders_created | 创建的子文件夹数 |
| api_calls_used | 本次消耗的高德 API 调用次数 |
| duration_sec | 归档耗时（秒）|
| status | 完成/部分失败 |

**前端**：在"归档"页面完成后显示本次统计，侧边栏新增"操作记录"入口。

#### P1-2：行程日志文件生成（trip_log.md）
**背景**：归档完成后，在每个大行程文件夹下自动生成一份行程摘要文档。  
**格式**：Markdown（所有文本编辑器/Notion/Obsidian 均支持，体积极小，可手动补充描述）  
**内容示例**：

```markdown
# 🗺️ 2025-09 东北之旅

| 项目 | 内容 |
|---|---|
| 行程时间 | 2025年9月10日 — 9月22日（共 **13天**）|
| 到访城市 | 哈尔滨市、雪乡、长春市 |
| 媒体文件 | 照片 243 张 · 视频 43 个 |

## 子行程

### 📂 01 · 哈尔滨 · 0910-0913（4天）
- **景点**：中央大街、太阳岛
- **媒体文件**：58 张照片、3 个视频

...

*由 旅迹 TripTrace 自动生成于 2025-09-22*
```

**文件位置**：`{output_path}/{大行程文件夹}/trip_log.md`  
**实现**：在 `archive/execute` 完成文件复制后追加调用，Python 字符串拼接，无需额外依赖  
**后续**：可升级为 HTML 版（更美观，可嵌入代表性缩略图）

### 优先级 P2（按需开发）

#### P2-1：视频生成模块（原 Phase 4）
见 `docs/roadmap.md`，延后到功能强化完成后

#### P2-2：测试与打包发布（原 Phase 5）
见 `docs/roadmap.md`

---

## 未来路线（条件触发）

### 当有外部用户时：Phase 5 多用户 SaaS

**架构变动**：新增云端代理服务

```
[用户桌面App] → [云端代理服务（你的服务器）] → [高德API]
                ↓
          [用户数据库 + 额度系统]
```

**功能清单**：
- 用户注册（邮箱 + 密码 + 昵称）
- 登录/免密登录（15天 refresh token）
- API 额度池管理（管理员手动录入总量）
- 额度申请 → 审批 → 发放流程
- 用户查看额度余量/明细/使用历史
- 管理员 Web 后台（审批申请、查看分发记录）
- 操作记录上传到云端

**开始时机**：第 1 个真实外部用户

---

## 重要注意事项

### 开发习惯
1. **commit message 必须单行**
2. **push 和 commit 分开执行**（网络慢时单独处理）
3. **高德 API Key**：存于 `backend/.env`，永远不要 `git add` 这个文件

### 关键路径和文件
- 后端数据库：`C:\Dev\trip-trace\backend\triprace.sqlite`
- 高德 Key 配置：`backend/.env`（`TRIPRACE_GAODE_API_KEY=...`）
- 测试照片：`C:\Users\Microsoft\Desktop\我的不动产\Eva\相册工具\测试文件夹（东北）`
- pip 镜像：已配置清华大学 TUNA（全局，无需 -i 参数）

---

## 给新对话的指令模板

```
我在开发名为"旅迹 TripTrace"的 Windows 桌面照片归档工具。
项目在 C:\Dev\trip-trace，GitHub: https://github.com/vera-hlh/trip-trace。

Phase 1~3 + POI集成全部完成，详情见 docs/handoff-phase3.md。
现在开始 Phase 4 功能强化，按优先级：
P0: 跳过已有POI的文件（修改 scan/geocode 查询条件）
P0: 数据库模型加 user_id 字段
P1: 本地操作记录（归档日志）
P1: 归档时生成 trip_log.md
```

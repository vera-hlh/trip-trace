# TripTrace 开发规范

> 版本：v1.0 | 最后更新：2026-06-09

---

## 一、环境准备

### 必须安装

| 工具 | 版本要求 | 用途 |
|---|---|---|
| Node.js | 18.x LTS+ | Electron/React 运行环境 |
| Python | 3.10+ | FastAPI 后端 |
| Git | 任意新版 | 版本管理 |
| FFmpeg | 最新版 | 视频处理（需加入系统 PATH） |

### 推荐工具

- **VSCode** + 插件：Python、ESLint、Prettier、Tailwind CSS IntelliSense
- **DB Browser for SQLite**：方便查看 SQLite 数据

---

## 二、项目启动

### 后端

```bash
cd C:\Dev\trip-trace\backend

# 创建虚拟环境（首次）
python -m venv .venv

# 激活虚拟环境
.venv\Scripts\activate     # Windows PowerShell

# 安装依赖（首次或更新依赖后）
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload --port 17890
```

后端启动后访问 `http://localhost:17890/docs` 可查看 API 文档（Swagger UI）。

### 前端

```bash
cd C:\Dev\trip-trace\frontend

# 安装依赖（首次）
npm install

# 启动开发模式（Electron + React）
npm run dev

# 仅启动 React（不含 Electron，方便纯 UI 调试）
npm run dev:renderer
```

---

## 三、目录结构规范

### 后端 (`backend/`)

```
backend/
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── api/                 # 路由层
│   │   ├── scan.py
│   │   ├── trips.py
│   │   ├── archive.py
│   │   ├── map.py
│   │   ├── media.py
│   │   └── video.py
│   ├── core/                # 核心配置
│   │   ├── config.py        # 配置项（可通过环境变量覆盖）
│   │   └── database.py      # SQLite 初始化
│   ├── models/              # SQLAlchemy 数据模型
│   │   ├── file.py
│   │   ├── trip.py
│   │   └── cache.py
│   ├── services/            # 业务逻辑
│   │   ├── metadata_service.py    # 元数据提取
│   │   ├── geocode_service.py     # 逆地理编码
│   │   ├── archive_service.py     # 智能归档算法
│   │   ├── remark_service.py      # 备注写入
│   │   ├── map_service.py         # 地图生成
│   │   └── video_service.py       # 视频导出
│   └── utils/               # 工具函数
│       ├── file_utils.py
│       ├── image_utils.py
│       └── timezone_utils.py
├── tests/                   # 单元测试
│   ├── test_metadata.py
│   ├── test_geocode.py
│   └── test_archive.py
├── requirements.txt
└── main.py                  # PyInstaller 入口
```

### 前端 (`frontend/`)

```
frontend/
├── electron/
│   ├── main.ts              # Electron 主进程
│   ├── preload.ts           # 预加载脚本（IPC 桥接）
│   └── backend.ts           # Python 子进程管理
├── src/
│   ├── components/          # 可复用 UI 组件
│   │   ├── ui/              # 基础 UI 组件（Button、Modal等）
│   │   ├── TripTree/        # 行程树形视图
│   │   ├── MapViewer/       # 地图嵌入展示
│   │   └── ProgressBar/     # 进度展示
│   ├── pages/               # 页面组件
│   │   ├── Home.tsx         # 首页（文件夹选择）
│   │   ├── Scan.tsx         # 扫描进度
│   │   ├── Trips.tsx        # 行程管理
│   │   ├── Preview.tsx      # 归档预览
│   │   ├── Settings.tsx     # 参数配置
│   │   └── Map.tsx          # 地图/视频展示
│   ├── store/               # 全局状态（Zustand）
│   │   ├── useAppStore.ts
│   │   └── useTripStore.ts
│   ├── api/                 # 封装的后端 API 调用
│   │   └── backend.ts
│   ├── types/               # TypeScript 类型定义
│   │   └── index.ts
│   └── App.tsx
├── package.json
├── vite.config.ts
└── tailwind.config.js
```

---

## 四、编码规范

### Python 后端

- 遵循 **PEP 8**，使用 `black` 格式化
- 类型注解：所有函数必须有类型注解
- 异常处理：业务异常统一用 `HTTPException`，日志用 `logging`
- 服务层函数：无副作用，便于单元测试

```python
# 好的写法
async def extract_photo_metadata(file_path: str) -> PhotoMetadata | None:
    """
    提取照片的 EXIF 元数据
    
    Args:
        file_path: 照片完整路径
        
    Returns:
        PhotoMetadata 对象，若无 EXIF 数据则返回 None
    """
    try:
        ...
    except Exception as e:
        logger.warning(f"无法提取元数据 {file_path}: {e}")
        return None
```

### TypeScript 前端

- 所有组件使用函数式 + Hooks
- Props 类型必须显式定义
- API 调用统一通过 `src/api/backend.ts` 封装

```typescript
// 好的写法
interface TripCardProps {
  trip: Trip
  onSelect: (id: number) => void
}

const TripCard: React.FC<TripCardProps> = ({ trip, onSelect }) => {
  ...
}
```

---

## 五、Git 工作流

### 分支策略

```
main          ← 稳定版本，只接受 merge request
develop       ← 开发主干
feature/xxx   ← 功能分支（从 develop 拉取）
fix/xxx       ← Bug 修复分支
```

### Commit 规范（Conventional Commits）

```
feat: 新功能
fix: Bug 修复
docs: 文档更新
refactor: 代码重构（不影响功能）
test: 测试
chore: 构建/工具链更新
```

示例：
```
feat(backend): 实现照片元数据提取模块
fix(archive): 修复地点回归切分逻辑错误
docs: 更新 API 接口文档
```

---

## 六、常见问题

### Python 虚拟环境激活失败

```powershell
# 如果遇到执行策略限制
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### fast-geocn 安装失败

```bash
# 先安装编译工具
pip install wheel
pip install fast-geocn
```

### PyInstaller 打包后找不到资源文件

在代码中使用 `sys._MEIPASS` 获取运行时路径：
```python
import sys, os

def get_resource_path(relative_path: str) -> str:
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)
```

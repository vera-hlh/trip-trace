# Phase 2 开发计划 & 用户介入分析

> 创建时间：2026-06-11 | 状态：🚀 进行中

---

## 开发策略

**结论**：我（AI 开发者）先独立完成 Week 2-5 的所有代码编写（含单元测试），您只需在关键节点介入验证，不打断日常开发节奏。

---

## 用户介入节点

### 节点 1：Week 2 完成后（可选，低成本）

**您需要提供**：1-2 个样本媒体文件
- 1 张包含 GPS 的手机照片（JPG 或 HEIC，iOS/Android 均可）
- 1 段包含拍摄位置的手机视频（MP4 或 MOV）

**用途**：验证真实设备 EXIF 格式兼容性（合成数据无法覆盖 iPhone HEIC、华为特殊格式等边界情况）

**优先级**：可选，若无特殊格式问题可跳过

---

### 节点 2：Week 3 前（一次性决策）

**您需要决定**：是否启用高德地图 API 获取景点名（POI 功能）

| 选项 | 说明 |
|---|---|
| **是** | 提供高德开发者 API Key → https://lbs.amap.com 免费申请 |
| **否（默认）** | Phase 2 暂时跳过 POI，仅用离线方案（省/市/区），后续随时可加 |

**注意**：不影响算法核心逻辑，可以后补

---

### 节点 3：Week 4 完成后 ⭐️ 最关键

**您需要做**：用真实云南照片文件夹验证行程切分算法

具体步骤：
1. 告知您的 2025 年云南照片文件夹路径（如 `C:\Users\Eva\Pictures\2025-09-云南`）
2. 运行 `/api/archive/preview` 查看归档预览
3. 确认算法输出是否符合预期（昆明×2、大理、丽江、香格里拉）

**为什么最关键**：
- 这是整个工具的核心功能
- 您的实际行程有特殊性（昆明两次的时间间隔、每个景点停留时长等）
- 只有真实数据才能发现边界问题，合成数据无法完全替代

**如果发现问题**：调整时间阈值或地点合并规则，并重新验证

---

### 节点 4：Week 5 完成后（可选）

**您需要做**：将 1-2 张归档后的照片导入手机，检查系统相册中能否看到地点备注

| 平台 | 查看方式 |
|---|---|
| iOS（iPhone）| 系统相册 → 选择照片 → 下滑查看"描述"字段 |
| Android | 系统相册 → 详情 → 备注/描述字段 |

**优先级**：可选，Phase 2 末期做也可以

---

## Phase 2 各周独立工作内容

### Week 2：元数据提取 + 数据库

我独立完成：
- SQLite 数据库初始化（`app/core/database.py`）
- SQLAlchemy 数据模型完善
- 照片元数据提取（PIL + piexif）：拍摄时间、GPS 坐标、格式检测
- 视频元数据提取（mutagen + ffmpeg-python）：ISO 6709 GPS、UTC→本地时间
- 无 GPS / 无时间文件的降级处理
- `/api/scan` 接口（异步 + SSE 进度推送）
- pytest 单元测试（含模拟 EXIF 数据）

### Week 3：逆地理编码

我独立完成：
- 集成 `reverse_geocoder`（全球离线，提供国家/省市）
- 集成 `fast-geocn`（中国离线，中文地名）
- 智能切换：中国坐标用 fast-geocn，境外用 reverse_geocoder
- POI 聚类懒加载算法（双因子：距离 ≤ 500m + 时间差 ≤ 2h）
- 地理编码缓存（`geocode_cache` 表）
- 高德 API 封装（Key 由您提供，或跳过）

### Week 4：智能归档算法

我独立完成：
- 行程切分核心算法（大行程边界 30 天 / 小行程 2h + 地点变化）
- 地点回归检测（A→B→A 自动分开行程）
- GPS 漂移过滤（短时间地点变化视为漂移）
- 文件夹命名生成（`YYYY-MM_行程名 > 序号_地点_MMDD-MMDD`）
- `/api/archive/preview` 接口
- `/api/trips` CRUD 接口
- 用模拟云南行程数据进行完整测试

**需要您**：Week 4 完成后在真实照片上验证（见节点 3）

### Week 5：文件操作 + 备注写入

我独立完成：
- 文件复制操作（保留原文件）
- 操作日志记录（支持撤销）
- `/api/archive/execute` + `/api/archive/cleanup` 接口
- 照片备注写入（piexif UserComment，`\x00×8 + UTF-8` 编码）
- 视频备注写入（mutagen `©cmt`）
- `/api/media/thumbnail` 缩略图接口

---

## 安装依赖备注

pip 已配置清华大学 TUNA 镜像（`C:\Users\Microsoft\AppData\Roaming\pip\pip.ini`）。

Phase 2 额外需要安装：
```bash
cd C:\Dev\trip-trace\backend
.venv\Scripts\python.exe -m pip install Pillow piexif mutagen ffmpeg-python timezonefinder pytz reverse_geocoder requests httpx
```

**注意**：`fast-geocn` 可能需要额外的编译工具，若安装失败先跳过，用 `reverse_geocoder` 替代。

# TripTrace v1.0 交付计划

> 基线：`37a792d`（2026-07-13，69 次提交）  
> 制定：2026-11-08  
> 目标：从"停更的 Phase 4 原型"走到"可安装、可回滚、可验证的 v1.0"  
> 预计：全职 7–9 周（约 35 人日 + 20% 缓冲）；业余每晚 2 小时约 3–4 个月

---

## 0. 目标与原则

**v1.0 的完成定义**

- 一个没有 Python/Node 环境的 Windows 10/11 用户，能安装、扫描、预览、调整、归档、看地图、查记录、卸载重装不丢数据。
- 归档结果与用户在界面上确认的方案**逐文件一致**。
- 源文件在用户明确确认前不被删除；删除进回收站，可恢复。
- 失败可定位：有日志、有错误文件清单、有回滚路径。
- 测试与构建在 CI 上自动跑，发布有 tag、有安装包、有校验和。

**执行原则**

1. 先止血，再恢复基线，再动架构，最后做体验与上线。
2. 每个里程碑都有可验证的退出条件，不靠"感觉完成"。
3. 一次只改一个事实源；宁删死代码，不保留"以后可能用"的接口。
4. 所有破坏性操作（强推、删历史、删源文件）先备份、再执行、后验证。

---

## 1. 里程碑总览

| 里程碑 | 内容 | 工期 | 依赖 | 退出条件 |
|---|---|---|---|---|
| M0 | 安全止血 | 1 天 | 无 | 仓库与历史中无有效凭据；有 LICENSE；基线 tag |
| M1 | 基线恢复 | 3 天 | M0 | 全新环境可安装；pytest/tsc/build 全绿；CI 生效 |
| M2 | 归档方案持久化 | 8 天 | M1 | 界面编辑 100% 落到磁盘；方案可重放 |
| M3 | 文件安全与一致性 | 4 天 | M2 | 重名不丢文件；删除可恢复；路径不可逃逸 |
| M4 | 地理编码与媒体兼容 | 5 天 | M1 | 境外不误判中国；HEIC/视频时间正确 |
| M5 | 性能与体验 | 4 天 | M2 | 5000 文件不卡死；无 N+1；前端可维护 |
| M6 | 验证 | 5 天 | M2–M5 | P0 用例全绿；干净虚拟机通过 |
| M7 | 打包与上线 | 5 天 | M6 | 安装包在干净机器跑通；v1.0.0 发布 |

**关键路径**：M0 → M1 → M2 → M3 → M6 → M7。  
M4、M5 可在 M2 之后并行；M6 的用例设计从 M1 就开始写。

---

## 2. M0 安全止血（Day 1）

**目标**：把已经公开的凭据作废，把仓库恢复到可以安全继续开发的状态。

### 2.1 凭据轮换（先做，不可跳）

- [ ] 在高德控制台删除旧 Key，新建 Key；设置用量告警与日限额。
- [ ] 检查旧 Key 近期调用量、账单、是否有异常来源。
- [ ] 新 Key 只放本机 `backend/.env`，不写入任何文档、截图、提交信息。
- [ ] 在 `.env.example` 中只保留 `TRIPRACE_GAODE_API_KEY=` 占位。

### 2.2 文档去敏

- [ ] 将 `docs/handoff-phase3.md` 中的 Key 字面量替换为 `${TRIPRACE_GAODE_API_KEY}`。
- [ ] 删除 handoff 中的个人绝对路径（`C:\Users\...\我的不动产\...`），改为 `<测试目录>`。
- [ ] 全仓搜索 `C:\Users\`、`TRIPRACE_GAODE_API_KEY`、`api_key`，确认无其他泄露。
- [ ] 新增 `SECURITY.md`：说明如何报告问题、支持版本、响应时间。

### 2.3 历史清理（轮换之后再做）

- [ ] `git bundle create ../trip-trace-before-purge.bundle --all` 备份。
- [ ] 用 `git filter-repo --replace-text` 或 BFG 清除历史中的旧 Key 与个人路径。
- [ ] 验证：`git log -S "<旧Key片段>" --all` 无结果；`git grep` 无结果。
- [ ] `git push --force-with-lease origin main`；本地重新 clone 验证。
- [ ] 在 GitHub 开启 Secret Scanning 与 Push Protection，确认无未处理告警。

### 2.4 仓库合规

- [ ] 添加 `LICENSE`（MIT，与 `package.json` 一致）。
- [ ] 在 `README` 增加安全说明：Key 不入库、坐标会发送到高德、地图瓦片来源。
- [ ] 清理后打基线 tag：`v0.8.0`，推送 tag。

**退出条件**：公开仓库当前树与历史中都不再包含有效凭据；Secret Scanning 无告警；仓库可正常构建。

---

## 3. M1 基线恢复（Day 2–4）

**目标**：让"新人 clone 下来能跑、测试能跑、CI 能跑"，先知道真实状态。

### 3.1 依赖与环境

- [ ] 新建干净 venv，按当前代码实际依赖安装。
- [ ] 重写 `backend/requirements.txt`：补 `pydantic-settings`；用 `pip freeze` 生成锁文件；把 `moviepy/opencv/ffmpeg-python` 移到 `requirements-video.txt`（未实现前不阻塞安装）。
- [ ] 补 `backend/requirements-dev.txt`：pytest、pytest-asyncio、black、ruff。
- [ ] 前端确认 `npm ci` 可复现；删除未使用依赖（axios、react-router-dom、lucide-react）或明确使用。
- [ ] 修 `.gitignore`：确保 `.pytest_cache/`、`dist/`、`dist-electron/`、`*.sqlite` 全覆盖。

### 3.2 测试修复

- [ ] 修 `tests/test_metadata.py`：`scan_folder()` 现在返回 `(files, skipped_dirs)`。
- [ ] 修 `tests/test_archive.py`：大行程命名已是 `{year}_{省市}_{天数}天_{MMDD}-{MMDD}`。
- [ ] 把根目录 `test_best_label.py` 收编为 `tests/test_best_label.py`。
- [ ] 删除不可读的 `backend/.pytest_cache/`（可再生成）。
- [ ] 补 `pytest.ini`/`conftest.py`，统一 `sys.path` 与 asyncio 模式。
- [ ] 记录当前真实通过率，写入 `docs/STATUS.md`。

### 3.3 构建与 CI

- [ ] `npm run build` 通过；`npx tsc --noEmit` 通过。
- [ ] 新增 `.github/workflows/ci.yml`：后端 pytest（3.12）、前端 `npm ci + tsc + build`。
- [ ] README 增加 CI 徽章与真实启动命令（`uvicorn_config.py` / `npm run dev:renderer`）。
- [ ] 修 README 三处失实：撤销、视频导出、`docs/archive-algorithm.md` 死链。
- [ ] 修正"当前阶段"描述，注明最后提交日期。

**退出条件**：干净机器按 README 能装、能跑；CI 在 main 上绿；测试失败数为 0（或明确 skip 并写明原因）。

---

## 4. M2 归档方案持久化（Week 2–3，核心）

**目标**：消灭"界面编辑是幻觉"的根因。预览生成方案 → 方案可编辑 → 执行消费方案，不再重算。

### 4.1 数据模型

新增三张表（`create_all` 即可，不动旧表）：

- [ ] `archive_plans`：`id, source_folder, output_folder, options_json, status(draft/executed/abandoned), plan_version, source_snapshot, created_at, executed_at`
- [ ] `plan_trips`：`id, plan_id, parent_id, kind(big/sub), folder_name, display_name, start_date, end_date, sequence_num, location_label, container_name, sort_order`
- [ ] `plan_files`：`id, plan_id, trip_id, media_file_id, target_rel_path, status(pending/copied/skipped/failed), error`

`source_snapshot` 存文件集合的哈希（路径 + size + mtime），用于检测"预览后源目录变了"。

### 4.2 接口

- [ ] `POST /api/archive/plans`：基于当前扫描数据生成方案（替代 preview 的计算职责）。
- [ ] `GET /api/archive/plans/{id}`：返回完整树 + 文件明细。
- [ ] `PATCH /api/archive/plans/{id}`：重命名大/子行程、合并子行程、拆分、容器分组、归档模式。
- [ ] `POST /api/archive/plans/{id}/execute`：只消费方案，不重算；记录 `plan_id` 到 `archive_logs`。
- [ ] `DELETE /api/archive/plans/{id}`：放弃草稿。
- [ ] 保留 `/api/archive/preview` 作为只读兼容层，内部调用 plan 生成，标记 deprecated。

### 4.3 一致性规则

- [ ] 执行前校验 `source_snapshot`；不一致返回 409，提示重新生成。
- [ ] `plan_version` 乐观锁，防止两个页面同时改。
- [ ] 执行幂等：同一 plan 重复执行只补未完成项。
- [ ] 方案废弃时保留审计记录，不物理删除。

### 4.4 前端改造

- [ ] `appStore` 只保留 `currentPlanId`，删除 `tripStructure` 作为权威数据源（可保留只读缓存）。
- [ ] ScanPage/ArchivePage/TripRebuilderPage 改为读写同一个 plan。
- [ ] 编辑操作改为 PATCH，失败回滚 UI 并提示。
- [ ] 刷新/重启后从 plan 恢复，不再依赖 localStorage 的旧树。
- [ ] 未保存修改离开页面时提示。

### 4.5 测试

- [ ] 合并两个子行程 → 执行后磁盘只有一个目录，文件数正确。
- [ ] 重命名 → 执行后目录名正确；重启后仍显示新名字。
- [ ] 容器分组 → 路径为 `big/container/sub/file`。
- [ ] 方案生成后修改源目录 → 执行被拒绝并提示。
- [ ] 两个客户端同时 PATCH → 后者收到版本冲突。

**退出条件**：所有结构性编辑都能在磁盘上验证；执行路径与方案逐文件一致；无"重算导致覆盖"的代码路径。

---

## 5. M3 文件安全与一致性（Week 3–4）

**目标**：不丢文件、不误删、不越界。

### 5.1 同名冲突

- [ ] 目标路径默认保留"源目录内相对子路径"（解决 DCIM 多子目录同名）。
- [ ] 仍冲突时追加 `_1/_2`，并在 SSE 中报告 `conflict`。
- [ ] 禁止"目标存在就静默 skip"；skip 必须仅限"内容相同"。
- [ ] 冲突策略写入方案，执行时不再临时决定。

### 5.2 复制校验

- [ ] 复制后校验 size；大文件可选 SHA-256。
- [ ] 校验通过才写 `current_path` 与 `status=copied`。
- [ ] 失败文件单独列出，支持"仅重试失败项"。

### 5.3 删除原文件

- [ ] `cleanup` 返回字段统一为 `deleted`，前端同步修正 `deleted_count`。
- [ ] 删除前校验目标存在且大小一致。
- [ ] 改用 `send2trash` 进回收站，保留 `permanent=true` 作为显式选项。
- [ ] cleanup 必须携带 `plan_id`，只能删除该方案已成功复制的源文件。
- [ ] 二次确认弹窗列出将删除的数量与总大小。

### 5.4 路径安全

- [ ] 统一净化目录名：拒绝 `<>:"/\|?*`、结尾空格/点、`CON/PRN/AUX/NUL/COM1…`、`..`、绝对路径。
- [ ] 用户输入即时校验并提示，后端二次校验。
- [ ] 统一路径前缀匹配为 `norm + os.sep`，删除 `contains(basename)` 兜底。
- [ ] 缩略图/媒体接口限制在已扫描根目录内（或签名 token），禁止任意路径读取。

### 5.5 数据库与配置路径

- [ ] DB 默认放 `%APPDATA%\TripTrace\triprace.sqlite`，可用 `TRIPRACE_DB_PATH` 覆盖。
- [ ] `.env` 从应用目录/用户目录加载，不依赖 CWD。
- [ ] Electron `spawn` 显式设置 `cwd` 与 `TRIPRACE_DB_PATH`。

**退出条件**：同名夹具全部落盘；穿越用例全部被拒；cleanup 可从回收站恢复；换工作目录启动不丢库。

---

## 6. M4 地理编码与媒体兼容（Week 4–5）

**目标**：位置别标错，iPhone 素材别丢时间。

### 6.1 行程类型真正生效

- [ ] `abroad`：强制离线，禁止调用高德。
- [ ] `domestic`：允许高德；境外坐标标记异常。
- [ ] `mixed`：按坐标判定，境内高德、境外离线。
- [ ] 把矩形 bbox 换成中国国界多边形（内置简化 GeoJSON，point-in-polygon）。
- [ ] 回归用例：首尔、河内、乌兰巴托、莫斯科、漠河、香港、台北。

### 6.2 缓存与成本

- [ ] 启用 `geocode_cache` 表：3 位小数网格读写，命中即返回。
- [ ] `poi_clusters` 持久化，按方案/行程隔离。
- [ ] `force_repoi` 按网格去重，先算预计调用数并让用户确认。
- [ ] 地理编码改为后台任务 + SSE 进度 + 可取消。
- [ ] 记录真实 API 调用数，不再用 `(city, poi)` 估算。

### 6.3 媒体兼容

- [ ] 接入 `pillow-heif`，支持 iPhone HEIC/HEIF 的时间与 GPS。
- [ ] 视频改用 `ffprobe` 读 `creation_time`、`©day`、ISO6709、旋转信息。
- [ ] 无时间/无 GPS 的文件显式标记 `needs_review`，不再静默用 mtime 冒充拍摄时间。
- [ ] RAW 明确标注"仅归档不改写"，或从支持列表移除。
- [ ] 固化样本集：iPhone HEIC、Android JPEG、DJI MP4、MOV、截图、无 EXIF 图。

**退出条件**：境外样本不再出现"中国"；HEIC 样本时间/GPS 正确；1000 张样本高德调用 ≤ 15 次；调用数可审计。

---

## 7. M5 性能与体验（Week 5–6）

**目标**：5000 张不卡死，代码还能继续改。

### 7.1 后端性能

- [ ] 扫描、复制、PIL 保存、缩略图全部移出事件循环（`asyncio.to_thread` + 信号量）。
- [ ] 扫描去重改为一次性预加载路径集合，消除每文件 SELECT。
- [ ] 归档批量查询 media_file，消除循环内两次 SELECT。
- [ ] 缩略图落盘缓存（key = path + mtime + width），视频用 ffmpeg 抽帧。
- [ ] 慢查询加索引：`files(original_path)`、`files(city)`、`plan_files(plan_id)`。
- [ ] 增加请求耗时中间件与慢请求日志。

### 7.2 前端可维护性

- [ ] 统一 API 客户端：base URL、超时、错误归一、类型定义；删除各页面硬编码。
- [ ] 拆分 `ScanPage`（1700 行）为 hooks + 子组件。
- [ ] 修 Tailwind 动态类名（`text-${color}-400` 不会生成）。
- [ ] 删除死代码：`Home.tsx`、`PlaceholderPage`、未用依赖。
- [ ] 增加错误边界、空状态、加载骨架、失败重试。
- [ ] 版本号从 `package.json` 注入，修侧边栏 `v0.8.0` 硬编码。

### 7.3 可观测性

- [ ] 结构化日志（JSON 行），写 `%APPDATA%\TripTrace\logs`，按天轮转。
- [ ] 关键事件：扫描开始/结束、API 调用数、归档文件级结果、异常堆栈。
- [ ] 日志不记录 Key、完整路径可脱敏。

**退出条件**：5000 文件扫描期间 `/health` 仍 < 1s；归档 1000 文件无事件循环阻塞告警；前端无重复 fetch 封装。

---

## 8. M6 验证（Week 6–7）

**目标**：用证据证明"能交付"，而不是"应该没问题"。

### 8.1 测试矩阵

- [ ] 单元：行程切分边界（同城 29 天、无时间、漂移、回归、跨年）、命名、备注编码、路径净化。
- [ ] 集成：方案 CRUD → 执行 → 磁盘校验；冲突；cleanup；409 失效；权限错误。
- [ ] 媒体：HEIC/JPEG/PNG/MP4/MOV/截图/无 EXIF/损坏文件。
- [ ] 数据量：42 文件真实集、1000 合成集、5000 压力集、跨多年集。
- [ ] 安全：本地 API 鉴权、CORS、路径穿越、任意文件读、Secret 扫描。
- [ ] E2E：Electron/Playwright 跑 扫描 → 预览 → 合并/重命名 → 归档 → 地图 → 记录。
- [ ] 打包：干净 Windows VM（无 Python/Node）安装 → 使用 → 卸载重装。

### 8.2 验收标准

- [ ] P0 用例 100% 通过；P1 允许有明确记录的 known issue。
- [ ] 5000 文件扫描 < 10 分钟（本机 SSD），内存 < 1.5 GB。
- [ ] 归档 1000 文件失败率 0；中断后可重试且不重复复制。
- [ ] 安装包在干净 VM 上一次通过，无缺失 DLL/VC++ 运行库。
- [ ] 卸载重装后历史记录与设置保留（用户数据目录不删）。

### 8.3 产出

- [ ] `docs/test-plan.md`、`docs/test-report.md`（含环境、数据、结果、截图）。
- [ ] `docs/known-issues.md`。
- [ ] 一份 5 分钟演示脚本与录屏。

---

## 9. M7 打包与上线（Week 7–8）

**目标**：用户双击安装就能用。

### 9.1 后端打包

- [ ] 新增 `backend/main.py` 作为 PyInstaller 入口（启动 uvicorn，读环境变量端口/DB）。
- [ ] 采用 one-folder 模式（启动快、hidden imports 好排查），输出到 `backend/dist/`。
- [ ] 确认 `reverse_geocoder` 数据文件、`folium` 模板、`timezonefinder` 数据被打进包。
- [ ] 后端 exe 支持 `--version`、`--port`，异常写日志后退出码非 0。

### 9.2 Electron 打包

- [ ] `electron-builder` 配置 `asar`、`extraResources`（后端目录）、NSIS、图标、per-user 安装（不要求管理员）。
- [ ] 生产模式启动顺序：建用户目录 → 起后端 → 等 `/health` → 开窗；超时给出可操作提示。
- [ ] 单实例锁；退出时优雅终止后端；崩溃后残留进程清理。
- [ ] 安装包体积目标 < 150 MB（后端 + Electron + 数据文件）。

### 9.3 代码签名与 SmartScreen

- [ ] 有证书：签名 exe 与安装包；无证书：文档说明 SmartScreen 提示与"更多信息 → 仍要运行"。
- [ ] 记录 SHA-256 校验和，随 Release 发布。

### 9.4 发布

- [ ] 版本升至 `1.0.0`（前后端/安装包一致）。
- [ ] 更新 CHANGELOG、README（安装、首次使用、卸载、数据位置）。
- [ ] 打 tag `v1.0.0`，创建 GitHub Release，附安装包、校验和、Release Notes。
- [ ] 准备回滚：上一版安装包、DB 迁移备份说明。
- [ ] 小范围 beta：3–5 个真实用户，1 周，收集日志与问题。

**退出条件**：干净 VM 安装即用；卸载重装数据保留；Release 页面完整；回滚方案可执行。

---

## 10. 范围决策（需拍板）

| 决策 | 建议 | 理由 |
|---|---|---|
| v1.0 是否包含 MP4 导出 | **否，放 v1.1** | 视频管线（Playwright 截图 + moviepy + ffmpeg）约 7–10 人日，且显著增加打包体积与失败面；核心价值是归档 |
| 同名冲突策略 | **保留源相对子路径 + 后缀兜底** | 相机卡多子目录同名是真实高频场景 |
| `/api/trips` 死接口 | **删除**，只保留 plan 体系 | 从未写入过数据，保留只会误导 |
| 多用户 / SaaS | **继续搁置** | 与 v1.0 目标无关，等有外部用户再启动 |
| 自动更新 | **v1.0 不做** | 先保证手动安装可靠，避免更新通道引入新故障 |

---

## 11. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 旧 Key 已被爬虫利用 | 中 | 费用/配额 | 立即轮换、查账单、设限额与告警 |
| 历史清理强推出错 | 低 | 仓库损坏 | 先 bundle 备份；force-with-lease；重新 clone 验证 |
| 方案持久化改造拖期 | 中 | 阻塞上线 | 先做最小闭环（生成/读取/执行），合并/容器第二步 |
| HEIC 解码库打包失败 | 中 | iPhone 用户不可用 | 提前在干净 VM 验证 wheel；准备 exiftool 兜底 |
| PyInstaller 缺依赖 | 高 | 安装包不可用 | M1 就做一次最小打包冒烟，不等到 M7 |
| 杀软误报 | 中 | 用户不敢装 | 签名、提交误报、提供校验和与源码构建说明 |
| 高德配额 | 中 | 地理编码失败 | 持久缓存、预估调用、离线降级 |
| 单人长期停更 | 中 | 计划失效 | 每周固定 2 个晚上；里程碑可缩小但不可跳过验证 |

---

## 12. 每周节奏与完成定义

**每周**

- 周一：确认本周 1 个里程碑目标 + 3 个可验收项。
- 周三：中间演示（真实数据，不跑合成）。
- 周五：更新 CHANGELOG、STATUS、下周待办；打 tag（可选）。

**每个提交**

- [ ] 只做一件事，提交信息用 `feat/fix/refactor/test/docs/chore`。
- [ ] 本地跑 `pytest` + `tsc` + `build`。
- [ ] 涉及用户可见行为时更新 CHANGELOG。
- [ ] 不提交 `.env`、数据库、个人路径、日志。

**每周退出**

- CI 绿；无 P0 未关闭；文档与代码一致；演示可复现。

---

## 13. 未来 7 天清单（可直接执行）

1. [ ] 高德控制台删除旧 Key、建新 Key、设限额。
2. [ ] handoff 去敏提交（Key + 个人路径）。
3. [ ] bundle 备份 + 历史清理 + 强推 + 重新 clone 验证。
4. [ ] 开 Secret Scanning / Push Protection。
5. [ ] 加 LICENSE、SECURITY.md。
6. [ ] 干净 venv 重装，重写 requirements，补 pydantic-settings。
7. [ ] 修两个陈旧测试，跑通 pytest。
8. [ ] 加 CI（pytest + tsc + build）。
9. [ ] README 真实性修订：撤销、视频、死链、启动命令、当前阶段。
10. [ ] 打 `v0.8.0` 基线 tag，写 `docs/STATUS.md`。

---

## 附：完成度看板（建议放 GitHub Projects）

| 状态 | 含义 |
|---|---|
| Backlog | 已记录，未排期 |
| Ready | 验收标准明确，可开工 |
| In Progress | 正在做，最多 2 项 |
| Verify | 代码完成，等测试/演示 |
| Done | CI 绿 + 验收通过 + 文档更新 |

**P0 标签**：数据丢失、凭据泄露、方案不一致、无法安装。  
**P1 标签**：功能错误但有绕过、性能明显退化。  
**P2 标签**：体验、文档、重构。

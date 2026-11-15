# M7 验证计划与记录

**最后更新**：2026-11-15  
**代码基线**：`8bff8cc`（聚类 source/poi_type 修复）；文档基线 `28428d5`  
**目的**：在打包 v1.0 前，验证真实扫描/地理编码/方案/归档/清理链路，以及前端交互。

---

## 1. 相关记录

- [东北边境真实样本验证](2026-11-14-real-sample-validation.md)
- [越南游轮真实样本验证](2026-11-14-vietnam-sample-validation.md)
- [Overpass 境外景点后续事项](2026-11-13-overpass-followup.md)

---

## 2. 自动验证结果

| 项目 | 结果 |
|---|---|
| 后端单元/集成测试 | **153 passed** |
| 前端 TypeScript | `tsc --noEmit` 通过 |
| 前端 renderer 构建 | `vite build --mode renderer` 通过（63 modules） |
| CI | 绿 |
| 旧接口移除 | OpenAPI 无 `/api/archive/preview`、`/api/archive/execute` |
| 后端冷启动 | 临时 DB 启动成功，`/health` 200，迁移成功 |
| 方案接口 | `/api/archive/plans/{id}/execute` 存在 |

> 自动验证不包含真实 Electron 界面点击。

---

## 3. 真实样本结果

### 3.1 东北边境（domestic）

样本：`2023.01.30-02.09 东北（哈尔滨、漠河、长白山）`

| 项目 | 结果 |
|---|---|
| 媒体文件 | 1194 |
| 有 GPS | 869 |
| 无 GPS | 325 |
| 扫描错误 | 0 |
| 地理编码更新 | 869 |
| 高德调用 | 54 |
| 异常 | 0 |
| 境外国家 | 0 |
| 方案 | 1 大行程 / 7 子行程 / 1194 文件 |

关键结论：

- 漠河 362 张：黑龙江省/大兴安岭/漠河市，无俄罗斯地名；
- 长白山 309 张：吉林省/延边、白山，无朝鲜地名；
- 发现并修复 POI 聚类 `source/poi_type` 丢失（`8bff8cc`）；
- 修复后 869 张全部 `geocode_source=gaode`，848 张有 `poi_type`。

### 3.2 越南游轮（abroad）

样本：`2017.07.18-22 皇家歌诗达游轮游（越南）`

| 项目 | 结果 |
|---|---|
| 媒体文件 | 145（5 个 AAE 跳过） |
| 有 GPS | 114 |
| 无 GPS | 31 |
| 扫描错误 | 0 |
| 地理编码更新 | 114 |
| 在线 API 调用 | 13 |
| 异常 | 5（香港） |
| 国家分布 | 越南 75 / 中国 39 |
| 方案 | 1 大行程 / 7 子行程 / 145 文件 |

关键结论：

- 越南城市识别为芽庄、會安、岘港、顺化；没有误用高德；
- 香港 5 张被标为异常，符合 `abroad` 预期；
- 海南/Sanya 近海坐标显示中国城市，但被多边形判为海域，未计入异常；
- Nominatim POI 覆盖不完整，公共 Overpass 仍 502/超时。

---

## 4. 前端手工验证步骤

> 必须实际点一遍；API 测试不能替代。

### 4.1 准备隔离环境（推荐）

使用临时数据库和少量样本，避免污染正式库/正式归档目录。

```powershell
$test = "C:\TripTrace-Test"
New-Item -ItemType Directory -Force "$test\src", "$test\out" | Out-Null

# 从东北样本复制少量文件（建议 10-20 个，含 GPS）
$sample = "C:\Users\Microsoft\Desktop\2023.01.30-02.09 东北（哈尔滨、漠河、长白山）"
Get-ChildItem -LiteralPath $sample -File |
  Where-Object { $_.Extension -in ".jpg", ".jpeg", ".mp4" } |
  Select-Object -First 12 |
  Copy-Item -Destination "$test\src"
```

### 4.2 启动后端（隔离 DB）

打开一个 PowerShell：

```powershell
$env:TRIPRACE_DB_PATH = "C:\TripTrace-Test\ui-test.sqlite"
$env:TRIPRACE_NOMINATIM_ENABLED = "true"
$env:TRIPRACE_OVERPASS_ENABLED = "false"   # 公共 Overpass 不稳定，先关

cd C:\Dev\trip-trace\backend
.\.venv\Scripts\python.exe uvicorn_config.py
```

### 4.3 启动 Electron（另一个 PowerShell）

```powershell
cd C:\Dev\trip-trace\frontend
npm run dev
```

> 不要用 `npm run dev:renderer` 做文件夹选择验证：它只开浏览器，没有 Electron 文件夹对话框。  
> `scripts/start-dev.ps1` 会使用默认数据库并只开 renderer，不适合这轮隔离验证。

### 4.4 界面检查

1. 主页显示后端“已连接”；
2. 侧边栏没有“测试控制台”，主页也没有入口；
3. 选择源目录 `C:\TripTrace-Test\src`，输出目录 `C:\TripTrace-Test\out`；
4. 扫描：进度持续更新，完成统计约 12 个文件；
5. 选择“国内行程” → 地理编码；
6. 行程树：重命名一个大行程/子行程；
7. 执行归档：观察 SSE 进度、完成摘要；
8. 检查 `C:\TripTrace-Test\out` 目录结构、`trip_log.md`、备注；
9. 勾选清理原文件 → 移入回收站；确认源文件可恢复、目标仍在；
10. 打开“我的旅迹”“地图”“操作记录”，确认缩略图和海报；
11. 关闭应用重启，确认方案需要重新生成（当前 `planId` 不持久化）。

### 4.5 境外样本（可选）

用越南样本重复：

```text
源目录：C:\Users\Microsoft\Desktop\2017.07.18-22 皇家歌诗达游轮游（越南）
行程类型：境外
```

预期：

- 约 145 个媒体文件，114 个有 GPS；
- 越南城市为芽庄/會安/岘港/顺化；
- 约 5 个香港照片提示异常；
- 景点 POI 可能为空或不完整，不是崩溃。

---

## 5. 小规模真实归档 + 清理

建议使用 4.1 的 `$test\src`，不要直接对 14.8GB 原目录执行清理。

检查项：

- [ ] 输出目录按大行程/子行程分层；
- [ ] 同名文件不覆盖；
- [ ] `trip_log.md` 生成；
- [ ] 照片备注写入成功；
- [ ] 视频备注 sidecar 生成；
- [ ] 清理后源文件进入回收站；
- [ ] 目标文件仍存在且 size 一致；
- [ ] 目标缺失/size 不一致时拒绝删除。

---

## 6. 验证结果记录

| 日期 | 项目 | 结果 | 备注 |
|---|---|---|---|
| 2026-11-13 | 后端冷启动 + health + OpenAPI | ✅ | 临时 DB；旧接口不存在 |
| 2026-11-13 | 自动测试 / tsc / build / CI | ✅ | 153 passed |
| 2026-11-14 | 东北边境真实样本 | ✅ | 1194 文件；0 境外误判；0 异常 |
| 2026-11-14 | 越南游轮真实样本 | ✅ | 145 媒体；75 越南/39 中国；5 香港异常 |
| 2026-11-14 | POI 聚类 source/poi_type | ✅ 已修 | `8bff8cc` |
| 待补 | 前端手工冒烟 | ⏳ | 需用户操作 |
| 待补 | 小规模真实归档 + 清理 | ⏳ | 建议用 `C:\TripTrace-Test\src` |
| 待补 | 5000 张性能 | ⏳ | 需样本或合成集 |
| 待补 | 干净 Windows 打包 | ⏳ | M8 |

---

## 7. 已知限制（不要误判为 bug）

- `planId` 不跨应用重启持久化；
- 没有 `DELETE` 方案、按时间拆分、执行幂等/只重试失败项；
- 大行程合并时源容器不迁移；
- 公共 Overpass 可能 502，境外景点可能为空；
- 图片备注用 Pillow 重编码，可能有质量损失；
- M7 删除了旧接口，旧会话/旧前端缓存可能提示重新生成方案；
- 近海中国坐标在 `abroad` 下可能显示中国城市但不计异常；
- 自动生成的子行程名可能是 POI/公交站名，需要手动重命名。

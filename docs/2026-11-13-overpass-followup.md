# Overpass 境外景点：现状、问题与后续优化

**日期**：2026-11-13  
**相关提交**：`fac0291`（Nominatim）、`804b27b`（Overpass）  
**状态**：代码已接入；公共实例可用性不稳定，暂不阻塞 v1.0 归档交付。

---

## 1. 当前实现

境外坐标（且不在中国国界内）的处理链：

1. 离线 `reverse_geocoder`：国家/省/城市/区；
2. Nominatim `/reverse`：补充地址和旅行相关 POI；
3. 如果 Nominatim 没拿到景点，再查 Overpass 附近 `tourism=attraction/museum/viewpoint/zoo/theme_park/artwork`；
4. 结果写入 `geocode_cache`，`source` 为 `nominatim` 或 `overpass`。

配置（`backend/.env`）：

```env
TRIPRACE_NOMINATIM_ENABLED=true
TRIPRACE_NOMINATIM_USER_AGENT=TripTrace/0.1 (your-email)
TRIPRACE_NOMINATIM_EMAIL=your-email
TRIPRACE_OVERPASS_ENABLED=true
# 可选
# TRIPRACE_OVERPASS_URL=https://overpass-api.de/api/interpreter
# TRIPRACE_OVERPASS_RADIUS_M=1500
# TRIPRACE_OVERPASS_TIMEOUT_SECONDS=15
```

默认值：

- Nominatim / Overpass 默认关闭，需显式开启；
- 中国坐标不送 OSM；
- Nominatim 与 Overpass 都限速 1 请求/秒；
- Overpass 遇 429/502/503/504 或异常时，退避 10 分钟，期间直接返回空。

---

## 2. 已验证内容

- 单元测试：Nominatim 解析、Overpass 解析/排序、过滤咖啡馆/酒店/无名对象、缓存 source、境外调用、国内不调用；
- 真实 Nominatim：首尔坐标返回国家/城市（POI 为空或被过滤）；
- 真实 Overpass：苏黎世坐标返回 `Karlsturm`（观景点），说明查询与解析链路可用；
- 公共 `overpass-api.de` 在首尔坐标上多次返回 502/超时，属于实例容量问题，不是代码异常。

---

## 3. 已知问题

### 3.1 公共 Overpass 可用性差

- `overpass-api.de` 经常 502（All query workers are busy）；
- 其他公共镜像（kumi、private.coffee 等）从当前网络访问会超时；
- 当前只有 10 分钟退避，没有多实例自动 fallback；
- 扫描境外照片时，第一个失败请求可能等待超时，之后 10 分钟内跳过。

### 3.2 POI 质量仍有限

- Nominatim 的 `reverse` 返回最近对象，常常是咖啡馆/商店；已过滤非旅行类型，但可能直接没有 POI；
- Overpass 只查 `tourism` 的少数类型，未覆盖公园、历史遗迹、自然地名、宗教场所等；
- 没有做“景点知名度/权重”排序，只有距离 + 简单类型惩罚；
- OSM 在部分国家/城市 POI 稀疏，尤其非热门景区。

### 3.3 请求量与缓存

- 每个境外 100m 网格最多 2 次请求（Nominatim + Overpass）；
- 密集城市可能仍有几十到上百个网格；
- 缓存只缓存最终结果，不单独缓存“Overpass 无结果”，失败/空结果可能重复查询（有 10 分钟进程级退避，但重启后重来）；
- 没有按国家/城市批量预取。

### 3.4 可观测性

- UI 只显示“在线 API 调用次数”，不区分高德/Nominatim/Overpass；
- Overpass 被退避时只有后端日志，用户不知道景点为什么为空；
- 没有记录每个 provider 的成功率、平均延迟、命中率。

### 3.5 隐私

- 开启后境外坐标会发送到 OpenStreetMap（Nominatim/Overpass）；
- 当前只在 README 说明，应用内没有显式提示或开关；
- 缓存会把坐标和地名持久化到本地数据库。

---

## 4. 后续优化方案（按优先级）

### P0：提升可用性

1. 支持 `TRIPRACE_OVERPASS_URLS` 多实例列表；
2. 按顺序尝试，失败切换下一个；
3. 对 502/超时做短重试 + 指数退避；
4. 记录每个实例的健康状态，避免每次从坏实例开始；
5. 允许完全关闭 Overpass，只保留 Nominatim/离线。

### P1：提升 POI 质量

1. 扩大查询类型：`historic`、`leisure=park/garden`、`natural=peak/water/beach`、`amenity=place_of_worship`；
2. 增加类型权重：attraction/museum/castle > viewpoint/monument > park/nature > 其他；
3. 排除 `tourism=hotel/guest_house/information` 等非景点；
4. 对同名/近名结果去重；
5. 可选接入 Wikidata/Wikipedia 作为知名度信号。

### P2：降低请求量

1. 缓存“空结果”（带 TTL，例如 7 天），避免重复查询；
2. 按行程/城市批量查询，而不是逐点；
3. 先按城市中心查一次，再对无结果点补查；
4. 对同一景点 500m 内合并网格。

### P3：可观测性与 UI

1. 返回 `provider_stats`：amap / nominatim / overpass 的调用数、成功数、失败数；
2. UI 显示“境外景点由 OpenStreetMap 提供，可能不完整”；
3. 设置页增加 Nominatim/Overpass 开关和隐私说明；
4. 日志记录 provider、耗时、HTTP 状态、是否命中缓存。

### P4：商业 provider（可选）

如果真实样本证明 OSM 覆盖不足：

- Mapbox Geocoding / Places；
- Google Geocoding / Places；
- 高德海外授权服务。

需要 Key/付费，但 POI 质量和稳定性更好；可保持 provider 抽象，按国家/用户配置切换。

---

## 5. 真实样本验证计划

等有真实境外照片后：

1. 选日本、韩国、欧洲各 1 组样本；
2. 统计：
   - 城市/行政区准确率；
   - 景点命中率（有人工标注）；
   - 每 100 张照片的 API 请求数；
   - 平均耗时、失败率；
3. 对比 Nominatim、Overpass、商业 provider；
4. 根据结果决定是否默认开启、是否换 provider、是否调整半径/类型；
5. 把结论补回本文，并更新 README/设置页。

---

## 6. 当前决策

- 代码保留，默认关闭；
- 本机 `.env` 已开启，便于实际使用验证；
- 公共 Overpass 不稳定时不阻塞归档：退回 Nominatim/离线，城市级仍可用；
- v1.0 不把“境外景点级 POI”作为硬性验收项；
- 等真实样本和可用实例再决定是否投入 P0–P4。

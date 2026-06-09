# TripTrace API 接口设计

> 版本：v1.0 | 后端地址：`http://localhost:17890`

---

## 通用规范

- 所有接口返回 JSON 格式
- 成功响应：`{ "success": true, "data": {...} }`
- 失败响应：`{ "success": false, "error": "错误信息" }`
- 长任务使用 SSE（Server-Sent Events）推送进度

---

## 系统接口

### GET `/health`
健康检查

**响应**
```json
{ "status": "ok", "version": "0.1.0" }
```

---

## 扫描接口

### POST `/api/scan`
扫描文件夹，提取所有媒体文件元数据（长任务，SSE 推送）

**请求体**
```json
{
  "folder_path": "C:\\Users\\Eva\\Pictures\\2025-09-云南",
  "options": {
    "include_subdirs": true,
    "enable_online_geocode": false,
    "gaode_api_key": ""
  }
}
```

**SSE 事件流**
```
data: {"type": "progress", "current": 10, "total": 150, "file": "IMG_001.jpg"}
data: {"type": "progress", "current": 11, "total": 150, "file": "IMG_002.jpg"}
...
data: {"type": "complete", "total_files": 150, "with_gps": 130, "without_gps": 20}
data: {"type": "error", "message": "无法读取文件: xxx.heic"}
```

---

## 行程接口

### GET `/api/trips`
获取行程列表（含大行程和子行程）

**查询参数**
- `parent_id`（可选）：获取指定大行程的子行程

**响应**
```json
{
  "success": true,
  "data": {
    "trips": [
      {
        "id": 1,
        "trip_name": "2025-09_云南之旅",
        "display_name": "2025年9月 云南之旅",
        "start_date": "2025-09-10",
        "end_date": "2025-09-20",
        "parent_trip_id": null,
        "file_count": 152,
        "sub_trips": [
          {
            "id": 2,
            "trip_name": "01_昆明_0910-0913",
            "start_date": "2025-09-10",
            "end_date": "2025-09-13",
            "parent_trip_id": 1,
            "sequence_num": 1,
            "location_label": "昆明市",
            "file_count": 32
          }
        ]
      }
    ]
  }
}
```

### PUT `/api/trips/{trip_id}`
修改行程（重命名）

**请求体**
```json
{ "display_name": "我的云南之旅" }
```

### POST `/api/trips/merge`
合并两个子行程

**请求体**
```json
{
  "trip_ids": [2, 3],
  "new_name": "01_昆明_0910-0915"
}
```

### POST `/api/trips/split`
将一个子行程按日期拆分

**请求体**
```json
{
  "trip_id": 2,
  "split_at": "2025-09-12T12:00:00"
}
```

---

## 归档接口

### POST `/api/archive/preview`
预览归档方案（不执行任何文件操作）

**请求体**
```json
{
  "folder_path": "C:\\Users\\Eva\\Pictures\\2025-09-云南",
  "output_path": "C:\\Users\\Eva\\Pictures\\归档",
  "options": {
    "big_trip_threshold_days": 30,
    "small_trip_threshold_hours": 2,
    "granularity": "city",
    "remark_template": "地点: {country}/{province}/{city}/{poi}\n行程: {trip_name}"
  }
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "preview": [
      {
        "original_path": "C:\\Users\\Eva\\Pictures\\2025-09-云南\\IMG_001.jpg",
        "target_path": "C:\\Users\\Eva\\Pictures\\归档\\2025-09_云南之旅\\01_昆明_0910-0913\\IMG_001.jpg",
        "trip_name": "01_昆明_0910-0913",
        "location": "云南省/昆明市"
      }
    ],
    "summary": {
      "total_files": 152,
      "trips_created": 5,
      "files_without_gps": 20,
      "files_needing_review": 5
    }
  }
}
```

### POST `/api/archive/execute`
执行归档（复制模式，不删除原文件）

**请求体**（同 preview）

**SSE 事件流**
```
data: {"type": "progress", "current": 10, "total": 152, "file": "IMG_001.jpg"}
data: {"type": "complete", "copied": 152, "failed": 0}
```

### POST `/api/archive/write-remarks`
为已归档文件写入备注字段

**请求体**
```json
{
  "trip_id": null,
  "remark_template": "地点: {country}/{province}/{city}/{poi}"
}
```

### POST `/api/archive/cleanup`
删除原始文件（用户二次确认后调用）

**请求体**
```json
{
  "source_folder": "C:\\Users\\Eva\\Pictures\\2025-09-云南",
  "confirm": true
}
```

---

## 地图接口

### GET `/api/map/html/{parent_trip_id}`
生成并返回交互式地图 HTML 内容

**查询参数**
- `map_tile`: `osm`（默认）或 `gaode`

**响应**：HTML 文本（`Content-Type: text/html`）

### GET `/api/map/locations/{parent_trip_id}`
获取行程的所有地点坐标（用于前端自定义地图渲染）

**响应**
```json
{
  "success": true,
  "data": {
    "locations": [
      {
        "trip_id": 2,
        "trip_name": "01_昆明_0910-0913",
        "lat": 25.0389,
        "lon": 102.7183,
        "photo_count": 32,
        "thumbnail_paths": ["C:\\...\\IMG_001.jpg", "..."]
      }
    ]
  }
}
```

---

## 媒体接口

### GET `/api/media/thumbnail`
返回压缩后的缩略图

**查询参数**
- `path`：图片完整路径（URL 编码）
- `width`：目标宽度（默认 400）
- `quality`：JPEG 质量（默认 75）

**响应**：JPEG 图片（`Content-Type: image/jpeg`）

### GET `/api/media/info`
获取单个文件的元数据

**查询参数**
- `path`：文件完整路径

**响应**
```json
{
  "success": true,
  "data": {
    "file_name": "IMG_001.jpg",
    "datetime_original": "2025-09-10T09:23:00",
    "latitude": 25.0389,
    "longitude": 102.7183,
    "location": "中国/云南省/昆明市/石林风景区",
    "has_gps": true,
    "file_size_mb": 4.2
  }
}
```

---

## 视频接口

### POST `/api/video/export`
导出 MP4 视频（长任务，SSE 推送）

**请求体**
```json
{
  "parent_trip_id": 1,
  "output_path": "C:\\Users\\Eva\\Desktop\\云南之旅.mp4",
  "options": {
    "resolution": "1920x1080",
    "fps": 30,
    "photos_per_location": 5,
    "photo_duration_seconds": 2,
    "include_title": true,
    "background_music_path": null
  }
}
```

**SSE 事件流**
```
data: {"type": "progress", "stage": "截图地图", "percent": 10}
data: {"type": "progress", "stage": "生成照片片段", "percent": 40}
data: {"type": "progress", "stage": "合成视频", "percent": 80}
data: {"type": "complete", "output_path": "C:\\Users\\Eva\\Desktop\\云南之旅.mp4"}
```

---

## 配置接口

### GET `/api/config`
获取当前配置

### PUT `/api/config`
更新配置

```json
{
  "gaode_api_key": "your_key_here",
  "default_big_trip_threshold_days": 30,
  "default_small_trip_threshold_hours": 2,
  "default_granularity": "city"
}
```

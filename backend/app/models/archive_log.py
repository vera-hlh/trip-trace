"""归档操作记录模型（本地日志）"""
from sqlalchemy import Column, Integer, String, Float, Boolean
from app.core.database import Base


class ArchiveLog(Base):
    __tablename__ = "archive_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 操作标识
    user_id = Column(String, default="local", nullable=False, index=True)
    created_at = Column(String, nullable=False)          # ISO8601 时间戳

    # 路径
    source_folder = Column(String, nullable=False)       # 源文件夹
    output_folder = Column(String, nullable=False)       # 输出目录

    # 文件统计
    photo_count = Column(Integer, default=0)             # 照片数量
    video_count = Column(Integer, default=0)             # 视频数量
    copied_count = Column(Integer, default=0)            # 实际复制数
    skipped_count = Column(Integer, default=0)           # 跳过（已存在）数
    error_count = Column(Integer, default=0)             # 失败数

    # 行程统计
    big_trips_count = Column(Integer, default=0)         # 大行程数
    sub_trips_count = Column(Integer, default=0)         # 子行程数

    # API 使用
    api_calls_used = Column(Integer, default=0)          # 高德 API 调用次数

    # 性能
    duration_sec = Column(Float, default=0.0)            # 归档耗时（秒）

    # 状态
    status = Column(String, default="success")           # "success" | "partial" | "failed"
    trip_log_generated = Column(Boolean, default=False)  # 是否生成了 trip_log.md
    remarks_written = Column(Integer, default=0)         # 写入备注的文件数

    # 归档时使用的参数（JSON 字符串）
    options_json = Column(String)                        # {"big_trip_days": 30, ...}

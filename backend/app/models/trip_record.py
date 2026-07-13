"""
我的旅迹：已归档大行程记录模型

每条记录对应归档执行时生成的一个"大行程"（BigTrip），
用于"我的旅迹"列表展示、排序、分页，以及后续生成海报。

与 ArchiveLog 的区别：
  - ArchiveLog：一次归档"执行"的技术统计日志（可能同时产生多个大行程）
  - TripRecord：每个"大行程"级别的用户可见记录（列表展示用）
"""
from sqlalchemy import Column, Integer, String, Text
from app.core.database import Base


class TripRecord(Base):
    __tablename__ = "trip_records"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String, default="local", nullable=False, index=True)

    # 大行程基本信息
    big_trip_name = Column(String, nullable=False)       # 最终显示名称（含用户重命名）
    start_date = Column(String)                          # 大行程起始日期 ISO8601（用于排序）
    end_date = Column(String)                            # 大行程结束日期 ISO8601
    sub_trip_count = Column(Integer, default=0)          # 子行程数量
    total_files = Column(Integer, default=0)             # 总文件数

    # 归档来源信息
    output_folder = Column(String)                       # 归档输出根目录
    big_trip_folder = Column(String)                     # 该大行程在输出目录下的文件夹名

    # 生成时间（记录创建时间，用于"生成时间"排序）
    created_at = Column(String, nullable=False)           # ISO8601

    # 子行程详情（JSON字符串），供阶段二生成海报时使用，避免归档后DB数据被清空无法回溯
    # 结构：[{"name": str, "location": str, "start_date": str, "end_date": str, "file_count": int}, ...]
    sub_trips_json = Column(Text)

    # 海报图片路径（阶段二填充，阶段一为空）
    poster_path = Column(String)

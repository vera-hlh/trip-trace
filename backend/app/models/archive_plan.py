"""归档方案（Archive Plan）数据模型

一次归档对应一个 ArchivePlan：

- PlanTrip 保存大行程 / 子行程树（parent_id 指向上层大行程）
- PlanFile 保存每个文件在方案中的目标相对路径与执行状态

设计原则：
- 方案是执行前唯一权威，execute 只消费方案，不再重算切分
- 方案可被用户编辑（重命名/合并/拆分/容器）
- 源目录变化时通过 source_snapshot 检测并使方案失效
"""
from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base


class ArchivePlan(Base):
    """一次归档方案（草稿 → 已执行 / 已放弃）"""

    __tablename__ = "archive_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, default="local", nullable=False, index=True)

    source_folder = Column(String, nullable=False)
    output_folder = Column(String, nullable=False)
    options_json = Column(Text)                 # 阈值、模式、备注模板等
    status = Column(String, default="draft", nullable=False, index=True)
    plan_version = Column(Integer, default=1, nullable=False)
    source_snapshot = Column(String)            # 文件集合哈希（路径+size+mtime）
    created_at = Column(String, nullable=False)
    executed_at = Column(String)


class PlanTrip(Base):
    """方案中的行程节点：大行程（kind=big）或子行程（kind=sub）"""

    __tablename__ = "plan_trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(
        Integer,
        ForeignKey("archive_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id = Column(
        Integer,
        ForeignKey("plan_trips.id", ondelete="CASCADE"),
        index=True,
    )

    kind = Column(String, nullable=False)       # "big" | "sub"
    folder_name = Column(String, nullable=False)
    display_name = Column(String)
    start_date = Column(String)
    end_date = Column(String)
    sequence_num = Column(Integer)
    location_label = Column(String)
    container_name = Column(String)             # 行程重建的容器层
    sort_order = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_plan_trips_plan_kind", "plan_id", "kind"),
    )


class PlanFile(Base):
    """方案中的单个文件：目标相对路径与执行状态"""

    __tablename__ = "plan_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(
        Integer,
        ForeignKey("archive_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_id = Column(
        Integer,
        ForeignKey("plan_trips.id", ondelete="SET NULL"),
        index=True,
    )
    media_file_id = Column(
        Integer,
        ForeignKey("files.id", ondelete="SET NULL"),
        index=True,
    )

    target_rel_path = Column(String, nullable=False)  # 相对 output_folder
    status = Column(String, default="pending", nullable=False, index=True)
    error = Column(Text)

    __table_args__ = (
        UniqueConstraint("plan_id", "media_file_id", name="uq_plan_file_media"),
        Index("ix_plan_files_plan_status", "plan_id", "status"),
    )

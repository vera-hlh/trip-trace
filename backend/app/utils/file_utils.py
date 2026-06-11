"""
文件操作工具

提供安全的文件复制、移动操作，以及操作日志记录。
设计原则：
  - 默认使用"复制"而非"移动"（保留原文件，由用户决定是否删除）
  - 每次操作写入日志，支持回滚
  - 自动处理目标路径冲突（重命名策略）
"""
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FileOperationResult:
    """文件操作结果"""
    source_path: str
    target_path: str
    success: bool
    error: Optional[str] = None
    file_size_bytes: int = 0


def ensure_dir(path: str) -> None:
    """确保目录存在（递归创建）"""
    os.makedirs(path, exist_ok=True)


def copy_file_safe(
    source: str,
    target: str,
    overwrite: bool = False,
    on_conflict: str = "rename",  # "rename" | "skip" | "overwrite"
) -> FileOperationResult:
    """
    安全复制文件

    Args:
        source: 源文件路径
        target: 目标文件路径
        overwrite: 是否覆盖（建议保持 False）
        on_conflict: 目标已存在时的策略
          - "rename": 自动重命名（IMG_001.jpg → IMG_001_1.jpg）
          - "skip": 跳过
          - "overwrite": 覆盖

    Returns:
        FileOperationResult
    """
    if not os.path.exists(source):
        return FileOperationResult(
            source_path=source,
            target_path=target,
            success=False,
            error=f"源文件不存在: {source}",
        )

    # 创建目标目录
    target_dir = os.path.dirname(target)
    try:
        ensure_dir(target_dir)
    except Exception as e:
        return FileOperationResult(
            source_path=source,
            target_path=target,
            success=False,
            error=f"创建目录失败: {e}",
        )

    # 处理目标文件已存在的情况
    actual_target = target
    if os.path.exists(target):
        if on_conflict == "skip":
            return FileOperationResult(
                source_path=source,
                target_path=target,
                success=True,  # 视为成功（跳过）
                error=None,
            )
        elif on_conflict == "rename":
            actual_target = _resolve_conflict(target)
        # on_conflict == "overwrite" 时直接继续

    try:
        shutil.copy2(source, actual_target)  # copy2 保留元数据时间戳
        file_size = os.path.getsize(actual_target)
        return FileOperationResult(
            source_path=source,
            target_path=actual_target,
            success=True,
            file_size_bytes=file_size,
        )
    except Exception as e:
        logger.error(f"复制文件失败 {source} → {actual_target}: {e}")
        return FileOperationResult(
            source_path=source,
            target_path=actual_target,
            success=False,
            error=str(e),
        )


def _resolve_conflict(path: str) -> str:
    """
    解决文件名冲突：自动添加数字后缀
    IMG_001.jpg → IMG_001_1.jpg → IMG_001_2.jpg → ...
    """
    p = Path(path)
    stem = p.stem
    suffix = p.suffix
    parent = p.parent

    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = str(parent / new_name)
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def delete_file_safe(file_path: str) -> bool:
    """
    安全删除文件（记录日志）

    Returns:
        True 成功，False 失败
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"已删除文件: {file_path}")
            return True
        return True  # 文件不存在视为成功
    except Exception as e:
        logger.error(f"删除文件失败 {file_path}: {e}")
        return False


def get_folder_stats(folder_path: str) -> dict:
    """
    获取文件夹统计信息

    Returns:
        {"total_files": N, "total_size_mb": N, "media_files": N}
    """
    from app.services.metadata_service import PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
    media_exts = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS

    total_files = 0
    media_files = 0
    total_size = 0

    for root, _, files in os.walk(folder_path):
        for f in files:
            full_path = os.path.join(root, f)
            total_files += 1
            try:
                total_size += os.path.getsize(full_path)
            except Exception:
                pass
            if Path(f).suffix.lower() in media_exts:
                media_files += 1

    return {
        "total_files": total_files,
        "media_files": media_files,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }

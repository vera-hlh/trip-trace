"""归档目标路径规则（M3）

策略：保留文件在源目录内的相对子路径，避免 DCIM 多子目录同名文件互相覆盖；
若仍然冲突（或用户重命名后冲突），在文件名后追加 `_1/_2`。
"""
import os


def source_relative_dir(source_folder: str, original_path: str) -> str:
    """返回文件在源目录内的相对目录；越界或无效时返回空串。"""
    if not source_folder or not original_path:
        return ""
    try:
        rel = os.path.relpath(original_path, source_folder)
    except (ValueError, OSError):
        return ""
    if rel in (".", "") or os.path.isabs(rel):
        return ""
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return ""

    rel_dir = os.path.dirname(rel)
    parts = [p for p in rel_dir.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return ""
    return os.path.join(*parts) if parts else ""


def unique_target(path: str, used: set[str]) -> str:
    """保证 path 在 used 中唯一；冲突时在扩展名前追加 _1/_2。"""
    key = path.casefold()
    if key not in used:
        used.add(key)
        return path

    base, ext = os.path.splitext(path)
    counter = 1
    while True:
        candidate = f"{base}_{counter}{ext}"
        candidate_key = candidate.casefold()
        if candidate_key not in used:
            used.add(candidate_key)
            return candidate
        counter += 1


def build_target_rel_path(
    big_folder: str,
    sub_folder: str,
    original_path: str,
    source_folder: str,
    file_name: str,
    used: set[str] | None = None,
    container_name: str = "",
) -> str:
    """生成相对 output_folder 的目标路径。"""
    parts = [big_folder]
    if container_name:
        parts.append(container_name)
    parts.append(sub_folder)
    rel_dir = source_relative_dir(source_folder, original_path)
    if rel_dir:
        parts.append(rel_dir)
    parts.append(file_name)
    path = os.path.join(*parts)
    return unique_target(path, used) if used is not None else path

"""Windows 目录名净化与校验（M3）"""
import os

INVALID_CHARS = set('<>:"/\\|?*')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_NAME_LENGTH = 120


def _strip_edges(name: str) -> str:
    # Windows 不允许目录名以空格或点结尾
    return (name or "").strip().rstrip(" .")


def _is_reserved(name: str) -> bool:
    # CON、CON.txt 等都算保留名
    return name.split(".")[0].upper() in RESERVED_NAMES


def sanitize_folder_name(name: str, fallback: str = "未命名") -> str:
    """把任意文本变成可用的 Windows 目录名（用于自动生成的名称）。"""
    value = _strip_edges(name)
    if not value:
        return fallback

    cleaned = "".join(
        "_" if (ch in INVALID_CHARS or ord(ch) < 32) else ch for ch in value
    )
    cleaned = _strip_edges(cleaned)
    if not cleaned:
        return fallback
    if _is_reserved(cleaned):
        cleaned = f"_{cleaned}"
    if len(cleaned) > MAX_NAME_LENGTH:
        cleaned = _strip_edges(cleaned[:MAX_NAME_LENGTH])
    return cleaned or fallback


def validate_folder_name(name: str) -> str:
    """校验用户输入；非法时抛 ValueError。"""
    value = _strip_edges(name)
    if not value:
        raise ValueError("不能为空")
    if any(ch in INVALID_CHARS or ord(ch) < 32 for ch in value):
        raise ValueError("含非法字符（<>:\"/\\|?* 或控制字符）")
    if _is_reserved(value):
        raise ValueError("是 Windows 保留名（CON/PRN/AUX/NUL/COM1…）")
    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"过长（>{MAX_NAME_LENGTH} 字符）")
    return value


def path_is_within(path: str, root: str) -> bool:
    """判断 path 是否位于 root 内（用于目标路径越界检查）。"""
    if not path or not root:
        return False
    try:
        target = os.path.abspath(path)
        base = os.path.abspath(root)
        return os.path.normcase(os.path.commonpath([base, target])) == os.path.normcase(base)
    except ValueError:
        return False

"""
应用配置（可通过环境变量/多个 .env 覆盖）

.env 查找顺序（后者覆盖前者）：
  1. 当前工作目录 .env（开发用）
  2. backend/.env
  3. %APPDATA%\\TripTrace\\.env
  4. TRIPRACE_ENV_FILE 指定的文件（最高优先级）
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    files: list[str] = [".env"]

    backend_dir = Path(__file__).resolve().parents[2]
    files.append(str(backend_dir / ".env"))

    appdata = os.environ.get("APPDATA")
    if appdata:
        files.append(str(Path(appdata) / "TripTrace" / ".env"))

    override = os.environ.get("TRIPRACE_ENV_FILE")
    if override:
        files.append(override)

    return tuple(dict.fromkeys(files))


class Settings(BaseSettings):
    app_name: str = "TripTrace"
    app_version: str = "0.1.0"
    backend_port: int = 17890

    # 数据库（实际路径由 core.database.resolve_db_path 决定）
    db_path: str = "triprace.sqlite"

    # 逆地理编码
    gaode_api_key: str = ""

    # 境外逆地理编码（公共 Nominatim 无需 Key；默认关闭，需显式开启）
    nominatim_enabled: bool = False
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "TripTrace/0.1 (local desktop app)"
    nominatim_email: str = ""
    nominatim_timeout_seconds: float = 10.0

    # 归档默认参数
    big_trip_threshold_days: int = 30
    small_trip_threshold_hours: int = 2
    default_granularity: str = "city"  # "city" | "poi"

    # 备注写入格式
    default_remark_template: str = "地点: {country}/{province}/{city}/{poi}"

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_prefix="TRIPRACE_",
        extra="ignore",
    )


settings = Settings()

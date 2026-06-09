"""
应用配置（可通过环境变量覆盖）
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "TripTrace"
    app_version: str = "0.1.0"
    backend_port: int = 17890

    # 数据库
    db_path: str = "triprace.sqlite"

    # 逆地理编码
    gaode_api_key: str = ""

    # 归档默认参数
    big_trip_threshold_days: int = 30
    small_trip_threshold_hours: int = 2
    default_granularity: str = "city"  # "city" | "poi"

    # 备注写入格式
    default_remark_template: str = "地点: {country}/{province}/{city}/{poi}"

    class Config:
        env_file = ".env"
        env_prefix = "TRIPRACE_"


settings = Settings()

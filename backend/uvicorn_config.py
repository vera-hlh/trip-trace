"""
uvicorn 开发服务器配置
使用方式: python uvicorn_config.py

优于直接调用 uvicorn app.main:app 的原因：
  - 排除 .venv 目录的文件监视（避免安装包时触发不必要的重启）
  - 统一端口配置
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=17890,
        reload=True,
        reload_excludes=[".venv", "__pycache__", "*.pyc", ".pytest_cache", "triprace.sqlite"],
        log_level="info",
    )

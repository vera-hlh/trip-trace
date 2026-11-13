"""统一日志格式（M5.2）"""
import logging


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_triptrace", False) for handler in root.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler._triptrace = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)

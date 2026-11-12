"""M3.2c：数据库路径、.env 加载与旧库迁移"""
from pathlib import Path

from app.core.config import Settings
from app.core.database import _migrate_legacy_db, resolve_db_path


def test_resolve_db_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "db.sqlite"
    monkeypatch.setenv("TRIPRACE_DB_PATH", str(target))
    assert resolve_db_path() == target


def test_resolve_db_path_defaults_to_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("TRIPRACE_DB_PATH", raising=False)
    assert resolve_db_path() == tmp_path / "TripTrace" / "triprace.sqlite"


def test_settings_reads_specified_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TRIPRACE_BACKEND_PORT=19999\n", encoding="utf-8")
    monkeypatch.delenv("TRIPRACE_BACKEND_PORT", raising=False)

    settings = Settings(_env_file=str(env_file))
    assert settings.backend_port == 19999


def test_legacy_db_is_copied_once(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "triprace.sqlite"
    legacy.write_bytes(b"legacy-db")
    target = tmp_path / "appdata" / "triprace.sqlite"

    _migrate_legacy_db(target)
    assert target.exists()
    assert target.read_bytes() == b"legacy-db"

    # 目标已存在时不再覆盖
    target.write_bytes(b"new-db")
    _migrate_legacy_db(target)
    assert target.read_bytes() == b"new-db"


def test_env_files_include_backend_dir():
    from app.core.config import _env_files

    files = _env_files()
    assert any(Path(p).name == ".env" for p in files)
    assert any("backend" in str(Path(p)) or str(Path(p)).endswith("backend\\.env") for p in files)


def test_env_file_override_is_last(monkeypatch, tmp_path):
    from app.core.config import _env_files

    override = tmp_path / "custom.env"
    monkeypatch.setenv("TRIPRACE_ENV_FILE", str(override))
    assert _env_files()[-1] == str(override)

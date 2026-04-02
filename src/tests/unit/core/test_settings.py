from pathlib import Path

from ii_agent.core.config.settings import Settings


def test_env_overrides_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET_KEY=from-dotenv\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JWT_SECRET_KEY", "from-env")

    settings = Settings()

    assert settings.jwt_secret_key == "from-env"


def test_sync_database_url_strips_async_drivers():
    settings = Settings(database={"database_url": "postgresql+asyncpg://u:p@localhost/db"})

    assert settings.sync_database_url == "postgresql://u:p@localhost/db"


def test_workspace_root_falls_back_to_storage_path(tmp_path):
    missing_root = tmp_path / "missing" / "workspace"
    fallback_store = tmp_path / "storage"

    settings = Settings(
        workspace_path=str(missing_root),
        use_container_workspace=True,
        storage={"file_store_path": str(fallback_store)},
    )

    resolved = Path(settings.workspace_root)

    assert resolved.exists()
    assert resolved == (fallback_store / "workspace").resolve()

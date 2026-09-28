"""Runtime configuration, read from ``MOODY_*`` environment variables or a ``.env`` file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    return Path.home() / ".local" / "share" / "moody"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOODY_", env_file=".env", extra="ignore")

    data_dir: Path = _default_data_dir()
    models_dir: Path = Path.home() / ".cache" / "moody" / "models"
    library_path: Path | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'moody.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

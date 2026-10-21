"""Configuración por entorno. Nada de secretos en el código."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"), env_prefix="BU_", extra="ignore"
    )

    #: PostgreSQL es el modo de referencia; SQLite el de arranque cero.
    #: Ver docs/adr/0002-persistencia-dual-y-gis-diferido.md
    database_url: str = Field(default=f"sqlite+pysqlite:///{REPO_ROOT / 'data' / 'baseball.db'}")
    #: Enlazado a loopback a propósito: esto no se expone a internet.
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default=["http://127.0.0.1:5173", "http://localhost:5173"])
    log_level: str = "INFO"
    fixture_path: Path = REPO_ROOT / "data" / "fixtures" / "places.json"
    default_currency: str = "MXN"
    #: Tope de días que un solo comando `advance` puede recorrer.
    max_advance_days: int = 400
    #: Guardar el detalle turno a turno multiplica el tamaño de la base; por
    #: omisión se guarda solo de los partidos más recientes.
    store_game_events: bool = True
    game_event_retention_days: int = 30
    sql_echo: bool = False

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()

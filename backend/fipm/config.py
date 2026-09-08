"""Application settings, env prefix FIPM_.

DECLARATION_STATUSES is the single source of truth for the allowed values of
the free-text "status" field inside a FIP's `answers` JSON. It will be
replaced by the enum finalised in docs/specs/00-fip-ontology-mapping.md; until
then this tuple is authoritative and nothing else may hard-code the values.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/fipm/config.py -> backend/fipm -> backend -> repo root. FIPM_DB_PATH
# and FIPM_DATA_DIR default relative to the repo root (not the process cwd),
# so `cd backend && uv run python -m fipm ...` finds ../data and ../fipm.db
# regardless of where it's invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DECLARATION_STATUSES: tuple[str, ...] = (
    "current",
    "planned",
    "planned-development",
    "planned-replacement",
    "none",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIPM_", env_file=".env", extra="ignore")

    base_url: str = "http://localhost:8000"
    db_path: str = str(_REPO_ROOT / "fipm.db")
    secret_key: str = "dev-secret-change-me"
    id_prefix: str = ""
    admin_email: str | None = None
    admin_password: str | None = None
    default_language: str = "en"
    data_dir: str = str(_REPO_ROOT / "data")
    static_dir: str = "./static"
    session_ttl_days: int = 14
    cookie_secure: bool = True
    allowed_origins: str = ""
    registration_open: bool = True
    env: str = "development"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def check_production_safety(self) -> None:
        """Refuse to start with an insecure default secret key in production."""
        if self.env == "production" and self.secret_key == "dev-secret-change-me":
            raise RuntimeError(
                "FIPM_SECRET_KEY must be set to a non-default value when FIPM_ENV=production"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()

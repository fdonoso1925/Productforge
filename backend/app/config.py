from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuración desde variables de entorno (ver .env.example en la raíz)."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # "production" activa las validaciones de arranque y apaga /docs y /openapi.json.
    environment: str = "development"

    # Freno ante loops en los endpoints con IA (no es una cuota de costo; ver app/security.py).
    rate_limit_per_minute: int = 30
    rate_limit_per_hour: int = 300
    max_body_bytes: int = 1_000_000

    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    allowed_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    anthropic_api_key: str = ""
    claude_model_outline: str = "claude-sonnet-5-5"
    claude_model_content: str = "claude-sonnet-5-5"
    claude_effort: str = "high"

    prompts_dir: Path = BACKEND_DIR.parent / "prompts"
    templates_dir: Path = BACKEND_DIR.parent / "templates"
    ad_templates_dir: Path = BACKEND_DIR.parent / "ad_templates"

    # true: el worker de jobs corre dentro de la API (desarrollo). En producción, proceso aparte.
    worker_inline: bool = False

    # URL pública del frontend: a dónde vuelve el navegador tras autorizar Google Drive.
    frontend_url: str = "http://localhost:3000"

    # Google Drive (OAuth de Google). Credenciales de un cliente "Aplicación web" en Cloud Console.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/storage/drive/callback"
    # Clave Fernet que cifra los tokens OAuth en la base.
    token_encryption_key: str = ""

    # Creativos para Meta Ads: proveedores de imagen (claves solo en el backend).
    # El orden manda; sin clave un proveedor queda fuera. Gemini no tiene cuota gratis para
    # imágenes: solo se usa si `gemini_daily_usd_cap` > 0 (tope diario en USD, 0 = apagado).
    image_providers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["pixabay"])
    gemini_api_key: str = ""
    pixabay_api_key: str = ""
    gemini_image_model: str = "gemini-3.1-flash-lite-image"
    gemini_image_price_usd: float = 0.034
    gemini_daily_usd_cap: float = 0.0

    @field_validator("allowed_emails", "cors_origins", "image_providers", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("allowed_emails")
    @classmethod
    def _lower(cls, value: list[str]) -> list[str]:
        return [email.lower() for email in value]

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()

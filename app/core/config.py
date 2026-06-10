from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/rayna_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    SECRET_KEY: str = "change-me-to-a-random-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Ahrefs
    AHREFS_API_TOKEN: str = ""

    # Apify
    APIFY_API_TOKEN: str = ""

    # SearchAPI
    SEARCHAPI_KEY: str = ""

    # Freepik
    FREEPIK_API_KEY: str = ""

    # Pexels
    PEXELS_API_KEY: str = ""

    # Unsplash
    UNSPLASH_ACCESS_KEY: str = ""

    # OpenAI (embeddings only)
    OPENAI_API_KEY: str = ""

    # Google (Geocoding API)
    GOOGLE_API_KEY: str = ""

    # Playwright
    PLAYWRIGHT_HEADLESS: bool = True

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str = ""

    # Cloudinary (temporary — used when IMAGE_STORAGE=cloudinary)
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Toggle: "s3" or "cloudinary"
    IMAGE_STORAGE: str = "cloudinary"

    # App
    ENVIRONMENT: str = "dev"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()

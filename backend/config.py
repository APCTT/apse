from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    KOREA_NTB_API_KEY: str
    KOREA_NTB_BASE_URL: str
    KOREA_NTB_TTL_SECONDS: int = 86400
    CACHE_TTL_SECONDS: int = 86400
    IP_AUSTRALIA_CLIENT_ID: str = ""
    IP_AUSTRALIA_CLIENT_SECRET: str = ""
    JPO_API_USERNAME: str = ""
    JPO_API_PASSWORD: str = ""
    JPO_TOKEN_URL: str = "https://ip-data.jpo.go.jp/auth/token"

    model_config = {"env_file": ".env"}


settings = Settings()

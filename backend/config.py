from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    KOREA_NTB_API_KEY: str = ""
    KOREA_NTB_BASE_URL: str = "https://apis.data.go.kr/B552536/tech_4/techall"
    KOREA_NTB_TTL_SECONDS: int = 86400
    CACHE_TTL_SECONDS: int = 86400
    CACHE_MAX_ENTRIES: int = 500
    IP_AUSTRALIA_CLIENT_ID: str = ""
    IP_AUSTRALIA_CLIENT_SECRET: str = ""
    JPO_API_USERNAME: str = ""
    JPO_API_PASSWORD: str = ""
    JPO_TOKEN_URL: str = "https://ip-data.jpo.go.jp/auth/token"
    # Optional semantic search. The application remains fully functional
    # without a Gemini key and falls back to the existing keyword search.
    GEMINI_API_KEY: str = ""
    GEMINI_RELATED_TERMS_MODEL: str = "gemini-3.5-flash-lite"
    SEMANTIC_SEARCH_ENABLED: bool = True
    SEMANTIC_SEARCH_MODEL: str = "gemini-embedding-001"
    SEMANTIC_SEARCH_DIMENSIONS: int = 768
    SEMANTIC_SEARCH_DB_PATH: str = "backend/cache/semantic_search.db"
    SEMANTIC_SEARCH_MIN_SCORE: float = 0.55
    SEMANTIC_SEARCH_DAILY_QUERY_LIMIT: int = 800

    model_config = {"env_file": ".env"}


settings = Settings()

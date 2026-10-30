import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://betapp:betapp@localhost:5432/betapp"
    secret_key: str = "change-me-in-production-please"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    admin_email: str = "admin@example.com"
    admin_password: str = ""
    admin_nickname: str = "Admin"
    debug: bool = False
    football_api_key: str = ""
    football_api_host: str = "v3.football.api-sports.io"
    # Optional FootyStats API key (from https://footystats.org/api).
    # If set, the API is used as a fallback when HTML scraping is blocked.
    # The API may not provide Over 1.5 frequency stats (uses defaults).
    footystats_api_key: str = ""
    # Optional HTTP/HTTPS proxy used when fetching from sources that block
    # datacenter IPs (e.g. Cloudflare in front of FootyStats on Render).
    # Format: "http://user:pass@host:port" or "socks5://host:port".
    # Leave empty to fetch directly.
    proxy_url: str = ""
    # Groq is the AI used to read match pages when API-Football has no result.
    # It only extracts facts from text the app already downloaded - it is never
    # asked to "know" a score, so it cannot invent one.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        extra = "ignore"

settings = Settings()
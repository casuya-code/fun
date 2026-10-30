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
    # Groq is the AI used to read match pages when API-Football has no result.
    # It only extracts facts from text the app already downloaded - it is never
    # asked to "know" a score, so it cannot invent one.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        extra = "ignore"

settings = Settings()
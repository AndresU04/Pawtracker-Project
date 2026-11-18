"""Configuration. All secrets/settings come from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    JWT_EXPIRES_MINUTES = int(os.environ.get("JWT_EXPIRES_MINUTES", "60"))
    CACHE_BACKEND = os.environ.get("CACHE_BACKEND", "none")  # none | memory | redis
    REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "60"))


class TestConfig(Config):
    """Used by pytest. Isolated in-memory SQLite; never touches real data."""

    TESTING = True
    SECRET_KEY = "test-secret-key-that-is-long-enough-for-hs256"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    JWT_EXPIRES_MINUTES = 5
    CACHE_BACKEND = "memory"
    CACHE_TTL_SECONDS = 60


config_by_name = {
    "development": Config,
    "production": Config,
    "testing": TestConfig,
}

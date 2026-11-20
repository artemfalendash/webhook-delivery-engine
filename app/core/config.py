'''
What the hell is config.py for?
config.py reads your .env file and turns it into a strongly typed Python object using pydantic-settings.

Without config.py: You have to type os.getenv("DATABASE_URL") 20 times across 10 files. If you misspell it once, your app fails silently in production.

With config.py: You define your environment variables in one place using Pydantic. When the app starts, Pydantic checks your .env file. 
If a required secret or DB URL is missing, it crashes immediately with a clear error before serving any requests.


It looks like this:

# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()





Then anywhere in your app, you just write from app.core.config import settings and access settings.DATABASE_URL with full autocomplete.



'''








from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()








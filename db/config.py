from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://uscode:uscode@localhost:5432/uscode"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    GEMINI_API_KEY: str
    APP_ENV: str = "development"
    DB_PATH: str = "pulse_ledger.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

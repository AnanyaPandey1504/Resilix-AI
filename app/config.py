from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    RAZORPAY_KEY_ID: str = "rzp_test_placeholder"
    RAZORPAY_KEY_SECRET: str = "placeholder_secret"
    RAZORPAY_WEBHOOK_SECRET: str = "rzp_webhook_secret_pulse_2026"
    GEMINI_API_KEY: str = "placeholder_gemini_key"
    APP_ENV: str = "development"
    DB_PATH: str = "pulse_ledger.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal
import os

class Settings(BaseSettings):
    # Mode
    AGENT_MODE: Literal["persona", "event", "auto"] = Field(
        default="persona",
        description="Active operating mode: 'persona' (digital twin) or 'event' (organizing committee) or 'auto'"
    )
    USER_NAME: str = Field(default="Subho", description="Owner name for the persona twin (e.g., Subho)")

    # LLM Settings
    LLM_PROVIDER: Literal["gemini", "openai"] = "gemini"
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    GEMINI_MODEL: str = "gemini-1.5-flash"
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key (optional alternative)")
    OPENAI_MODEL: str = "gpt-4o-mini"

    # WhatsApp Provider: "green_api", "twilio", "meta", or "auto"
    WHATSAPP_PROVIDER: Literal["green_api", "twilio", "meta", "auto"] = "green_api"

    # Green API (https://green-api.com/en/docs/)
    GREEN_API_INSTANCE_ID: str = Field(default="", description="Green API Instance ID (e.g., 7103...)")
    GREEN_API_API_TOKEN_INSTANCE: str = Field(default="", description="Green API Token Instance")
    GREEN_API_HOST: str = Field(default="https://api.green-api.com", description="Green API base host URL")

    # WhatsApp / Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""

    # Meta WhatsApp Cloud API (Alternative)
    WHATSAPP_CLOUD_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "twin_agent_verify_token"

    # Email / SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    NOTIFICATION_EMAIL_TO: str = ""
    NOTIFICATION_FROM_NAME: str = "Twin & Event Agent"

    # Smart Hybrid Batching & Digest
    DIGEST_INTERVAL_SECONDS: int = 300  # 5 minutes
    DIGEST_BATCH_SIZE: int = 10         # flush immediately if 10 unnotified FAQs pile up

    # Database
    DB_PATH: str = os.path.join(os.path.dirname(__file__), "twin_agent.db")

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

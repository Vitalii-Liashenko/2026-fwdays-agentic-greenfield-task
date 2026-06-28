import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in .env")

# PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "tracker_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "tracker_password")
DB_NAME = os.getenv("DB_NAME", "expense_tracker")

# Build connection string
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Category vocabulary (from AGENTS.md)
VALID_CATEGORIES = {
    "Продукти",
    "Транспорт",
    "Кафе/Ресторани",
    "Комуналки",
    "Розваги",
    "Здоров'я",
    "Покупки",
    "Інше",
}

# Confidence threshold for soft-fail
CONFIDENCE_THRESHOLD = 0.7

# Max retries on hard-fail
MAX_RETRIES = 3

# LLM model
LLM_MODEL = "gpt-4o-mini"

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# xAI Grok
XAI_API_KEY = os.getenv("XAI_API_KEY")

# Google AI (Gemini)
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data.db")

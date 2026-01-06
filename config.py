import os

# Optional dependency: python-dotenv
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

# Load environment variables from .env file
if load_dotenv:
    load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-dev-key-change-in-prod")
    DB_NAME = os.getenv("CUTTING_DB_PATH", "cutting_web_data.db")

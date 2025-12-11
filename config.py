import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-dev-key-change-in-prod")
    DB_NAME = os.getenv("CUTTING_DB_PATH", "cutting_web_data.db")

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 398783184  # Замените на свой Telegram ID 

DB_TYPE = os.getenv('DB_TYPE', 'sqlite')  # 'sqlite' или 'postgres'

# Для SQLite
SQLITE_PATH = os.path.abspath(os.getenv('SQLITE_PATH', './events.db'))

# Для PostgreSQL
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'events') 
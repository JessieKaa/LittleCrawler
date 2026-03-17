import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

# 加载.env文件
load_dotenv(PROJECT_ROOT / ".env")

# 数据库配置
MYSQL_DB_USER = os.getenv("MYSQL_DB_USER", "root")
MYSQL_DB_PWD = os.getenv("MYSQL_DB_PWD", "root")
MYSQL_DB_HOST = os.getenv("MYSQL_DB_HOST", "127.0.0.1")
MYSQL_DB_PORT = os.getenv("MYSQL_DB_PORT", 3306)
MYSQL_DB_NAME = os.getenv("MYSQL_DB_NAME", "xhs_crawler")
SQLITE_DB_PATH = os.path.join(PROJECT_ROOT, "database", "sqlite_tables.db")
DB_TYPE = os.getenv("DB_TYPE", "mysql")

# 监听配置
POLL_INTERVAL = int(os.getenv("LLM_POLL_INTERVAL", 10))
BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", 10))

# LLM配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 4000
LLM_TIMEOUT = 360
MAX_RETRIES = 3
RETRY_DELAY = 2

# 提示词文件
PROMPT_FILE = os.path.join(os.path.dirname(__file__), "prompt.txt")

# 日志配置
LOG_DIR = os.path.join(PROJECT_ROOT, "llm_processor", "logs")
LOG_LEVEL = "INFO"

# 状态文件
STATE_FILE = os.path.join(PROJECT_ROOT, "llm_processor", "state.json")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

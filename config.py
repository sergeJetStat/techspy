import os
from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DB_PATH = os.getenv("DB_PATH", "techspy.db")
MAX_CONCURRENT_CRAWLS = int(os.getenv("MAX_CONCURRENT_CRAWLS", "20"))
CRAWL_TIMEOUT = int(os.getenv("CRAWL_TIMEOUT", "15"))

# Use Playwright (headless browser) for crawling — catches dynamic/GTM scripts.
# Set USE_PLAYWRIGHT=0 to fall back to HTTP-only mode (faster, less RAM).
USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "1") != "0"
CONFIDENCE_THRESHOLD = int(os.getenv("CONFIDENCE_THRESHOLD", "60"))

# Model settings
MODEL = "claude-opus-4-6"
MAX_TOKENS = 4096

# Queue settings
QUEUE_MAX_SIZE = 1000
UNKNOWN_SIGNALS_THRESHOLD = 10  # trigger Detection Agent after N unknown signals

# Crawl tiers (days between recrawls)
CRAWL_TIERS = {
    1: 7,    # top 100K domains — weekly
    2: 14,   # top 1M domains — biweekly
    3: 30,   # rest — monthly
}

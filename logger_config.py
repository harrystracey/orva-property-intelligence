"""
Centralized logging configuration for Palm Jumeirah Intelligence System
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Create logs directory
LOGS_DIR = Path(__file__).parent / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Log file with date
LOG_FILE = LOGS_DIR / f"palm_jumeirah_{datetime.now().strftime('%Y%m%d')}.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Reduce console verbosity: only WARNING and above to stdout
_root = logging.getLogger()
for h in _root.handlers:
    if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout:
        h.setLevel(logging.WARNING)
        break


def get_logger(name):
    """Get a logger for a specific module."""
    return logging.getLogger(name)


app_logger = get_logger('app')
data_logger = get_logger('data_processor')
ai_logger = get_logger('ai')
scraper_logger = get_logger('scraper')

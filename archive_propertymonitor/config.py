"""Configuration loader for Property Research Agent."""

from dotenv import load_dotenv
import os
import sys

load_dotenv()

# Credentials
PROPERTYMONITOR_EMAIL = os.getenv("PROPERTYMONITOR_EMAIL")
PROPERTYMONITOR_PASSWORD = os.getenv("PROPERTYMONITOR_PASSWORD")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def validate_config():
    """Validate all required environment variables are present."""
    missing = []
    
    if not PROPERTYMONITOR_EMAIL:
        missing.append("PROPERTYMONITOR_EMAIL")
    if not PROPERTYMONITOR_PASSWORD:
        missing.append("PROPERTYMONITOR_PASSWORD")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    
    if missing:
        print("❌ ERROR: Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\n📝 Instructions:")
        print("   1. Open the .env file in this project folder")
        print("   2. Add: ANTHROPIC_API_KEY=your_key_here")
        print("   3. Get your API key from: https://console.anthropic.com/")
        sys.exit(1)
    
    print("✅ Configuration validated successfully")
    return True


# Scraping settings - human-like delays to avoid bot detection
HUMAN_DELAYS = {
    'min_typing_delay': 0.05,    # 50ms between keystrokes
    'max_typing_delay': 0.15,    # 150ms between keystrokes
    'min_action_delay': 1.0,     # 1 second between actions
    'max_action_delay': 3.0,     # 3 seconds between actions
    'page_load_timeout': 30000,  # 30 seconds
}

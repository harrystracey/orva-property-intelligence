# AI Property Research Agent

AI-powered PropertyMonitor.ae scraper for Palm Jumeirah market intelligence.

Uses **Claude AI** to intelligently navigate the website and extract property data based on natural language queries.

## Features

- 🔐 Automatic login to PropertyMonitor.ae
- 🤖 AI-powered page navigation and data extraction
- 🔍 Natural language queries (e.g., "What's the service charge for Tiara?")
- 🛡️ Anti-bot detection evasion with human-like behavior
- 📊 Streamlit web interface

## Setup Instructions

### 1. Install Dependencies

```bash
cd property_research_agent
pip install -r requirements.txt
```

### 2. Install Playwright Browser

```bash
playwright install chromium
```

### 3. Configure API Key

Edit the `.env` file and add your Anthropic API key:

```env
PROPERTYMONITOR_EMAIL=harry@edwardsandtowers.com
PROPERTYMONITOR_PASSWORD=P0GBAtrix!
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Get your API key from:** https://console.anthropic.com/

### 4. Run the Application

```bash
streamlit run research_app.py
```

## Example Queries

| Query | What It Does |
|-------|--------------|
| "What's the service charge for Tiara?" | Finds service charge data for Tiara Residences |
| "Recent sales in Oceana" | Shows recent sale transactions in Oceana |
| "Rental transactions in Shoreline 5" | Finds rental data for Al Hallawi (Shoreline 5) |
| "Average price per sqft in Azure" | Extracts pricing data for Azure Residences |

## Building Name Reference

### Shoreline Apartments (Arabic → English)

| Arabic Name | English Name |
|-------------|--------------|
| Al Basri | Shoreline 1-3 |
| Al Dawaar | Shoreline 4 |
| Al Hallawi | Shoreline 5 |
| Al Msalli | Shoreline 6 |
| Al Nabat | Shoreline 7 |
| Al Sultana | Shoreline 8 |
| Al Thamam | Shoreline 9 |
| Al Das | Shoreline 10 |
| Al Khushkar | Shoreline 11 |
| Al Janahi | Shoreline 12 |
| Al Majara | Shoreline 13 |
| Al Fahad | Shoreline 14 |
| Al Fattan | Shoreline 15 |
| Al Shirawi | Shoreline 16 |
| Al Ramth | Shoreline 17 |
| Al Hamri | Shoreline 18 |
| Al Hatmi | Shoreline 19 |
| Al Seef / Al Merkad | Shoreline 20 |

### Other Palm Jumeirah Buildings

- Tiara Residences
- Azure Residences
- Oceana (Atlantic, Pacific, Southern, Caribbean)
- Anantara Residences
- Kempinski Residences
- Fairmont Residences
- Serenia Residences
- Balqis Residences
- Palm Beach Towers
- Golden Mile
- Marina Residences

## How It Works

1. **Browser Launch**: Opens a real Chrome browser (visible for debugging)
2. **Login**: AI finds and fills login form automatically
3. **Query Analysis**: Claude extracts building name and data type from your question
4. **Navigation**: AI navigates to the relevant page/section
5. **Data Extraction**: Claude reads the page and extracts the answer
6. **Response**: Returns formatted answer to your query

## Troubleshooting

### "Missing Anthropic API Key"
- Open `.env` file
- Add your key: `ANTHROPIC_API_KEY=sk-ant-...`
- Get key from: https://console.anthropic.com/

### "Login Failed"
- Check PropertyMonitor credentials in `.env`
- Website may have changed - check browser window for errors

### "Browser Won't Open"
- Run: `playwright install chromium`
- Ensure no firewall blocking

## Security Notes

- 🔒 Credentials stored locally in `.env` (never committed to git)
- 🛡️ `.gitignore` prevents credential leaks
- 🔐 API keys never sent to third parties

## File Structure

```
property_research_agent/
├── research_app.py      # Streamlit web interface
├── scraper_agent.py     # AI browser automation
├── config.py            # Configuration loader
├── requirements.txt     # Python dependencies
├── .env                 # Credentials (DO NOT SHARE)
├── .gitignore           # Prevents credential commits
└── README.md            # This file
```

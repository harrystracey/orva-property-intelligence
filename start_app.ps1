# ============================================================================
# Palm Jumeirah Lead Tool - Startup Script
# Double-click this file to start the app with API key pre-configured
# ============================================================================

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Palm Jumeirah Lead Search Tool" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to script directory first
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

Write-Host "  Working directory: $scriptPath" -ForegroundColor Yellow
Write-Host ""

# Load API key from .env file
$envFile = Join-Path $scriptPath ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.+?)\s*$') {
            $key = $matches[1]
            $value = $matches[2]
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
            if ($key -eq "ANTHROPIC_API_KEY") {
                $env:ANTHROPIC_API_KEY = $value
            }
        }
    }
} else {
    Write-Host "  WARNING: .env file not found at $envFile" -ForegroundColor Yellow
    Write-Host "  Create a .env file with ANTHROPIC_API_KEY=your-key-here" -ForegroundColor Yellow
}

# Verify API key is set
if ($env:ANTHROPIC_API_KEY) {
    Write-Host "  API Key configured" -ForegroundColor Green
} else {
    Write-Host "  API Key not set - AI features will not work" -ForegroundColor Red
}

Write-Host ""

# Check if Streamlit is installed
$streamlitCheck = Get-Command streamlit -ErrorAction SilentlyContinue
if (-not $streamlitCheck) {
    Write-Host "  Streamlit not found. Installing..." -ForegroundColor Red
    pip install streamlit pandas openpyxl anthropic python-dotenv --break-system-packages
    Write-Host ""
}

# Start Streamlit
Write-Host "  Starting Streamlit server..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  The app will open in your browser automatically." -ForegroundColor Gray
Write-Host "  If not, open: http://localhost:8501" -ForegroundColor Gray
Write-Host ""
Write-Host "  Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

streamlit run app.py

# Keep window open if there's an error
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  An error occurred. Press any key to exit..." -ForegroundColor Red
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

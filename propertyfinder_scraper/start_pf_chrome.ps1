# Launch Chrome with debug port for PropertyFinder + Replit scraper.
# Opens PropertyFinder search and Replit app in two tabs.
# Run this first; log in to Replit app and set your PropertyFinder search, then run the scraper.

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProfileDir = Join-Path (Join-Path $ScriptDir "..") "scraped_data\pf_chrome_profile"
$Port = 9222

$ChromePaths = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)
$Chrome = $null
foreach ($p in $ChromePaths) {
    if (Test-Path $p) { $Chrome = $p; break }
}
if (-not $Chrome) {
    $Chrome = "chrome.exe"
}

Write-Host "Starting Chrome (PropertyFinder profile) on port $Port..."
& $Chrome --remote-debugging-port=$Port --user-data-dir="$ProfileDir" `
    "https://www.propertyfinder.ae/en/search?l=2&c=2&fu=0&rp=y&ob=mr" `
    "https://property-scraper-towersdubai.replit.app/"

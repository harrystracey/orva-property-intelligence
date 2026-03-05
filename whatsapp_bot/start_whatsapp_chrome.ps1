# Launch Chrome with a dedicated profile for WhatsApp Web (session persists).
# First run: Chrome opens WhatsApp; log in once. Next runs: already logged in.
# Run this BEFORE running the campaign.

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProfileDir = Join-Path $ScriptDir "whatsapp_chrome_profile"
$Port = 9222

# Chrome path (Windows)
$ChromePaths = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)
$Chrome = $null
foreach ($p in $ChromePaths) {
    if (Test-Path $p) { $Chrome = $p; break }
}
if (-not $Chrome) {
    $Chrome = "chrome.exe"   # hope it's in PATH
}

Write-Host "Starting Chrome (WhatsApp profile) on port $Port..."
& $Chrome --remote-debugging-port=$Port --user-data-dir="$ProfileDir" "https://web.whatsapp.com"

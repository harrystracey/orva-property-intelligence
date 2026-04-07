@echo off
echo Starting Chrome with remote debugging on port 9222...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --remote-allow-origins=* ^
  --user-data-dir="C:\Users\thema\AppData\Local\Google\Chrome\User Data" ^
  --profile-directory="Profile 9" ^
  --no-first-run ^
  --no-default-browser-check ^
  "https://insight.reidin.com/home/dashboard/1147"
echo Chrome launched. Wait for Reidin to load, then run:
echo   python reidin_extractor.py --type rentals
pause

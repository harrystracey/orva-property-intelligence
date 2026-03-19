# Microsoft's official Playwright Python image ships: Python 3.11, Chromium, Xvfb, all system deps
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn python-dotenv playwright==1.58.0

COPY whatsapp_bot/playwright_server/server.py .

EXPOSE 3001
# Start Xvfb virtual display at :99 before launching the server
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & sleep 1 && python server.py"]

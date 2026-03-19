# Microsoft's official Playwright Python image ships: Python 3.11, Chromium, Xvfb, all system deps
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn python-dotenv playwright==1.58.0

COPY whatsapp_bot/playwright_server/server.py .

EXPOSE 3001
CMD ["python", "server.py"]

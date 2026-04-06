FROM python:3.11-slim

WORKDIR /app

# Avoid apt in this image to prevent Windows/WSL apt networking instability during build.
# API requirements here install from Python wheels and do not require extra OS packages.

# Install API dependencies
COPY orva_api/requirements.txt /app/orva_api/requirements.txt
RUN pip install --no-cache-dir -r orva_api/requirements.txt

# Copy all project code (existing modules + API)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "orva_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 curl && \
    rm -rf /var/lib/apt/lists/*

# Install API dependencies
COPY orva_api/requirements.txt /app/orva_api/requirements.txt
RUN pip install --no-cache-dir -r orva_api/requirements.txt

# Copy all project code (existing modules + API)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "orva_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

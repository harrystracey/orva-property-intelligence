FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user so we never run the API as root.
RUN groupadd --system --gid 1001 orva && \
    useradd --system --uid 1001 --gid orva --create-home orva

# Install API dependencies as root so pip caches cleanly.
COPY orva_api/requirements.txt /app/orva_api/requirements.txt
RUN pip install --no-cache-dir -r orva_api/requirements.txt

# Copy all project code (existing modules + API)
COPY --chown=orva:orva . .

USER orva

EXPOSE 8000

# Health check hits /api/health (unauthenticated endpoint). curl is already
# installed via apt-get above.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail --silent --show-error http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "orva_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

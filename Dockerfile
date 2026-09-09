# Portable image: works on Fly.io, Railway, Render, Cloud Run — anywhere that
# runs a container and sets $PORT.
#
# Python 3.12 rather than 3.14: every dependency has a prebuilt linux wheel
# there, so the build stays fast and doesn't need a compiler.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so edits to the agent code don't reinstall the world.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workout_agent/ ./workout_agent/
COPY ui/ ./ui/
COPY serve_ui.py .

# The API key is injected as an env var by the platform's secret store.
# .dockerignore keeps the local .env out of the image.
EXPOSE 8080
CMD ["python", "serve_ui.py"]

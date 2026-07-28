FROM python:3.12-slim

RUN pip install --no-cache-dir uv

# Keep the venv outside /app so the docker-compose dev bind mount
# (.:/app) doesn't shadow it with the host's (possibly absent/foreign) .venv.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

EXPOSE 8000

CMD ["uv", "run", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

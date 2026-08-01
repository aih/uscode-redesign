FROM python:3.12-slim

RUN pip install --no-cache-dir uv

# `ingest mirror push/pull` shells out to the aws CLI (ingest/mirror.py); in
# production the container reads credentials from the EC2 instance role via
# IMDSv2, which requires HttpPutResponseHopLimit=2 on the instance (docs/deploy.md).
RUN pip install --no-cache-dir awscli

# Keep the venv outside /app so the docker-compose dev bind mount
# (.:/app) doesn't shadow it with the host's (possibly absent/foreign) .venv.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

EXPOSE 8000

# --proxy-headers: behind a proxy, request.url.scheme must be the client's, not
# this hop's — the Secure cookie decision reads it (ADR-0019).
CMD ["uv", "run", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", \
     "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

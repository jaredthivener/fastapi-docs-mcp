FROM python:3.14-alpine AS builder

ENV UV_SYSTEM_PYTHON=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN apk add --no-cache curl ca-certificates

RUN curl -Ls https://astral.sh/uv/install.sh | sh

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY main.py /app/main.py

RUN uv sync --no-dev

FROM python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN adduser -D -u 10001 appuser
USER appuser

COPY --from=builder /app /app

CMD ["python", "main.py"]
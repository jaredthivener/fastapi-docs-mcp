# Base image pinned by digest (not just tag) so a build is reproducible and
# dependabot's "docker" ecosystem can track/bump the pin like every other
# dependency in this repo (uv.lock, github-actions).
FROM python:3.14-alpine@sha256:3f818d6811ff5f3f2b5e5d836df3d25c2dd2e588d3b4981338a8ba17e422f74f AS builder

ENV UV_SYSTEM_PYTHON=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apk add --no-cache ca-certificates

# uv itself comes from its official distroless image (digest-pinned), not a
# curl-piped-to-shell installer script — no remote script execution, and the
# pin is one more thing dependabot can track.
COPY --from=ghcr.io/astral-sh/uv:0.12.4@sha256:d0a6eca6c669dc7e9c51218707b8438a3d30402733d739dcc00adb3e213e8f5c /uv /uvx /bin/

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY main.py /app/main.py
COPY src /app/src

RUN uv sync --no-dev

FROM python:3.14-alpine@sha256:3f818d6811ff5f3f2b5e5d836df3d25c2dd2e588d3b4981338a8ba17e422f74f

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN adduser -D -u 10001 appuser
USER appuser

COPY --from=builder /app /app

CMD ["python", "main.py"]

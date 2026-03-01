FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

COPY src/ src/
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "--directory", "src", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

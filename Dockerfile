# Application plane image (Chapter 3). The Linnet API, mock
# providers A and B and the orders service share it; Compose sets
# each service's command. Versions follow versions.toml.
FROM python:3.14.7-slim
RUN pip install --no-cache-dir uv==0.11.7
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src ./src
COPY services ./services
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:/app" \
    PYTHONUNBUFFERED=1
USER 10001

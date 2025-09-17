FROM python:3.11.13-slim AS uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

COPY uv.lock pyproject.toml /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --no-editable

COPY ./src /app/src
COPY README.md ./README.md
COPY LICENSE LICENSE
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.11.13-slim

# Create a non-root user for security
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# Copy virtual environment and change ownership to app user
COPY --from=uv --chown=app:app /app/.venv /app/.venv

# Ensure executables in the venv take precedence over system executables
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER app

# when running the container, add --db-path and a bind mount to the host's db file
ENTRYPOINT ["mcp-docker-server"]

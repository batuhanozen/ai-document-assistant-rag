FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DATA_DIR=/app/data
WORKDIR /app
ARG INSTALL_AI=false
COPY pyproject.toml README.md LICENSE ./
COPY app ./app
RUN if [ "$INSTALL_AI" = "true" ]; then pip install '.[ai]'; else pip install .; fi \
    && useradd --create-home --uid 10001 assistant \
    && mkdir /app/data && chown assistant:assistant /app/data
USER assistant
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]

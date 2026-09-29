# FC Middleware: Django API, Celery worker/beat and the sales sync, in one image.

# ---- Build stage: compile wheels that need headers (mysqlclient) ----
FROM python:3.10-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.8.17

COPY requirements.txt /tmp/requirements.txt
RUN uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r /tmp/requirements.txt

# ---- Runtime stage ----
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime client library for mysqlclient only; no compilers in the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .
# static/ is filled by collectstatic at start-up; logs/ and reports/ are written by the sales sync.
RUN mkdir -p static media logs reports && chown -R app:app static media logs reports

USER app
EXPOSE 8000

CMD ["gunicorn", "middleware.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]

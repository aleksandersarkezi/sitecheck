# syntax=docker/dockerfile:1

# ---- build stage: turn the source into a wheel --------------------------------
FROM python:3.13-slim AS build

WORKDIR /src
RUN pip install --no-cache-dir build==1.2.2
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

# ---- runtime stage: only the installed package, no build tools --------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SITECHECK_DB=/data/sitecheck.db

# Unprivileged user with a fixed UID so volume permissions are predictable.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /nonexistent --shell /usr/sbin/nologin app \
 && mkdir -p /data \
 && chown app:app /data

COPY --from=build /dist/*.whl /tmp/
RUN WHEEL="$(ls /tmp/*.whl)" \
 && pip install "${WHEEL}[service]" \
 && rm /tmp/*.whl

USER app
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"]

# --proxy-headers: trust X-Forwarded-For so rate limiting sees the real visitor
# IP. Safe here because port 8000 is never published; only Caddy can reach it.
# --no-server-header: don't advertise "uvicorn" (sitecheck itself flags that).
CMD ["uvicorn", "sitecheck.service.app:create_app_from_env", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--no-server-header", "--workers", "1"]

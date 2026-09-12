# syntax=docker/dockerfile:1
#
# Single backend image, used by BOTH the `api` and `worker` Compose services
# (spec/local-dev.md L1, L4; spec/backend.md B2).
#
# Layout produced here:
#   /srv/app            -> the installed application package (`app.main`, `app.worker`,
#                           `app.seed_demo` are importable from WORKDIR /srv)
#   /srv/alembic.ini    -> script_location = migrations
#   /srv/migrations     -> Alembic revisions
#   /data/private       -> private file storage (FILE_STORAGE_ROOT), a mounted volume
#
# All of these are valid from WORKDIR /srv:
#   uvicorn app.main:app --host 0.0.0.0 --port 8000
#   python -m app.worker
#   python -m app.seed_demo
#   alembic upgrade head
#
# No secret and no .env file is baked in; configuration arrives at run time via
# Compose `env_file` (see .env.example and .dockerignore).

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# OS packages for the scan path (spec/backend.md B4, spec/local-dev.md L4).
#   tesseract-ocr{,-fra,-ara,-eng} : OCR engine + the OCR_LANGUAGES=fra+ara+eng data files
#   libjpeg62-turbo, zlib1g        : JPEG/Flate image streams for Pillow / pdfplumber
#   libfreetype6                   : glyph rasterisation used by Pillow and reportlab exports
#   libopenjp2-7                   : JPEG 2000 image streams that appear in scanned PDFs
# pypdfium2 ships a self-contained pdfium wheel, and psycopg is installed as a
# binary wheel, so no PDF or libpq build dependency is needed. TLS roots for a
# possible AI_MODE=live provider call already come from the base image.
# apt lists are removed in the same layer.
RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      tesseract-ocr \
      tesseract-ocr-fra \
      tesseract-ocr-ara \
      tesseract-ocr-eng \
      libjpeg62-turbo \
      zlib1g \
      libfreetype6 \
      libopenjp2-7 \
 && rm -rf /var/lib/apt/lists/*

# Non-root runtime account, created before the copies so files land owned by it.
RUN groupadd --system --gid 10001 appsrv \
 && useradd --system --uid 10001 --gid 10001 \
      --no-create-home --shell /usr/sbin/nologin appsrv

WORKDIR /srv

# Dependencies first: this layer is cached until requirements.txt changes.
COPY --chown=appsrv:appsrv requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# Then the application itself: backend/ -> /srv, so backend/app -> /srv/app.
COPY --chown=appsrv:appsrv . /srv

# FILE_STORAGE_ROOT. A fresh named volume mounted here inherits this ownership,
# so the non-root user can write private case files.
RUN mkdir -p /data/private \
 && chown -R appsrv:appsrv /data

USER appsrv

EXPOSE 8000

# `worker` overrides this with `python -m app.worker` in compose.yaml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

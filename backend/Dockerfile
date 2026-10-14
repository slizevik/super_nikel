FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && python -m pip install -r requirements.txt

RUN python -m pip install --force-reinstall --no-deps \
    --index-url https://download.pytorch.org/whl/cpu torchvision

RUN set -eux; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources; \
    for attempt in 1 2 3; do \
        if apt-get -o Acquire::Retries=5 update \
            && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
                libgl1 \
                libglib2.0-0 \
                libxcb1 \
                libreoffice-writer; then \
            break; \
        elif [ "$attempt" -eq 3 ]; then \
            exit 1; \
        else \
            sleep 10; \
        fi; \
    done; \
    rm -rf /var/lib/apt/lists/*

COPY alembic.ini ./alembic.ini
COPY backend ./backend

WORKDIR /app/backend

EXPOSE 8000

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_EXTRA_INDEX_URL=https://d33sy5i8bnduwe.cloudfront.net/simple/

WORKDIR /app

# System deps for psycopg2, PyGithub SSL, git, ...
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip first so all installers see PIP_EXTRA_INDEX_URL
RUN pip install --upgrade pip setuptools wheel

# Install app dependencies. PIP_EXTRA_INDEX_URL (set above) makes
# emergentintegrations resolvable from the Emergent private index.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt \
    && pip install 'gradio==4.44.1' 'huggingface_hub<0.26'

COPY backend  /app/backend
COPY frontend /app/frontend
COPY policy   /app/policy

EXPOSE 8001 3000

# Default command runs the backend; docker-compose overrides for the gradio service
CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8001"]

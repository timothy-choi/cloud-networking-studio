# Production API image — FastAPI + Uvicorn (see docs/DEPLOYMENT.md for compose and EC2).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Docker socket workflows (deploy to host engine) typically require root or docker group — see DEPLOYMENT.md.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

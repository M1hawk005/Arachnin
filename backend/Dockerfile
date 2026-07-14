FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN addgroup --system arachnin && adduser --system --ingroup arachnin arachnin

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --requirement requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

USER arachnin
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

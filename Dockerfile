FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html ./
COPY static/ ./static/

RUN useradd -m -u 1000 keywave && chown -R keywave:keywave /app
USER keywave

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3).status==200 else 1)"

# Production runtime: gunicorn + single gevent-websocket worker (in-memory room state).
CMD ["gunicorn", "--worker-class", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", \
     "-w", "1", "--bind", "0.0.0.0:5000", "--access-logfile", "-", \
     "--error-logfile", "-", "app:app"]

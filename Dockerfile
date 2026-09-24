FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt && useradd --uid 10001 --create-home nmea && mkdir /data && chown nmea:nmea /data
COPY --chown=nmea:nmea app ./app
COPY --chown=nmea:nmea scripts ./scripts
COPY --chown=nmea:nmea samples ./samples
USER nmea
EXPOSE 8080/tcp 10110/udp
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]

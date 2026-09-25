FROM node:22-bookworm-slim AS cesium-assets
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt && useradd --uid 10001 --create-home nmea && mkdir /data && chown nmea:nmea /data
COPY --chown=nmea:nmea app ./app
COPY --from=cesium-assets --chown=nmea:nmea /web/node_modules/cesium/Build/Cesium ./app/static/cesium
COPY --from=cesium-assets --chown=nmea:nmea /web/node_modules/cesium/LICENSE.md ./app/static/cesium/LICENSE.md
COPY --chown=nmea:nmea scripts ./scripts
COPY --chown=nmea:nmea samples ./samples
USER nmea
EXPOSE 80/tcp 10110/udp 10111/tcp
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:80/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "1", "--no-access-log"]

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
RUN pip install --no-cache-dir numpy==2.3.5 && useradd --uid 10004 --create-home sdrtx && mkdir /data && chown sdrtx:sdrtx /data
COPY sdr-tx/modulator.py sdr-tx/server.py ./
COPY emulator/ais_suite.py emulator/ais-all-types.log ./
COPY sdr-tx/static ./static
USER sdrtx
EXPOSE 80 1235 10113/tcp 10113/udp
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost/health',timeout=2)"
CMD ["python","server.py"]

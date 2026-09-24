FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10002 -m sim
COPY --chown=sim:sim server.py ./server.py
COPY --chown=sim:sim static ./static
USER sim
EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"
CMD ["python","-m","uvicorn","server:app","--host","0.0.0.0","--port","8090","--workers","1"]

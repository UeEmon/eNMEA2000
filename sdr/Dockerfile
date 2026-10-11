FROM debian:bookworm-slim AS engine-build
ARG AIS_CATCHER_COMMIT=8833c64b3da0c42e9a724b9bd13eaab2fffadcca
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl cmake g++ make pkg-config librtlsdr-dev libusb-1.0-0-dev && rm -rf /var/lib/apt/lists/*
RUN curl -fL --retry 3 https://github.com/jvde-github/AIS-catcher/archive/${AIS_CATCHER_COMMIT}.tar.gz -o /source.tar.gz && mkdir /source && tar -xzf /source.tar.gz --strip-components=1 -C /source
RUN cmake -S /source -B /build -DRTLSDR=ON -DAIRSPY=OFF -DAIRSPYHF=OFF -DHACKRF=OFF -DHYDRASDR=OFF -DSDRPLAY=OFF -DSOXR=OFF -DSAMPLERATE=OFF -DZMQ=OFF -DPSQL=OFF -DSQLITE=OFF -DOPENSSL=OFF -DZLIB=OFF -DNMEA2000=OFF -DWEBVIEWER=OFF && cmake --build /build --parallel 2

FROM python:3.12-slim-bookworm AS router
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN useradd --uid 10003 --create-home sdr && mkdir /data /iq && chown sdr:sdr /data
COPY core.py engine.py service.py ./
USER sdr
CMD ["python", "service.py"]

FROM router AS receiver
USER root
RUN apt-get update && apt-get install -y --no-install-recommends librtlsdr0 libusb-1.0-0 && rm -rf /var/lib/apt/lists/*
COPY --from=engine-build /build/AIS-catcher /usr/local/bin/AIS-catcher
COPY --from=engine-build /source.tar.gz /usr/share/ais-catcher/source.tar.gz
USER sdr
ENV SDR_ROLE=receiver

FROM nginx:1.28-alpine AS web
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY static /usr/share/nginx/html

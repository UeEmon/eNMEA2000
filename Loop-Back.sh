#!/usr/bin/env bash
# Start everything at once: main app, NMEA emulator, AIS SDR receiver/transmit emulator and
# ADS-B (adsb/, formerly the eADS-B2000 repository; ADSB_ENABLE=0 skips ADS-B).
# Prints the admin tokens at the end (SHOW_TOKENS=0 hides them).
set -Eeuo pipefail
# Real RTL-SDR (optional; one dongle per band, so AIS and ADS-B together need two):
#   AIS_RTL_TCP=host.docker.internal:1234   rtl_tcp -a 0.0.0.0 -p 1234 -f 162000000 -s 1536000 -d 0
#   ADSB_RTL_TCP=host.docker.internal:1237  rtl_tcp -a 0.0.0.0 -p 1237 -f 1090000000 -s 2000000 -d 1
# Host ports 1235/1236 belong to the AIS and ADS-B transmit emulators.
# Extra outputs besides the main app (kept on re-run, also editable in the SDR receiver UI):
#   AIS_OUTPUTS=udp://192.168.1.30:10110,tcp://192.168.1.31:10111   (AIS NMEA to iPads etc.)
#   ADSB_OUTPUTS=tcp://host.docker.internal:10111,udp://192.168.1.30:10110   ($PADSB to iPads too; read by adsb/)
AIS_OUTPUTS="${AIS_OUTPUTS:-}"
AIS_RTL_TCP="${AIS_RTL_TCP:-}"
ADSB_RTL_TCP="${ADSB_RTL_TCP:-}"
host_port='^[A-Za-z0-9._-]+:[0-9]{1,5}$'
for value in "$AIS_RTL_TCP" "$ADSB_RTL_TCP"; do
  if [ -n "$value" ] && ! [[ "$value" =~ $host_port ]]; then
    printf 'AIS_RTL_TCP/ADSB_RTL_TCP は host:port の形式で指定してください: %s\n' "$value" >&2
    exit 1
  fi
done
cd "$(dirname "$0")"
ROOT="$PWD"
phase='Dockerの確認'
trap 'printf "起動に失敗しました: %s。既に起動したコンテナと保存データは保持しています。\n" "$phase" >&2' ERR

command -v docker >/dev/null || { printf 'Dockerをインストールして起動してください。\n' >&2; exit 1; }
docker info >/dev/null
docker compose version >/dev/null

phase='設定ファイルの作成'
if [ ! -f .env ] || [ ! -f sdr/.env ] || [ ! -f sdr-tx/.env ]; then
  # Match the host user so mode-0600 secrets remain readable on Linux.
  docker run --rm --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$ROOT,target=/work" -w /work \
    python:3.12-slim python -c \
    'import runpy; [runpy.run_path(p, run_name="__main__") for p in ("scripts/setup.py", "sdr/setup.py", "sdr-tx/setup.py")]'
fi

compose_in() (
  cd "$ROOT/$1"
  shift
  docker compose -f compose.yaml "$@"
)

# Validate every project's own .env before starting any of the stacks.
for project in . emulator sdr sdr-tx adsb; do
  phase="$project のCompose設定確認"
  compose_in "$project" config --quiet
done
for project in . emulator sdr sdr-tx; do
  phase="$project の起動"
  printf '\n起動中: %s\n' "$project"
  compose_in "$project" up -d --build --wait
done

phase='SDR連接設定'
compose_in . exec -T app python - main < scripts/configure-sdr-chain.py
compose_in sdr-tx exec -T modulator python - transmitter-config < scripts/configure-sdr-chain.py
compose_in emulator exec -T emulator python - emulator < scripts/configure-sdr-chain.py
compose_in sdr exec -T -e AIS_RTL_TCP="$AIS_RTL_TCP" -e AIS_OUTPUTS="$AIS_OUTPUTS" nmea-router python - receiver < scripts/configure-sdr-chain.py
if [ -z "$AIS_RTL_TCP" ]; then
  compose_in sdr-tx exec -T modulator python - transmitter-start < scripts/configure-sdr-chain.py
fi

# ADS-B (adsb/): simulator -> transmit emulator -> receiver -> $PADSB to TCP 10111.
adsb_started=''
if [ "${ADSB_ENABLE:-1}" != 0 ]; then
  phase='ADS-Bの起動'
  printf '\n起動中: adsb\n'
  if [ -n "$ADSB_RTL_TCP" ]; then
    # Real dongle: only the receiver, reading I/Q from rtl_tcp.
    ADSB_INPUT=--rtltcp ADSB_SOURCE="$ADSB_RTL_TCP" compose_in adsb up -d --build --wait --no-deps receiver
  else
    compose_in adsb up -d --build --wait
  fi
  adsb_started=1
fi

printf '\n全環境の起動が完了しました。既定の接続先:\n'
printf '  本体             http://localhost:18081  (.env の APP_TOKEN)\n'
printf '  NMEAエミュレータ http://localhost:8090\n'
printf '  SDR受信部        http://localhost:18082  (sdr/.env の SDR_TOKEN)\n'
printf '  SDR送信模擬部    http://localhost:18083  (sdr-tx/.env の SDR_TX_TOKEN)\n'
printf 'ポートを変更済みの場合は各Compose設定の公開ポートを使用してください。\n'
if [ -n "$AIS_RTL_TCP" ]; then
  printf 'AIS: 実機RTL-SDR（rtl_tcp %s, 162 MHz）→ SDR受信部 → TCP:10111 → 本体。SDR受信は開始済みです。\n' "$AIS_RTL_TCP"
else
  printf '連接: NMEAエミュレータ → TCP:10113 → SDR送信模擬部 → RTL-TCP:1235 → SDR受信部 → TCP:10111 → 本体\n'
  printf 'SDR受信と変調は開始済みです。NMEAエミュレータのWeb画面でデータ送信を開始してください。\n'
fi
if [ -n "$adsb_started" ] && [ -n "$ADSB_RTL_TCP" ]; then
  printf 'ADS-B: 実機RTL-SDR（rtl_tcp %s, 1090 MHz）→ ADS-B受信部 → $PADSB TCP:10111 → 本体。\n' "$ADSB_RTL_TCP"
elif [ -n "$adsb_started" ]; then
  printf 'ADS-B: シミュレータ → SDR送信模擬部（RTL-TCP:1236）→ ADS-B受信部 → $PADSB TCP:10111 → 本体。航空機は地図に表示されます。\n'
  printf '  ADS-Bシミュレータ http://localhost:8091  (複数機の諸元を一括設定)\n'
else
  printf 'ADS-B環境は起動していません（ADSB_ENABLE=0）。\n'
fi

if [ "${SHOW_TOKENS:-1}" != 0 ]; then
  bash "$ROOT/scripts/show-tokens.sh"
else
  printf '\n管理トークンは bash scripts/show-tokens.sh で表示できます。\n'
fi

#!/usr/bin/env bash
# Print the admin tokens from the generated .env files (bash scripts/show-tokens.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
env_value() { [ -f "$ROOT/$1" ] && sed -n "s/^$2=//p" "$ROOT/$1" | tail -n 1 || printf '（%s が未作成）' "$1"; }
printf '\n管理トークン（他人に見せないでください。各画面のログインに使います）:\n'
printf '  本体          http://localhost:18081  APP_TOKEN     %s\n' "$(env_value .env APP_TOKEN)"
printf '  SDR受信部     http://localhost:18082  SDR_TOKEN     %s\n' "$(env_value sdr/.env SDR_TOKEN)"
printf '  SDR送信模擬部 http://localhost:18083  SDR_TX_TOKEN  %s\n' "$(env_value sdr-tx/.env SDR_TX_TOKEN)"
printf '  NMEAエミュレータ（http://localhost:8090）とADS-B環境はトークン不要です。\n'

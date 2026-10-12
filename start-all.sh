#!/usr/bin/env bash
# Start the main application and all three standalone test/receiver stacks.
set -Eeuo pipefail
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
for project in . emulator sdr sdr-tx; do
  phase="$project のCompose設定確認"
  compose_in "$project" config --quiet
done
for project in . emulator sdr sdr-tx; do
  phase="$project の起動"
  printf '\n起動中: %s\n' "$project"
  compose_in "$project" up -d --build --wait
done

printf '\n全環境の起動が完了しました。既定の接続先:\n'
printf '  本体             http://localhost:18081  (.env の APP_TOKEN)\n'
printf '  NMEAエミュレータ http://localhost:8090\n'
printf '  SDR受信部        http://localhost:18082  (sdr/.env の SDR_TOKEN)\n'
printf '  SDR送信模擬部    http://localhost:18083  (sdr-tx/.env の SDR_TX_TOKEN)\n'
printf 'ポートを変更済みの場合は各Compose設定の公開ポートを使用してください。\n'
printf '受信・変調・試験データ送信は各Web画面で開始してください。\n'

# 独立Docker TCPエミュレータ

本体システムを起動した後、プロジェクトのルートで `docker compose -f emulator/compose.yaml up -d --build --wait` を実行します。エミュレータ画面は `http://localhost:8090` です。

Web画面で緯度・経度、対地速度（ノット）、針路（度）、AIS船舶数（1～20）、送信間隔（0.2～60秒）、GPS／AISの出力を指定できます。「送信開始・設定反映」を押すと、指定した値からNMEA0183のRMC/GGAとAIS Type 1/5を生成し、TCP 10111へCRLF区切りで連続送信します。停止するとTCP接続を閉じます。接続先は環境変数 `NMEA_TARGET_HOST` と `NMEA_TARGET_PORT` で指定します。

別のComposeプロジェクトとして起動し、独立したDockerネットワークから `host.docker.internal:10111` に接続します。`extra_hosts: host-gateway` はLinuxのGitHub Actionsでも同じ経路を使うための指定です。Web UIは既定でローカルホストのみに公開します。接続先のアドレスをWeb画面から変更する機能は設けていません。

端末のPython 3.12から `python scripts/smoke_emulator.py` で2つのCompose間のTCP送信・AIS位置情報保存を検証できます。用途はシステム試験です。実際のAIS送信器ではありません。

# NMEA Observatory — NMEA0183解析Webシステム

AWS運用とDocker Desktopでの確認に対応する初期実装です。
UDP受信・ファイル解析・データ保存・WebSocketライブ表示に共通の解析エンジンを使います。
画面は日本語で、PC／スマートフォンの両方に対応します。

## 1. Docker Desktopで起動

前提：Docker Desktopを起動し、Linuxコンテナを使用してください。
Windowsでは本フォルダでPowerShellを開き、次を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

macOS／Linux：

```bash
bash start.sh
```

1. 初回のみイメージのダウンロードとビルドを行います。インターネット接続が必要です。
2. `http://localhost:8080` を開きます。
3. 自動生成された `.env` の `APP_TOKEN=` 以降をログイン画面に入力します。
4. `.env` は秘密情報です。共有用ZIPやGitに含めないでください。

Pythonが端末に入っていなくても起動スクリプトを利用できます。
コマンドが失敗した場合は、`docker compose logs --tail=100` で確認してください。
Webは既定で端末内のみ、UDPは端末の全IPv4インターフェースで待ち受けます。
LAN内の別端末から画面を確認する場合、`.env` の `WEB_BIND=0.0.0.0` に変更して再起動してください。
AWSではHTTPSを使用します。

## 2. 動作確認

コンテナ内から受信・保存・ファイル解析を確認：

```bash
docker compose exec app python scripts/smoke.py
```

サンプルUDPを連続送信：

```bash
docker compose --profile demo up -d simulator
```

停止：

```bash
docker compose --profile demo stop simulator
```

`simulator` はDocker内部ネットワークで送信します。Docker Desktopの公開UDPポートの確認には、端末にPythonがある場合、次を使います。

```bash
python scripts/send_udp.py --host 127.0.0.1 --repeat
```

外部NMEA機器からは、**Docker Desktop端末のLAN側IPアドレス、UDP 10110** にユニキャスト送信します。
端末のファイアウォールで、対象ネットワークからのUDP 10110受信を許可してください。
初期版ではブロードキャスト／マルチキャスト参加は実装していません。

ファイル解析は画面で `samples/demo.log` を選択します。
このファイルは意図的なチェックサム不正を1件含みます。正常40件の位置センテンス、AIS Type 5の分割2行、エラー1行から構成されます。
結果は正常41件、断片待機1件、エラー1件です。「断片待機」は受信時点の履歴であり、後で再構成が完了してもその履歴は書き換えません。

## 3. 実装内容

| 機能 | 動作 |
|---|---|
| UDP | 10110/UDP、送信元ごとの処理、有界キュー、受信停止・再開 |
| NMEA | チェックサム検証、pynmea2による対応センテンス解析、GP/GN等のトーカ識別 |
| 位置 | GGA/RMC/GLL等の有効位置、RMCから日付付きUTC時刻を抽出 |
| AIS | pyaisで対応するVDM/VDOを解析。1/2/3/5/18/19/21/24等を含む。分割再構成とタイムアウト |
| ファイル | 最大100 MB、同時2件、進捗・停止・結果保持。行単位のTXT/LOG/NMEA/CSV内のセンテンス抽出 |
| 記録 | 元センテンス、受信・解析時刻、送信元、チェックサム結果、解析属性、位置、MMSI |
| データベース | Docker/AWSはPostgreSQL 17。軽量テスト用にSQLiteにも対応 |
| 画面 | 受信統計、最新500件、入力／文字列フィルター、解析詳細、位置・航跡プロット |
| 配信 | WebSocket。切断後の再接続、配信遅延時の最新履歴再取得 |
| 出力 | JSONL全項目、GeoJSON位置情報。APIでsource/MMSIによる絞り込み可 |
| 認証 | ランダムトークンでログイン、有効期限12時間の署名Cookie、Origin検査 |
| 保持 | Dockerボリューム／AWS EBS、ファイルジョブ情報。中断ジョブは再起動時に明示 |

未知センテンスは `unsupported` として原文・フィールドを残します。未知のメッセージまで意味解析できるという保証ではありません。
AIVDM/AIVDO Type 6/8等のアプリケーション固有バイナリは、ライブラリが提供する範囲の属性・バイト列を保持します。

## 4. データ処理上のルール

- UDPデータグラムに複数センテンスがある場合は、それぞれ保存します。
- センテンス単位の送信を前提とし、任意のUDPデータグラムをまたぐ文字列の結合はしません。IPフラグメントはOSの処理範囲です。
- AIS分割は送信元IP/ポート・トーカ・チャネル・シーケンス番号・総断片数をキーにします。UDPは30秒、ファイルは3600秒の処理時間で期限切れにします。
- 識別子なしのAIS分割は順序通りの到着を前提とします。同一送信元・チャネルで識別子なしの複数メッセージが交錯すると完全な識別はできません。
- ファイルごとに独立した再構成器を使います。別ファイルやライブ受信の断片は結合しません。
- 先頭断片を受信していない後続AIS断片はエラーとします。順序逆転を万能に復元する処理ではありません。
- NMEAチェックサム必須。欠落、不正、位置未取得の状態は記録します。有効測位でないGGA/RMC/GLLは位置表示しません。
- `received_at` はサーバ受信／ファイル解析時刻。`event_time` は日付のあるRMC等から確定できる場合のみです。
- ファイル先頭の独自タイムスタンプやCSVの時刻列は自動で日時として採用しません。AISの秒フィールドだけから絶対日時を推測しません。
- ファイルは入力順に処理します。UTC日時のないデータを恣意的に時刻ソートしません。
- UDPの欠落数はNMEA文字列だけでは確定できません。画面の破棄数はアプリのキュー上限／DB失敗／配信破棄で検知できた分です。
- 元データ保存後に画面へ配信します。ブラウザは最新500件だけ保持し、GeoJSON/JSONLはDBの履歴を逐次出力します。
- 位置画面は簡易座標プロットです。海図・背景地図・正しい距離縮尺を提供するGISではなく、日付変更線をまたぐ航跡には未対応です。

## 5. 起動・停止・保存

```bash
docker compose stop
docker compose start
docker compose logs --tail=100 app
docker compose down
```

`down` は通常、名前付きボリュームを保持します。`down -v` は保存データを削除するため通常運用では使わないでください。
UDP受信器とAIS断片状態を単一プロセスで管理するため、**Uvicorn workers=1** とします。
複数プロセス・複数EC2へ増やす場合は受信器の独立化、共有キュー、DB・配信の分離が必要です。

バックアップ（bash環境）：

```bash
bash scripts/backup.sh
```

`nmea.dump` はPostgreSQLカスタム形式、`raw-data.tar.gz` は取り込んだファイルです。
厳密に対応したバックアップが必要な場合は、シミュレーターを止め、UDPを停止し、全インポート完了後に実行してください。
空の復元先DBでの例：

```bash
docker compose stop app
docker compose exec -T db pg_restore -U nmea -d nmea --no-owner < backups/YOUR_BACKUP/nmea.dump
docker compose run --rm --no-deps -T app tar -C /data -xzf - < backups/YOUR_BACKUP/raw-data.tar.gz
docker compose start app
```

既存データのあるDBへ上書きするコマンドは含めていません。復元先は別の新規環境を使ってください。
保存期限・自動パージは初期版では未実装です。空き容量を監視して定期的にバックアップしてください。

## 6. AWSへの配置

詳細は [aws/README.md](aws/README.md) を参照してください。
AWS側も同じDockerイメージ・同じPostgreSQLメジャーバージョンを使います。
この配布物はAWSのリソースを自動で作成したものではなく、構築に必要なコードを含むものです。

## 7. 開発・テスト

Python 3.12で：

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
cfn-lint aws/cloudformation.json
```

テストはSQLiteを使用し、UDPソケット、WebSocket、ファイル入力、永続化を確認します。
Docker Desktop／PostgreSQL／AWSでの実行結果と区別した検証記録は [VERIFICATION.md](VERIFICATION.md) に記載しています。

## 8. 初期版の範囲外

背景地図、KML/KMZ/CZML、履歴アニメーション、AIS静的情報の船舶マスタへの統合、国籍別統計、複数UDPポート、複数ユーザー権限、保存期間の自動管理、高可用性、10万隻規模の性能保証は次段階です。
AIS Type 24のPart A/Bは個別イベントとして保持し、船舶マスタへの統合は未実装です。
再起動時にAISの未完了断片は保持しません。

## 9. 参照資料

- [Dockerポート公開](https://docs.docker.com/engine/network/port-publishing/)
- [AWS ALBリスナーとWebSocket](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-listeners.html)
- [AWS Network Load BalancerのUDP対応](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/load-balancer-listeners.html)
- [pyais](https://github.com/M0r13n/pyais)
- [FastAPI](https://fastapi.tiangolo.com/)

NMEA0183規格そのものの全文は同梱していません。利用ライブラリの対応範囲は規格全項目の適合認証とは異なります。

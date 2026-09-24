# 検証記録

2026-09-24時点。

| 項目 | 結果 |
|---|---|
| Python 3.12 pytest | 13件成功。GIS航路追従・経路編集API、UDP/TCP実ソケット、WebSocket、ファイル入力、AIS分割と期限切れ、GPS、JSONL/GeoJSON、ログイン、SQLite永続化 |
| Pythonコンパイル・JS構文・bash構文 | 成功 |
| CloudFormation cfn-lint | 成功。テンプレートの静的検証 |
| GitHub Actions | PR #1の初回実行でPythonジョブとDockerジョブがともに成功。DockerジョブではPostgreSQL、UDP、ファイル解析、GeoJSONのスモーク試験を実行。最新のCIで両ジョブ成功。独立ComposeからTCP→PostgreSQL、航路追従、Cesium素材配信、Chromiumで地図クリックによる航路点・開始位置設定を確認 |
| Docker Compose実行 | GitHub ActionsのUbuntu上で起動・スモーク成功。この実行環境にはDocker Engineがなく、ユーザー端末のDocker Desktopでの確認は未実施 |
| PostgreSQL結合 | 初期版はGitHub ActionsのDockerスモークで成功。最新のCIで再実行成功。この環境のpytestはSQLiteを使用 |
| AWS実デプロイ | 認証されたAWSアカウント、VPC、2つのサブネット、ACM証明書、許可するCIDRが未指定のため未実施 |
| ブラウザ視覚検証 | GitHub ActionsのChromium/PlaywrightでCesium表示、航路点・開始位置のクリック設定を確認。この環境ではブラウザ実体を取得できず、Docker Desktop端末での目視確認は未実施 |

注意：本ファイルの「成功」は上記の実行条件で観測した結果であり、Docker Desktop／AWSでの動作実績を意味しません。

# 検証記録

2026-09-24時点。

| 項目 | 結果 |
|---|---|
| Python 3.12 pytest | 10件成功。UDP/TCP実ソケット、WebSocket、ファイル入力、AIS分割と期限切れ、GPS、JSONL/GeoJSON、ログイン、SQLite永続化 |
| Pythonコンパイル・JS構文・bash構文 | 成功 |
| CloudFormation cfn-lint | 成功。テンプレートの静的検証 |
| GitHub Actions | PR #1の初回実行でPythonジョブとDockerジョブがともに成功。DockerジョブではPostgreSQL、UDP、ファイル解析、GeoJSONのスモーク試験を実行。Cesium/TCPエミュレータ追加後のCIでも両ジョブ成功。独立ComposeからのTCP→PostgreSQL連接とCesium素材配信を確認 |
| Docker Compose実行 | GitHub ActionsのUbuntu上で起動・スモーク成功。この実行環境にはDocker Engineがなく、ユーザー端末のDocker Desktopでの確認は未実施 |
| PostgreSQL結合 | 初期版はGitHub ActionsのDockerスモークで成功。変更後の再実行も成功。この環境のpytestはSQLiteを使用 |
| AWS実デプロイ | 認証されたAWSアカウント、VPC、2つのサブネット、ACM証明書、許可するCIDRが未指定のため未実施 |
| ブラウザ視覚検証 | Playwright用ブラウザ実体を取得できず未実施。JavaScript構文検査は成功。Cesium表示の目視確認はDocker Desktop端末で実施 |

注意：本ファイルの「成功」は上記の実行条件で観測した結果であり、Docker Desktop／AWSでの動作実績を意味しません。

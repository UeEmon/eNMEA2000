# 検証記録

2026-09-24時点。

| 項目 | 結果 |
|---|---|
| Python 3.12 pytest | 9件成功。UDP実ソケット、WebSocket、ファイル入力、AIS分割と期限切れ、GPS、JSONL/GeoJSON、ログイン、SQLite永続化 |
| Pythonコンパイル・JS構文・bash構文 | 成功 |
| CloudFormation cfn-lint | 成功。テンプレートの静的検証 |
| GitHub Actions | PRに定義。GitHub上での結果を確認するまで未検証 |
| Docker Compose実行 | この実行環境にDocker Engineがないため未実施。端末のDocker Desktopで `docker compose up -d --build --wait` と `docker compose exec app python scripts/smoke.py` が必要 |
| PostgreSQL結合 | Dockerスモークで検証予定。この環境のpytestはSQLiteを使用 |
| AWS実デプロイ | 認証されたAWSアカウント、VPC、2つのサブネット、ACM証明書、許可するCIDRが未指定のため未実施 |
| ブラウザ視覚検証 | Playwright用ブラウザ実体を取得できず未実施。JavaScript構文検査は成功 |

注意：本ファイルの「成功」は上記の実行条件で観測した結果であり、Docker Desktop／AWSでの動作実績を意味しません。

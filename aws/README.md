# AWS初期運用構成

## 構成

- **UDP：送信機器 → EC2 Elastic IP:10110 → Dockerアプリ**
- **TCP：送信機器 → EC2 Elastic IP:10111 → 同じDockerアプリ**
- **Web：ブラウザ → ALB HTTPS:443 → EC2:8080 → 同じDockerアプリ**
- DB：同一EC2のPostgreSQLコンテナ。DBポートはホストに公開しません。
- ファイル・DB：暗号化gp3 EBSの `/opt/nmea/raw` と `/opt/nmea/postgres`。
- 認証情報：Secrets ManagerでWebトークン・DBパスワードを別々に生成。
- アプリログ：CloudWatch Logs、14日保持。
- 管理：Systems Manager Session Manager。SSHポートは開けません。

まずDocker Desktopに近い**単一EC2構成**にしています。EC2障害やAZ障害中の受信継続は保証しません。
本格的な高可用性が必要になった時点で、UDP受信を独立させ、NLB・共有キュー・RDSへ分離してください。
ALBはWeb用です。このテンプレートでUDPをALBに送信しても受信できません。

## 必要な事前情報

1. AWSアカウントとリージョン（例：ap-northeast-1）。
2. 同一VPC内、異なるAZにある**インターネットゲートウェイへの経路があるパブリックサブネット2つ**。
3. 同じリージョンで発行済みのACM証明書。そのドメイン名のDNSを変更できること。
4. Webアクセス元、UDP送信元、TCP送信元それぞれのグローバルIPv4 CIDR。
5. Docker Desktop、Python 3.12、`boto3`、AWS認証情報。
6. EC2/ALB/EIP/IAM/Secrets Manager/CloudWatch/CloudFormation/ECR作成権限と必要なクォータ。

NMEA機器がLAN内へしか送れない場合、そのLANの中継機器からAWSのElastic IPへユニキャスト転送してください。
インターネット上のUDPを許可しない運用では、VPN等の閉域経路に合わせたネットワーク設計が別途必要です。
このテンプレートはIPv4のAWS標準商用リージョン向けです。中国／GovCloudは対象外です。

## 構築

まずDocker Desktopで起動とスモーク試験を完了してください。その後、プロジェクトのルートで：

```bash
python -m pip install boto3
python aws/deploy.py --region ap-northeast-1 --vpc vpc-XXXXXXXX --subnet-a subnet-AAAAAAAA --subnet-b subnet-BBBBBBBB --certificate arn:aws:acm:ap-northeast-1:ACCOUNT:certificate/CERT-ID --web-cidr YOUR-WEB-PUBLIC-IP/32 --udp-cidr YOUR-SENDER-PUBLIC-IP/32 --tcp-cidr YOUR-TCP-SENDER-PUBLIC-IP/32
```

上記は計画表示だけです。実際にリソース作成とイメージ公開を実行する場合は、同じコマンドに `--execute` を追加します。
AWS認証はboto3の標準認証チェーンを使います。SSOの場合は先に端末で `aws sso login --profile NAME` を実行し、`AWS_PROFILE` を設定してください。
秘密鍵をソースコードに書かないでください。

スクリプトは以下を行います。

1. Docker接続、AWSアカウント、サブネット、CloudFormation構文を確認。
2. `nmea-observatory` ECRリポジトリを作成（存在すれば再利用）。
3. `linux/amd64` イメージをビルドし、一意の日時タグでプッシュ。
4. `cloudformation.json` からスタックを新規作成。

既存スタックの上書きは行いません。ECRリポジトリはこのスクリプトで作成され、CloudFormationスタックの管理外です。
AWS利用料金が発生します。金額はインスタンス・ALB・EIP・ストレージ・通信量などにより変わります。

## 起動後の確認

1. CloudFormationのイベントを確認して `CREATE_COMPLETE` を待つ。
2. EC2の初期化が終わり、ALBターゲットが `healthy` になることを確認する。
3. スタック出力 `WebDnsTarget` に証明書のドメインのCNAMEまたはRoute 53 Aliasを向ける。
4. `https://証明書のドメイン` を開く。ALBのDNS名そのものでは証明書の名前が一致しません。
5. スタック出力 `AppTokenSecretArn` のSecret値をAWSコンソールで取得し、ログイン。
6. UDPをスタック出力 `UdpHost` の10110番、TCPを `TcpHost` の10111番へ送信する。
7. ファイル解析と再起動後のデータ保持を確認する。

CloudFormationの作成完了だけではアプリの稼働を保証しません。UserDataの成否はSession Managerで `/var/log/cloud-init-output.log`、`docker ps`、`docker logs nmea-app` から確認できます。

## 更新とデータ保持

更新は新しいECRタグを作ってから、EC2上でアプリコンテナだけを再作成します。
**CloudFormationのAppImage変更だけでは既存EC2のUserData再実行を保証しないため、アプリ更新には使わないでください。**
更新前にバックアップを取得し、起動条件はbootstrap.shの `docker run ... nmea-app` と同一にしてください。
単一受信器のため再作成中のUDP/TCPセンテンスは失われます。送信側のバッファリング／リプレイは別途必要です。
DBスキーマ変更を含む更新には、別途移行手順が必要です。この初期版にはDB移行ツールを含めていません。

EBSルートボリュームは `DeleteOnTermination=false`、Secretsは `Retain` です。
EC2終了・スタック削除後にもボリューム／秘密情報が残る設計ですが、**新しいEC2へ自動復元はしません**。
残存リソースとECRは個別に管理し、不要になった段階で削除してください。保存分の料金は継続します。

## バックアップ例（EC2上で実行）

```bash
sudo mkdir -p /opt/nmea-backup
sudo sh -c 'docker exec nmea-db pg_dump -U nmea -d nmea -Fc > /opt/nmea-backup/nmea.dump'
sudo tar -C /opt/nmea/raw -czf /opt/nmea-backup/raw-data.tar.gz .
```

これは手動バックアップです。S3転送、AWS Backup、定期実行と復元訓練は本番運用に合わせて追加してください。
このテンプレートには自動バックアップ・容量アラーム・RDSは含めていません。

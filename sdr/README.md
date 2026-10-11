# SDR AIS受信部

本体と独立したDocker Compose環境です。AIS-catcher v0.70（ソースcommit `8833c64b3da0c42e9a724b9bd13eaab2fffadcca` に固定）でAIS A/Bを同時受信し、チェックサム検証済みの `!AIVDM` を複数のTCP/UDP宛先に配信します。本体のデータベースやiPadを直接変更しません。

## 起動（リポジトリのルートで実行）

MacではDocker Desktop、WindowsではDocker DesktopのLinuxコンテナ、LinuxではDocker EngineとCompose v2を使用します。Python 3は初期トークン生成にのみ必要です。初回はソース取得・ビルドのためインターネット接続が必要です。

```sh
git clone https://github.com/UeEmon/eNMEA2000.git
cd eNMEA2000
python3 sdr/setup.py
docker compose -f sdr/compose.yaml up -d --build --wait
```

Windows PowerShellでは `python3` を `py -3` に読み替えてください。既にclone済みなら作業内容を保存して `git pull --ff-only` 後、残りを実行します。

管理画面: http://localhost:18082 。`sdr/.env` の `SDR_TOKEN` を入力します。`.env` は隠しファイルです。エディタで開くか、Mac/Linuxでは `cat sdr/.env`、PowerShellでは `Get-Content sdr/.env` で確認できます。setup.pyの再実行で既存設定を上書きしません。

1. 入力方式・ホスト・ポートなどを設定。
2. 配信先に本体またはiPadの待受IPを入力。標準はTCP 10111 / UDP 10110。
3. 「設定を保存」→「受信開始」。保存時はいったん受信を停止します。
4. 受信件数、最終受信、配信先ごとの状態を確認。

受信開始は明示操作です。コンテナ再起動後も設定とNMEAログは保持しますが、自動的に受信を開始しません。終了するには `docker compose -f sdr/compose.yaml down`。`down -v` は保存設定・ログを削除します。

## OSごとのSDR接続

|環境|接続方式|
|---|---|
|Apple Silicon / Intel Mac|RTL-TCP / SpyServer。USBはホストまたは外部のSDR端末で処理|
|Windows Docker Desktop|RTL-TCP / SpyServer。USBはホストまたは外部のSDR端末で処理|
|Linux Docker Engine|ネットワーク入力、またはUSB用Compose追加|

Docker Desktopの通常構成ではホストUSBを直接利用できません。Mac/Windowsで物理USB受信機を使う際は、ホストOS対応の `rtl_tcp`、SpyServer、またはLinux/Raspberry Pi受信ノードを別途準備してください。すべてをコンテナ化する場合はLinuxのUSB受信ノードを使います。USB/IPは本構成の検証範囲外です。

RTL-TCPのホスト側起動例（rtl_tcp導入済みの場合）:

```sh
rtl_tcp -a 0.0.0.0 -p 1234 -f 162000000 -s 1536000
```

同じPC上のサービスへの入力ホストは `host.docker.internal`、外部端末ならそのLAN IPを指定します。rtl_tcpは必要なLAN内だけで接続を許可してください。SpyServerのポートは稼働中のサーバ設定に合わせます（例5555）。ゲインautoはSpyServerではサーバ既定値です。

LinuxのUSB直結:

```sh
docker compose -f sdr/compose.yaml -f sdr/compose.usb.yaml up -d --build --wait
```

入力方式をUSBにし、複数台ある場合はUSBシリアルを入力します。USB追加構成では受信コンテナだけrootで起動し、USBバスをマウントします。`privileged` およびDockerソケットは使いません。ホストのDVBドライバがデバイスを占有する場合はホスト側で解放してください。

## 本体・iPadとの接続

同じDocker Desktop端末にある本体には `host.docker.internal:10111`（TCP）。本体の受信開始とホスト側10111の公開を確認します。別端末の本体/iPadには端末のLAN IPを指定します。iPadはアプリを前面で動作させ、ローカルネットワーク許可と受信待受を有効にします。クラウド宛先はVPNなどで到達できるTCP/UDP待受IPを指定します。WebのHTTPS/ALBアドレスはNMEAの宛先ではありません。

1文/UDPデータグラム、TCPはCRLF区切り。同一UDP宛先は同じソケットを使用して分割文の送信元を維持します。宛先ごとに512文のキュー、2秒の鮮度上限、切断時破棄、独立再接続があります。TCPの送信カウントはOSに渡した件数で、DBへの登録保証ではありません。切断や輻輳時には分割AISが不完全になる場合があり、アプリ側の断片タイムアウトに委ねます。

受信した他船AISを自己位置に変換しません。AIVDOやGPSの自己位置入力は本体/iPadの別入力経路を利用してください。

## I/Qファイル・ログ

`sdr/iq` に中心周波数162 MHzで記録したraw I/Qを置き、画面でファイル、サンプルレート、形式CU8/CS8/CS16/CF32を指定します。ファイルは読み取り専用で渡します。一回処理して停止し、繰り返し再送しません。これは記録信号の復調であり、過去時刻を復元する再生ではありません。過去データを運用中のライブ画面に混在させないよう試験用の宛先を使用してください。

NMEAログはDockerボリューム `sdr-data` 内に保存。標準上限100MB、4ファイルでローテーションします。画面からダウンロードしたログを本体のファイル解析へ投入できます。プロセス診断は末尾100行とDockerの容量制限付きログに保存します。信号強度はこの版では取得・表示しません。

## 構成・保護

- `ais-receiver`: AIS-catcherとプロセス管理。USB、RTL-TCP、SpyServer、raw I/Q入力。
- `nmea-router`: 検証・ログ・配信・管理API。依存Pythonパッケージなし。
- `receiver-web`: Nginx、内部80、ホスト18082。8080/8888は使用しません。

管理APIにSDR_TOKENが必要です。標準ではlocalhostにのみ公開し、トークンをブラウザの永続ストレージに保存しません。LAN公開する場合は `SDR_BIND` とHTTPSの終端を環境に合わせて設定してください。受信内部APIおよびUDP10112はホストに公開しません。Dockerネットワーク管理者は信頼境界内です。

AIS-catcherはGPL-3.0です。使用ソース一式（ライセンスを含む）を受信イメージの `/usr/share/ais-catcher/source.tar.gz` に同梱し、ビルド手順をDockerfileに保持しています。PythonとNginxおよびRTL-SDRのライセンスもそれぞれ適用されます。

## 検証

```sh
python3 -m unittest discover -s sdr/tests -v
```

専用CIでamd64/arm64それぞれのDockerビルド、認証、TCP/UDP配信、分割文、再接続、設定永続化、容量制限、日本語画面操作とI/Qファイル処理を確認します。`python3 sdr/smoke.py` は試験用10110/10111を使用するため、本体が停止した専用試験環境で実行してください。設定は終了時に戻しますが試験ログは残ります。

無信号I/Qによるエンジン起動試験は、実際のAIS電波の復調性能・USB機種互換性を証明しません。実受信、実機RTL-TCP/SpyServer、各OS上のDocker Desktopによる確認は受信機・アンテナを接続した現地試験が必要です。

参照: [AIS-catcher](https://github.com/jvde-github/AIS-catcher)、[入力仕様](https://jvde-github.github.io/AIS-catcher-docs/usage/cli/)、[Docker Desktop USB制約](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/general/)。

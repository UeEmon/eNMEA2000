# eNMEA iPad（単体動作）

既存AWS/Docker版と同じリポジトリで管理する、iPadOS 17以降のネイティブアプリです。受信・解析・SQLite保存はSwiftで端末内実行し、GISだけを同梱CesiumJSで描画します。サーバ接続、Cesium ionトークン、地図配信サーバは不要です。

## Macからインストール

必要環境：Mac、iPadOS 17以降のiPad、iOS 17以降のSDKを含むXcode、Node.js 22、Homebrew。Docker DesktopはiPadアプリのビルドには使いません。

```bash
git clone https://github.com/UeEmon/eNMEA2000.git
cd eNMEA2000
brew install xcodegen
bash ipad/tools/prepare-assets.sh
swift test --package-path ipad
xcodegen generate --spec ipad/project.yml
open ipad/eNMEA-iPad.xcodeproj
```

Xcodeの **Settings → Accounts** にApple Accountを追加し、ターゲット **eNMEA-iPad → Signing & Capabilities** でTeamを選択してください。Bundle Identifierは自分のTeamで利用できる固有値に変更します。USB接続したiPadを実行先に指定し、Runを押します。端末で開発者モードや信頼の設定が求められた場合は案内に従います。初回のローカルネットワーク許可は許可してください。拒否した場合はiPadの設定でこのアプリのローカルネットワーク権限を変更します。

実機への署名・配布には利用者のApple Account/Teamが必要です。CIの成果物は**シミュレータ用アプリ**であり、実機へ直接インストールできるIPAではありません。TestFlight/App Store配布はMacで署名・Archiveして別途実施します。

## 受信と操作

1. iPadと送信元を同じLANへ接続し、アプリの「設定 → このiPadのIPアドレス」で受信先を確認します。IPv4を優先してWi-Fi／有線LANのIPv4・IPv6を表示し、「コピー」でコピーできます。接続変更・アプリ復帰時に更新され、「IPアドレスを更新」で手動更新もできます。アドレスが表示されない場合はWi-Fi／有線LANの接続を確認してください。
2. アプリの設定でUDP（初期値10110）とTCP（初期値10111）のポートを指定して「受信開始」を押します。
3. 送信元から**iPadのIPアドレス**へユニキャストUDP送信、またはTCP接続で改行区切りのNMEA文を送ります。Macのlocalhostではありません。
4. GISの船舶をタップすると右側に詳細と航跡が表示されます。長押し、マウスの右クリック、または詳細の「監視対象に登録」から登録できます。重複MMSI/IMOには更新・取りやめのダイアログが出ます。
5. アラートをタップすると該当船舶を選択し、GIS中央へ移動します。位置未受信の船舶はまだ地図に表示できません。
6. 「ファイル読込」でFilesから.log/.nmea/.txt等のテキストを選べます。右上メニューからログ書き出し・受信データ削除を実行できます。監視対象は別テーブルで保持し、編集・削除できます。

受信は**フォアグラウンドのみ**です。バックグラウンド移行で停止し、復帰後は受信開始を押します。ファイル解析は受信を停止して実行し、過去ログによるライブ監視アラートを抑止します。地図と保存済みデータはインターネット接続なしで利用できます。UDPブロードキャスト・マルチキャストはこの初期版の対象外です。

## Dockerエミュレータとの接続試験

既存エミュレータは引き続きMacのDocker Desktopで起動します。エミュレータの送信先ホストをiPadのWi-Fi IPへ、TCP送信先ポートを10111へ設定してください。iPad側を受信開始した後に全メッセージタイプ送信と自動周回を実行します。これはサーバ版を経由せず、エミュレータからiPadへ直接接続します。Macのファイアウォール・Wi-Fiの端末間通信制限も確認してください。

## 解析範囲

- AIS Type 0〜28の基本ビットフィールド。Type16/22/24/25/26の形式分岐、AIS複数文の再組立、送信元分離、30秒期限、チェックサム検証。
- Type17/22/23の低分解能座標とType25/26の宛先・アプリID・無線状態を補正して扱います。
- Type6/8/17/25/26等のバイナリ応用データはビット長と16進文字列を保持します。DAC/FID固有・ベンダー固有の応用フィールドは個別展開しません。
- NMEA0183のRMC/GGA/GLL/VTG/HDT/HDG/ZDAの主要フィールドと位置。有効位置だけを使用します。その他のセンテンスは原文と列を保持し、unsupported表示します。
- MIL-STD-2525D / APP-6D切替、Natural Earth II、航跡、MMSI/IMO監視。AIS以外のGPS情報は受信一覧に表示し、船舶シンボルはMMSIを持つAIS位置情報から生成します。
- 最新500件を一覧表示し、選択船舶の最大100受信分から航跡を描画します。保存ログは書き出し可能です。バックアップは書き出しを使い、アプリ削除前に実施してください。

## 開発と検証

```bash
swift test --package-path ipad
bash ipad/tools/prepare-assets.sh
xcodegen generate --spec ipad/project.yml
xcodebuild -project ipad/eNMEA-iPad.xcodeproj -scheme eNMEA-iPad \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath ipad/DerivedData CODE_SIGNING_ALLOWED=NO build
```

`.github/workflows/ipad.yml` がmacOS上でAIS全タイプ・不正文・分割文・座標・バイナリ形式・SQLite永続化・監視重複・アラートと実際のUDP/TCP受信・同梱ファイル配信をテストし、シミュレータ向けアプリをビルドします。別ジョブで外部通信を遮断したGIS表示・航跡・両規格のシンボル・クイックメニューを検証します。実機のUDP/TCP、タッチ操作、オフライン地図、バックグラウンド停止は上記手順で確認してください。

地図のHTTPは127.0.0.1の自動割当ポートで同梱ファイルだけを読み出します。LANへのWeb公開はありません。WebViewの外部遷移を禁止し、パス逸脱を拒否します。8080/8888は固定使用しません。AWS/Docker版のWebコンテナ内ポート80と外部ポートは変更しません。

## 検証結果（2026-10-10）

[iPad CI](https://github.com/UeEmon/eNMEA2000/actions/runs/38026946480) でSwiftテスト9件（失敗0件）、オフラインGIS操作、Xcode 16.4 / iOS Simulator 18.5向けのarm64・x86_64ビルドが通過しました。実機署名・実機インストール、iPadのWebView描画・タッチ操作、実LANでの受信は利用者のMac/iPadで確認してください。Swift 5言語モードでビルドし、可変の受信・DBオブジェクトを1つのシリアルキューで操作します。

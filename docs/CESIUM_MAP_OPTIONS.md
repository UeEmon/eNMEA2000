# Cesium背景地図の配布候補

背景地図の権利とCesiumJS本体のライセンスは別です。地図タイルを同梱する場合、画像・データ・スタイル・フォントそれぞれの条件を確認してください。AISの表示は航海用途には使えません。

| 候補 | Cesiumへの組み込み | 配布の目安 | 留意点 |
| --- | --- | --- | --- |
| Natural Earth II | CesiumJS同梱の `Assets/Textures/NaturalEarthII` を `TileMapServiceImageryProvider` で表示 | 同梱可能。現在の本システムの背景図 | Natural Earthはパブリックドメイン。広域の概要地図向け。 |
| Natural Earth データを自作タイル化 | ラスタータイルを生成して `UrlTemplateImageryProvider` で配信 | 自作タイルを同梱可能 | 追加するスタイルや素材は別途条件を確認。 |
| OpenStreetMapデータによる自前タイル | 自前のラスタタイルサーバーをCesiumに接続 | ODbLと帰属表示などの条件を満たして配布可能 | OSM公式タイルサーバーから一括取得して同梱することはできません。 |
| OpenMapTiles（自前ホスト） | サーバー側でラスタ化しCesiumにXYZで提供 | OSMデータ・スタイル・フォントの条件を満たす場合に配布可能 | vector PBFをCesiumのラスタ imagery にそのまま指定しないでください。 |
| 国土地理院の地理院タイル | `UrlTemplateImageryProvider` でオンライン表示 | オンライン利用は出典表記等の条件付き。オフライン同梱は個別確認 | 測量成果の複製・使用に申請が必要となる場合があります。 |

## 一次資料

- Natural Earth 利用条件: https://www.naturalearthdata.com/about/terms-of-use/
- CesiumJS ライセンス: https://github.com/CesiumGS/cesium/blob/main/LICENSE.md
- CesiumJS imagery provider: https://cesium.com/learn/cesiumjs/ref-doc/UrlTemplateImageryProvider.html
- OpenStreetMapタイル利用方針: https://operations.osmfoundation.org/policies/tiles/
- OpenStreetMapデータの著作権: https://www.openstreetmap.org/copyright
- OpenMapTilesライセンス: https://openmaptiles.org/docs/website/licensing/
- 地理院タイル利用方法: https://maps.gsi.go.jp/development/ichiran.html
- 国土地理院・測量成果の利用手続: https://www.gsi.go.jp/LAW/2930-index.html

配布時は同梱済みのNatural Earth IIを既定とし、詳細地図が必要な環境では自前ホストのタイルを追加できます。

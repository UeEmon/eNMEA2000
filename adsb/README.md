# ADS-B（1090ES）受信・シミュレータ

設計・使い方は [docs/ADSB_DESIGN.md](../docs/ADSB_DESIGN.md) を参照してください。

| モジュール | 役割 |
|---|---|
| `modes.py` | CRC-24、DF17/18の解析・生成、CPR符号化／復号 |
| `tracker.py` | ICAO単位の航空機状態 |
| `mapping.py` | eNMEA2000イベント行、AIS Type 9ブリッジ |
| `simulator.py` | 航空機トラフィック生成（AVR/TCP、CU8 I/Q） |
| `ppm.py` | 1090 MHz PPM 変調・最小復調（2 Msps） |
| `receiver.py` | AVR/I/Q入力 → JSON行・本体へ転送 |
| `ollama_assist.py` | ローカルOllamaによるコーディング補助 |

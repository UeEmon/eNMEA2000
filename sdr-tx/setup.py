import secrets
from pathlib import Path
path=Path(__file__).resolve().parent/'.env'
try:
    with path.open('x') as f:f.write('SDR_TX_TOKEN='+secrets.token_urlsafe(32)+'\nSDR_TX_WEB_BIND=127.0.0.1\nSDR_TX_DATA_BIND=0.0.0.0\n')
    path.chmod(0o600)
    print('Created sdr-tx/.env; use SDR_TX_TOKEN at http://localhost:18083')
except FileExistsError:print('Existing sdr-tx/.env preserved')

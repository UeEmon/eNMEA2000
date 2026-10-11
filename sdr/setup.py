"""Generate local secret without overwriting an existing deployment."""
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent / '.env'
try:
    with path.open('x', encoding='utf8') as f:
        f.write('SDR_TOKEN=' + secrets.token_urlsafe(32) + '\nSDR_BIND=127.0.0.1\nSDR_WEB_PORT=18082\n')
    path.chmod(0o600)
    print('Created sdr/.env. Use its SDR_TOKEN to sign in at http://localhost:18082')
except FileExistsError:
    print('sdr/.env already exists; preserved.')

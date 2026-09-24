from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
p = root / '.env'
if p.exists():
    print('.env already exists; kept unchanged. APP_TOKEN is in that file.')
else:
    p.write_text(f'APP_TOKEN={secrets.token_urlsafe(32)}\nPOSTGRES_PASSWORD={secrets.token_hex(24)}\nWEB_BIND=127.0.0.1\nUDP_BIND=0.0.0.0\nUDP_ALLOW_CIDRS=\n',encoding='utf-8')
    p.chmod(0o600)
    print('Created .env. Open it locally and use APP_TOKEN to sign in.')

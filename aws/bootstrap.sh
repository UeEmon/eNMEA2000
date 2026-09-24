#!/bin/bash
set -euo pipefail
dnf install -y docker
systemctl enable --now docker
install -d -m 700 /opt/nmea
install -d -o 10001 -g 10001 /opt/nmea/raw
install -d /opt/nmea/postgres
aws secretsmanager get-secret-value --region '${AWS::Region}' --secret-id '${AppSecret}' --query SecretString --output text > /opt/nmea/app.secret
aws secretsmanager get-secret-value --region '${AWS::Region}' --secret-id '${DbSecret}' --query SecretString --output text > /opt/nmea/db.secret
chmod 600 /opt/nmea/*.secret
python3 - <<'PY'
from pathlib import Path
root=Path('/opt/nmea')
token=(root/'app.secret').read_text().strip()
password=(root/'db.secret').read_text().strip()
(root/'app.env').write_text('APP_TOKEN='+token+'\nDATABASE_URL=postgresql+psycopg://nmea:'+password+'@nmea-db:5432/nmea\nDATA_DIR=/data\nCOOKIE_SECURE=true\n')
(root/'db.env').write_text('POSTGRES_DB=nmea\nPOSTGRES_USER=nmea\nPOSTGRES_PASSWORD='+password+'\n')
for name in ['app.env','db.env']: (root/name).chmod(0o600)
(root/'app.secret').unlink();(root/'db.secret').unlink()
PY
aws ecr get-login-password --region '${AWS::Region}' | docker login --username AWS --password-stdin '${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com'
docker network create nmea
docker pull '${AppImage}'
docker pull postgres:17-bookworm
docker run -d --name nmea-db --network nmea --restart unless-stopped --env-file /opt/nmea/db.env --mount type=bind,source=/opt/nmea/postgres,target=/var/lib/postgresql/data --log-opt max-size=10m --log-opt max-file=3 postgres:17-bookworm
ready=0
for attempt in $(seq 1 60); do
  if docker exec nmea-db pg_isready -U nmea -d nmea; then ready=1; break; fi
  sleep 2
done
[ "$ready" = 1 ]
docker run -d --name nmea-app --network nmea --restart unless-stopped --init --env-file /opt/nmea/app.env --mount type=bind,source=/opt/nmea/raw,target=/data -p 8080:8080/tcp -p 10110:10110/udp -p 10111:10111/tcp --log-driver awslogs --log-opt awslogs-region='${AWS::Region}' --log-opt awslogs-group='${LogGroup}' --log-opt awslogs-stream=app --log-opt mode=non-blocking --log-opt max-buffer-size=4m '${AppImage}'

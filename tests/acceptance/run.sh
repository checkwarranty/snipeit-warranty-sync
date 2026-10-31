#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
docker compose up -d
for attempt in $(seq 1 60); do
  if docker compose exec -T db healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1; then break; fi
  sleep 2
done
docker compose exec -T snipe php artisan migrate --force --no-interaction
docker compose exec -T snipe php artisan passport:keys --force --no-interaction
docker compose exec -T snipe php artisan passport:client --personal --name=Acceptance --no-interaction > /tmp/cw-snipe-oauth-bootstrap.log
docker compose exec -T snipe php artisan snipeit:create-admin --first_name=Acceptance --last_name=Admin --email=acceptance@example.invalid --username=acceptance --password=acceptance-only-password
docker compose exec -T snipe php /opt/cw-testing/seed.php
docker compose cp snipe:/tmp/cw-snipe-auth.json /tmp/cw-snipe-auth.json
docker compose exec -T snipe chown -R www-data:www-data storage bootstrap/cache
for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:18080/login >/dev/null; then break; fi
  sleep 2
done
if ! python3 runtime.py; then
  docker compose exec -T snipe sh -c 'tail -n 100 storage/logs/laravel*.log' >&2 || true
  exit 1
fi

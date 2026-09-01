#!/usr/bin/env bash
# Full reset of the crAPI target: wipes all volumes so the next `up -d`
# starts from a genuinely fresh DB. Slow — prefer signing up fresh throwaway
# users for iterative dev, use this before an actual evaluation run.
set -euo pipefail
cd "$(dirname "$0")/crapi/deploy/docker"

docker compose down -v
docker compose up -d

echo "crAPI reset. Waiting for crapi-web to report healthy..."
until [ "$(docker inspect -f '{{.State.Health.Status}}' crapi-web 2>/dev/null)" = "healthy" ]; do
  sleep 5
done
echo "crAPI is up at http://localhost:8888"

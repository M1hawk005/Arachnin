#!/usr/bin/env bash
# Idempotent production deploy for a single host (e.g. an Oracle Ampere VPS).
# Pulls the pre-built multi-arch images referenced in compose.production.yml,
# applies pending migrations via the api service's entrypoint, and restarts
# the stack with zero manual steps. Safe to re-run; safe to run from cron.
#
#   ./deploy/deploy.sh              # deploy whatever :latest resolves to
#   BACKEND_IMAGE=...:1.4.0 \
#   FRONTEND_IMAGE=...:1.4.0 ./deploy/deploy.sh   # pin an explicit release
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/deploy/.env.production}"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.production.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found." >&2
  echo "       cp deploy/.env.production.example deploy/.env.production and set the secrets first." >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

echo "==> Validating compose configuration"
compose config --quiet

echo "==> Pulling published images"
compose pull

echo "==> Starting stack (migrations run from the api entrypoint)"
compose up -d --remove-orphans

echo "==> Reclaiming space from superseded images"
docker image prune --force >/dev/null

echo "==> Current state"
compose ps

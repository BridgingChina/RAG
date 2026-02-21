#!/bin/bash
set -euo pipefail

OP_ENV_ID="sv3l4gxu36lovhnlmiczh2kncm"

export OP_SERVICE_ACCOUNT_TOKEN
OP_SERVICE_ACCOUNT_TOKEN=$(cat /opt/bridge-rag/.op-token)

# Export git version info for Docker build args
export GIT_COMMIT GIT_DATE
GIT_COMMIT=$(git rev-parse --short HEAD)
GIT_DATE=$(git log -1 --format=%cs)

# Build all images and start all services
op run --environment "$OP_ENV_ID" -- \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --project-name bridge-rag up -d --build "$@"

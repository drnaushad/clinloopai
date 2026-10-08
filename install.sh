#!/usr/bin/env bash
# ClinLoop AI — one-command on-premise install
#
#   curl -fsSL https://raw.githubusercontent.com/drnaushad/clinloopai/main/install.sh | bash
#
# Options (environment variables):
#   CLINLOOP_DIR=/opt/clinloop    install directory          (default: ~/clinloop)
#   CLINLOOP_LLM=0                skip the bundled Ollama LLM (e.g. Ollama already runs on this host)
#   CLINLOOP_VERSION=1.2.0        pin an image version       (default: latest)
#
# Re-running is safe: secrets in an existing .env are kept; images are updated.
set -euo pipefail

DIR="${CLINLOOP_DIR:-$HOME/clinloop}"
RAW="https://raw.githubusercontent.com/drnaushad/clinloopai/main"
WITH_LLM="${CLINLOOP_LLM:-1}"

say()  { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "Docker is required: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required (docker compose …)"
docker info >/dev/null 2>&1 || fail "Cannot reach the Docker daemon (is it running? are you in the docker group?)"

random_hex() {  # $1 = number of bytes
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$1"
  else head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; fi
}

mkdir -p "$DIR"
cd "$DIR"
say "Installing into $DIR"
curl -fsSL "$RAW/docker-compose.yml" -o docker-compose.yml

if [ ! -f .env ]; then
  say "Creating .env with new secrets"
  ADMIN_TOKEN="$(random_hex 24)"
  umask 077
  {
    echo "# ClinLoop configuration. Keep this file private (mode 600)."
    echo "# One entry per person: token:user:role (roles: viewer, navigator, clinician, admin)"
    echo "CLINLOOP_API_TOKENS=${ADMIN_TOKEN}:admin:admin"
    echo "CLINLOOP_SIGNING_KEY=$(random_hex 32)"
    echo "CLINLOOP_VERSION=${CLINLOOP_VERSION:-latest}"
    echo "CLINLOOP_LLM_MODEL=exaone3.5:7.8b"
    if [ "$WITH_LLM" = "1" ]; then
      echo "COMPOSE_PROFILES=llm"
    else
      echo "# Using an Ollama already running on this host:"
      echo "CLINLOOP_OLLAMA_URL=http://host.docker.internal:11434"
    fi
    echo "# Hospital FHIR server (read-only):"
    echo "# Governance: keep rules a specialist has not signed off in shadow mode (recommended for clinical use)"
    echo "CLINLOOP_ENFORCE_SIGNOFF=1"
    echo "CLINLOOP_SIGNOFF_APPROVALS=1"
    echo "# Your hospital's critical-finding list (copy the default from the image, edit, approve at /governance.html):"
    echo "# CLINLOOP_CRITICAL_FINDINGS=/var/lib/clinloop/critical_findings.json"
    echo "# CLINLOOP_FHIR_BASE=https://fhir.hospital.local/r4"
    echo "# CLINLOOP_FHIR_TOKEN="
  } > .env
  NEW_INSTALL=1
else
  say "Keeping existing .env"
  NEW_INSTALL=0
fi

say "Pulling images (first run downloads several GB if the LLM is enabled)"
docker compose pull
say "Starting ClinLoop"
docker compose up -d

say "Waiting for the API to become healthy"
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8124/api/v1/health >/dev/null 2>&1; then
    echo
    say "ClinLoop is running:  http://localhost:8124/worklist.html"
    if [ "$NEW_INSTALL" = "1" ]; then
      echo "   Admin token (also in $DIR/.env):  $ADMIN_TOKEN"
    fi
    echo "   Rules stay in shadow mode until a specialist signs them off: http://localhost:8124/governance.html"
    echo "   Add users by editing CLINLOOP_API_TOKENS in $DIR/.env, then: docker compose up -d"
    echo "   Update later by re-running this installer."
    exit 0
  fi
  sleep 2
done
fail "The API did not become healthy. Check: cd $DIR && docker compose logs clinloop-api"

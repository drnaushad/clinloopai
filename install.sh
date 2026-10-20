#!/usr/bin/env bash
# ClinLoop AI — one-command on-premise install
#
#   curl -fsSL https://raw.githubusercontent.com/drnaushad/clinloopai/main/install.sh | bash
#
# Options (environment variables):
#   CLINLOOP_DIR=/opt/clinloop    install directory          (default: ~/clinloop)
#   CLINLOOP_LLM=0                skip the bundled Ollama LLM (e.g. Ollama already runs on this host)
#   CLINLOOP_VERSION=1.2.0        pin an image version       (default: latest)
#   CLINLOOP_MODELS="exaone3.5:7.8b medgemma:4b"   models to pull (default: these two, plus medgemma:27b on a GPU >= 20 GB)
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

# GPU: the largest NVIDIA GPU's memory decides whether MedGemma 27B is pulled (override with CLINLOOP_MODELS)
GPU_MB=0
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_MB=$( (nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null || true) | tr -d ' ' | grep -E '^[0-9]+$' | sort -n | tail -1 || true)
  GPU_MB=${GPU_MB:-0}
fi
BIG_GPU=""
[ "${GPU_MB:-0}" -ge 20000 ] 2>/dev/null && BIG_GPU=1

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
      # Local models: EXAONE 3.5 (messages, Korean/English) and MedGemma 4B (images) always;
      # MedGemma 27B (report second reader, ~17 GB) only when a GPU with >= 20 GB memory is present
      echo "CLINLOOP_PULL_MODELS=${CLINLOOP_MODELS:-exaone3.5:7.8b medgemma:4b${BIG_GPU:+ medgemma:27b}}"
    else
      echo "# Using an Ollama already running on this host:"
      echo "CLINLOOP_OLLAMA_URL=http://host.docker.internal:11434"
    fi
    echo "# Hospital FHIR server (read-only):"
    echo "# Intended-use profile: core locks off research features (image analysis, model readers); see docs/regulatory/"
    echo "CLINLOOP_PROFILE=core"
    echo "# BioMCP literature lookups for rule reviewers: off in the core profile; needs outbound internet"
    echo "# CLINLOOP_BIOMCP=1"
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

# Only with the NVIDIA Container Toolkit installed: without it, a GPU request would stop the stack from starting
if [ "$WITH_LLM" = "1" ] && [ "${GPU_MB:-0}" -gt 0 ] && docker info 2>/dev/null | grep -qi nvidia \
   && [ ! -f docker-compose.override.yml ]; then
  say "NVIDIA GPU found (${GPU_MB} MB): running the bundled models on it"
  {
    echo "# Written by install.sh: the bundled Ollama uses the NVIDIA GPU (needs the NVIDIA Container Toolkit)"
    echo "services:"
    echo "  ollama:"
    echo "    deploy:"
    echo "      resources:"
    echo "        reservations:"
    echo "          devices:"
    echo "            - driver: nvidia"
    echo "              count: all"
    echo "              capabilities: [gpu]"
  } > docker-compose.override.yml
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

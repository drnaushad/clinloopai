#!/usr/bin/env bash
# Set up the on-premise LLM for ClinLoop without Docker.
#   ./scripts/setup_local_llm.sh [model]      (default model: exaone3.5:7.8b)
set -euo pipefail

MODEL="${1:-${CLINLOOP_LLM_MODEL:-exaone3.5:7.8b}}"
URL="${CLINLOOP_OLLAMA_URL:-http://localhost:11434}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Install it first:"
  echo "  Linux:   curl -fsSL https://ollama.com/install.sh | sh"
  echo "  macOS:   https://ollama.com/download"
  exit 1
fi

if ! curl -sf "$URL/api/tags" >/dev/null; then
  echo "Starting Ollama…"
  (ollama serve >/tmp/ollama.log 2>&1 &)
  for _ in $(seq 1 30); do curl -sf "$URL/api/tags" >/dev/null && break; sleep 1; done
fi
curl -sf "$URL/api/tags" >/dev/null || { echo "Ollama did not start; see /tmp/ollama.log"; exit 1; }

echo "Downloading $MODEL (several GB on first run)…"
ollama pull "$MODEL"

echo
echo "Ready. Start the ClinLoop API with:"
echo "  export CLINLOOP_OLLAMA_URL=$URL CLINLOOP_LLM_MODEL=$MODEL"
echo "  uvicorn src.clinloop_engine.api:app --host 127.0.0.1 --port 8124"
echo "The Connections panel will then show 'On-premise LLM (Ollama): Connected · $MODEL'."

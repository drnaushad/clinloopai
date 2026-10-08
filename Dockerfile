# ClinLoop AI — on-premise image: API, clinician worklist, cockpit, BioMCP
#
#   docker run -p 127.0.0.1:8124:8124 -v clinloop-data:/var/lib/clinloop \
#     -e CLINLOOP_API_TOKENS=... -e CLINLOOP_SIGNING_KEY=... ghcr.io/drnaushad/clinloopai
#   → http://localhost:8124/worklist.html
FROM python:3.12-slim

LABEL org.opencontainers.image.title="ClinLoop AI" \
      org.opencontainers.image.description="Closed-loop clinical safety monitoring: API, clinician worklist and cockpit" \
      org.opencontainers.image.source="https://github.com/drnaushad/clinloopai"

# All runtime state lives on the /var/lib/clinloop volume: the loop registry,
# the outreach outbox and BioMCP's cache (HOME / XDG_CACHE_HOME).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLINLOOP_DB=/var/lib/clinloop/clinloop.db \
    CLINLOOP_OUTBOX=/var/lib/clinloop/outbox.jsonl \
    CLINLOOP_WEB_ROOT=/app/web \
    HOME=/var/lib/clinloop \
    XDG_CACHE_HOME=/var/lib/clinloop/cache

# OCR for outside reports (Korean and English)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

# Optional on-premise imaging model (research use only): docker build --build-arg WITH_IMAGING_AI=1
# Installs CPU PyTorch + TorchXRayVision and bakes the weights into the image, so no internet is needed.
ARG WITH_IMAGING_AI=0
ENV CLINLOOP_MODEL_DIR=/opt/clinloop/models
RUN if [ "$WITH_IMAGING_AI" = "1" ]; then \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
      && pip install --no-cache-dir torchxrayvision \
      && python -c "import torchxrayvision as x; x.models.DenseNet(weights='densenet121-res224-all', cache_dir='/opt/clinloop/models')"; \
    fi

COPY src ./src
COPY data/cases.json data/fhir_example_bundle.json ./data/

# Web UI, served by the API at / (only these files are exposed)
COPY index.html worklist.html governance.html imaging.html config.js manifest.json sw.js ./web/
COPY css ./web/css
COPY js ./web/js
COPY icons ./web/icons
COPY data/cases.json data/fhir_example_bundle.json data/radiology_test_bundle.json ./web/data/

# Unprivileged user; state on a mounted volume
RUN useradd --system --uid 10001 --home-dir /var/lib/clinloop clinloop \
    && mkdir -p /var/lib/clinloop/cache \
    && chown -R clinloop /var/lib/clinloop
USER clinloop
VOLUME ["/var/lib/clinloop"]

EXPOSE 8124
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8124/api/v1/health', timeout=4).status == 200 else 1)"

# CLINLOOP_API_TOKENS and CLINLOOP_SIGNING_KEY must be supplied at runtime
CMD ["uvicorn", "src.clinloop_engine.api:app", "--host", "0.0.0.0", "--port", "8124"]

# ClinLoop AI API — on-premise pilot image (no GPU stack; read-only data feed)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLINLOOP_DB=/var/lib/clinloop/clinloop.db

WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY src ./src
COPY data/cases.json data/fhir_example_bundle.json ./data/

# Run as an unprivileged user; the loop registry lives on a mounted volume
RUN useradd --system --uid 10001 clinloop && mkdir -p /var/lib/clinloop \
    && chown clinloop /var/lib/clinloop
USER clinloop
VOLUME ["/var/lib/clinloop"]

EXPOSE 8124
# CLINLOOP_API_TOKENS and CLINLOOP_SIGNING_KEY must be supplied at runtime
CMD ["uvicorn", "src.clinloop_engine.api:app", "--host", "0.0.0.0", "--port", "8124"]

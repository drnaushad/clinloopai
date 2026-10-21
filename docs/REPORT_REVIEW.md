# Report review: local models and optional research API

This feature is a synthetic-only draft. It does not make the public website a hospital-ready
patient-data system, validate a model or change the follow-up engine's clinical scope.

## Local LLM pathway

Open `review.html`, select the local pathway, and connect your own loopback Ollama with cloud
features disabled. Follow the existing `private.html` connection and SSH tunnel instructions.
The code checks the selected model's metadata before sending text and refuses remote/cloud
aliases, incomplete output, malformed JSON and untraceable source quotes. No cloud fallback
is used. A model returning valid JSON and exact quotes can still misinterpret the report.

Hospital care requires a separately approved local installation: hospital staff authentication,
patient access records, audit trail, reviewed rules, privacy/security approval, and prospective
clinical validation. Use the existing authenticated document/imaging endpoints for hospital
PDF, OCR and imaging workflows. The public preview is not a replacement for those controls.
Keep model suggestions in research/shadow review until independently validated.

## OpenAI research pathway

The first provider is OpenAI. No other provider is implied by “API.” Use synthetic data only.
The browser calls a gateway on the user's own computer; the gateway calls only
`https://api.openai.com/v1/responses`. The API key is never sent to the public website or
returned to the browser. Requests use Structured Outputs, `store: false`, no tools or
conversation history, and disabled automatic input truncation. `store: false` is not a
promise of zero retention: the provider's account settings and terms still apply.

Install the repository's pinned API dependencies in an isolated environment, then run:

```sh
python scripts/run_research_review.py
```

The helper asks for the API key with hidden input and a model ID supported by your account.
It generates a separate local gateway access code in `data/secrets/research-review/`, with
directory mode 700 and file mode 600. Open that file privately and enter its code in the
browser, never the OpenAI API key. The helper removes the code file on normal shutdown.
Never put an API key in a URL, public JavaScript, command-line arguments, a screenshot or Git.

The gateway binds only `127.0.0.1:18127`. Its exact allowed browser origin defaults to
`https://clinloopai.app`; for development use `CLINLOOP_RESEARCH_WEB_ORIGIN` with an exact
loopback origin. Wildcards and unrelated origins are rejected. Each request requires the
gateway access code plus synthetic-only and external-transmission confirmations. It accepts
one in-flight analysis and at most 12 attempts per hour to limit accidental API spending.
It has no hospital database, patient search or saved report-history route. It is not a
multi-user service and is not suitable for identifiable records. Use a separate gateway per
research operator; do not share the API key or access code.

For a research gateway on a private Ubuntu server, keep it loopback-bound and use a tunnel
from the laptop (only if the laptop's port is free):

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18127:127.0.0.1:18127 USER@YOUR_SERVER
```

No key was supplied for development testing. Provider requests were mocked; a real paid
API round trip must be recorded separately before claiming that an account/model works.

## Supported inputs and output checks

Six text categories: laboratory, radiology, pathology, ECG report text, discharge summary
and other health-report text. Categories organize extraction and do not establish specialty
accuracy. This preview accepts complete UTF-8 text/.txt up to 6000 bytes. It rejects PDF,
scanned images, DICOM and waveforms; those need approved extraction/modality-specific models
and separate validation. Nothing is silently truncated.

The model supplies source quotes with present/negated/uncertain/historical labels, explicitly
stated follow-up quotes, quoted timing and missing context. Every quote must occur exactly
in the source. Timing must occur inside its follow-up quote. Any unsupported item rejects the
whole output. No unstated interval is calculated and no obligation is closed. Empty findings
are not a normal report. Clinicians must check assertion status, anatomy, laterality, units,
reference ranges, dates, addenda and the relevance of any recommendation.

Switching pathways, disconnecting, leaving or ten minutes of inactivity clears page memory.
This is not secure memory deletion, upstream cancellation, provider-log deletion or grant
revocation. API key security also depends on the user's host, browser and website delivery.

## Verification

```sh
node tests/test_report_review.cjs
node tests/test_private_workspace.cjs
pytest tests/test_research_report_gateway.py
pytest tests/
python src/run_benchmark.py
```

Synthetic fixture agreement is software regression evidence, not real-patient accuracy.
Measure real-report performance only with approved datasets, independent clinician reference
labels and patient-separated test sets. A licensed clinician must review changes to clinical
logic line by line under `AGENTS.md` before deployment.

Official implementation references: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
and [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create).

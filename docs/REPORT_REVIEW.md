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

## OpenAI, Anthropic and Gemini research pathway

Choose a research provider explicitly: OpenAI, Anthropic (Claude), or Google Gemini.
Use synthetic data only. Each has one model ID configured on the operator's personal
gateway; model availability and structured-output support depend on the provider account.
The page does not claim that a listed provider or model has been clinically validated.
Changing provider clears the source, result and access code, then requires a fresh connection
and named-provider transmission confirmation. There is no fallback between providers.

The browser calls only the personal loopback gateway. That gateway uses fixed destinations:

| Provider | API destination | Server-side key variable | Model variable |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1/responses` | `OPENAI_API_KEY` | `CLINLOOP_RESEARCH_MODEL` |
| Anthropic | `https://api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` | `CLINLOOP_RESEARCH_ANTHROPIC_MODEL` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/models/MODEL:generateContent` | `GEMINI_API_KEY` | `CLINLOOP_RESEARCH_GEMINI_MODEL` |

Keys are sent in vendor-specific headers, never in URL queries, public website code or
browser responses. Model IDs must be bare IDs, without `models/`, slashes, query strings or
fragments. No model substitution, tools, conversation history or automatic retry is used.
OpenAI requests retain `store: false` and disabled input truncation. Other providers do
not receive an invented equivalent of that setting. No zero-retention guarantee is made:
each provider's account settings and terms apply.

Anthropic uses JSON schema output via `output_config.format`. Gemini uses
`generationConfig.responseMimeType` and `responseJsonSchema`. Their outgoing schema omits
string/array length constraints for compatibility, while the original full constraints and
exact source quotes are still validated locally. Refusals, token-limit stops, blocked results,
unexpected tools, missing or multiple results, and invalid evidence are rejected in full.

Install the repository's pinned API dependencies in an isolated environment, then run:

```sh
python scripts/run_research_review.py
```

The helper asks which provider to configure, then its API key with hidden input and a bare
model ID with JSON structured-output support. Existing configured keys/models in the
environment may enable additional providers on that same personal gateway; no unconfigured
provider is silently substituted. `CLINLOOP_RESEARCH_PROVIDER` can preselect the helper's
provider as `openai`, `anthropic` or `gemini`.
It generates a separate local gateway access code in `data/secrets/research-review/`, with
directory mode 700 and file mode 600. Open that file privately and enter its code in the
browser, never a provider API key. The helper removes the code file on normal shutdown.
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
and [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create),
[Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
and [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).


## Reliability review — 21 October 2026

The browser now cancels a pending connection before it can restart a cleared session, locks
analysis while a file is loading, and binds results to the exact source and selected model.
Changing either invalidates the old result. Source evidence includes surrounding text and a
count of repeated quote occurrences; assertion labels remain unverified model claims.

Structured local review checks the installed model's declared context window before sending
text and reserves room for the schema and output. Models with missing or inadequate capacity
are refused. An explicit successful stop is required; partial output and embedded thinking
traces are rejected. No input is split or silently truncated. This may refuse older Ollama
responses or smaller models that previously appeared to work with incomplete context.

The hospital text transport disables environment proxies, rejects redirects, public addresses
and cloud/remote model aliases, checks completion metadata, and returns generic failures.
An explicitly configured missing model no longer silently selects another. Inventory and
capability checks do not prove inference health, clinical accuracy or an air-gapped network.
GPU use is not inferred from a model's estimated memory requirement.

A separate hospital second-reader change refuses oversized/partial reads instead of silently
cutting a report. That change is a clinician-review draft under AGENTS.md and is excluded from
the software release candidate until reviewed line by line.

### Repeatable local synthetic evaluation

Check the fixed fixtures without any model call:

```sh
node scripts/evaluate_report_review.cjs --check-fixtures
```

After the operator has checked local inference health, run one explicitly selected installed
model against the 12 fixed synthetic cases (two per text category):

```sh
node scripts/evaluate_report_review.cjs --model medgemma:4b --address http://127.0.0.1:11434 --output /tmp/clinloop-medgemma4b-synthetic.json
```

Use a new output filename for each run. Substitute `medgemma:27b` or `exaone3.5:7.8b` explicitly
for comparisons; there is no model fallback, download or external provider call. The runner
uses the application's actual transport and source validator, stops on a failed generation,
and counts cases not run separately. Its reference expectations test synthetic extraction
agreement, including negation, uncertainty, history, units and explicit timing. They are not
independent clinical reference labels, sensitivity/specificity or real-patient accuracy.

Official references checked for this review: [Ollama generate completion metadata and schema format](https://docs.ollama.com/api/generate),
[Ollama context-window configuration](https://docs.ollama.com/faq),
[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
and the [MedGemma model cards](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card).
Installed model metadata, rather than a model name alone, determines the capability checks.


### October 22 safety checks (research preview)

The browser rejects a `present` assertion when its quoted sentence or immediate source prefix begins
with an explicit English negation (`no`, `without`, `negative for`). This is a conservative abstention
check, not a validated clinical negation classifier: it can over-reject mixed clauses and does not
cover every language, uncertainty expression, historical context or omitted finding. It never
changes an assertion to a different clinical meaning. The original report still requires review.

Recommendation-like English source sentences that the model did not quote as follow-up are shown
separately for human review, including conditional or negated recommendations. No finding link,
follow-up action or deadline is inferred. This mitigates a recorded synthetic model failure; it does
not prove that the underlying model is more accurate. Independent clinician reference labels,
clinician review of these checks, and task-specific evaluation remain required for clinical use.

The hospital second-reader boundary now refuses empty, oversized (over 6000 UTF-8 bytes), invalid
or explicitly incomplete answers rather than silently trimming input or accepting partial reads.
It returns generic errors without model payloads. These boundary checks do not change guideline
rules or authorize patient care.

The report catalogue independently loads saved synthetic reports while optional live connectivity
is checked. Case changes clear old readings; late responses cannot replace a newer selection.

For authentication, an unset `CLINLOOP_API_TOKENS` creates no administrator account. Configure
credentials in a protected service environment or configure hospital SSO before deploying this
update to a private server. Never recover credentials from logs. Existing running services are not
changed by preparing or publishing the static website files.


## 2026-10-26 software-only update candidate

Connection failures now distinguish local Ollama, the named research gateway, and missing review
setup. The local address belongs to the browser's device: opening the public page on a phone does
not connect it to another computer's loopback server. Local-network permission is a browser control;
an embedded browser may still block access after server-side origin checks pass.

The synthetic evaluator now checks exact one-to-one source tuples, checkpoint identity at both run
boundaries, separate attempted/rejected/unrun coverage, and report-type/language breakdowns across
24 fixed developer-authored cases. Legacy plan-wide bounds are labelled coverage penalties, not
measured extraction accuracy. Entirely unrun subgroups have null measured recall. These fixtures
are development checks, not independent clinician reference labels.

The source-bound review-packet tool records pending human review against exact source hashes and
changed lines. Staging unchanged new files does not invalidate a receipt; changed source still does.
It cannot verify medical credentials, create runtime rule approvals, publish code or authorize care.
This software update contains no clinical-rule or learned-model activation.

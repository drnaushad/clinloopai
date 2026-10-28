# Report review: local models and optional research API

This feature is a synthetic-only draft. It does not make the public website a hospital-ready
patient-data system, validate a model or change the follow-up engine's clinical scope.

## Finding the right workspace

Every page offers the same 13 destinations in the same three groups: Clinical workspace,
Research, and Evidence and setup. Phones and tablets use a labelled page selector; larger
screens show those groups as links. The current destination stays selected after resizing
and Back/Forward. The keyboard-operable **Choose a workflow** disclosure explains the
input requirements and links directly to report review, follow-up examples, imaging workflow
information and measured validation evidence. All thirteen menu workspaces provide the same English/Korean language controls, including
Report review, Personal workspace, Live report reader, Validation evidence and International setup.
The mobile page selector and desktop groups follow the selected interface language.

Language is presentation only. The interface translator touches explicitly marked application
labels, help, errors and statuses. It never translates source reports, model responses,
quoted evidence, prompts, input values, units, rule IDs or model identifiers. A visible note
explains why source evidence can remain in a different language. Switching language does not
rerun a model, clear a report, change its type or model, or reset its completeness confirmation.
English/Korean UI copy is engineering-reviewed; this is not clinical language validation.

Display language follows main-menu navigation as `?lang=en` or `?lang=ko`, including the
phone selector and Back/Forward. Only known menu routes and safe document anchors receive
this preference; authentication fields or other query parameters are not propagated to
navigation links. Isolated workspaces read no browser storage for language and retain their
existing session-clearing behavior. Ordinary clinical pages keep their existing optional
display preference. Standalone SMART pages and the separate local provider-key setup are
not part of the thirteen menu workspaces and currently retain their existing language scope.

Report review shows its UTF-8 byte count and the next required step. Review remains disabled
until a model is connected, the complete source is valid and the operator confirms completeness.
Editing the source or changing model/category clears earlier output and the confirmation.
The counter measures bytes rather than characters; it never truncates an oversized report.
Do not remove clinical context simply to meet a size limit.

The container includes all menu pages, the report-review schema, SMART sandbox pages and the
two public evidence documents linked by Validation. Its web root does not expose the full
repository or the internal source-review packet. CI smoke checks exercise every clean menu
route and startup resources, rather than relying solely on the cockpit loading.

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

Provider requests send keys in vendor-specific headers, never in URL queries, public website code or
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

### Guided local key setup

For a form instead of terminal key entry, install the pinned API dependencies in an isolated
Python environment and run this command from the repository:

```sh
python scripts/run_research_review.py --setup
```

1. Open `http://127.0.0.1:18127/setup` on the computer running the gateway. Copy the
   **gateway access code** from the protected file named in the terminal; paste it into setup.
2. Select OpenAI, Anthropic (Claude) or Google Gemini. Enter your provider API key and an
   exact model ID supporting JSON structured output. Select **Use this provider**. Repeat
   for another provider if needed. This only saves configuration; it makes no provider request
   or charge and does not verify account access or model compatibility.
3. Open `https://clinloopai.app/review`, choose **Research API**, select that same provider,
   and enter the **gateway access code**, never the provider key. Confirm synthetic-only
   external transmission, connect, then add a complete synthetic report and review it.

OpenAI here means its GPT API, not a ChatGPT browser login. Pick a model available in your
provider account; this tool cannot guarantee comparative accuracy from a model name.
Links in local setup lead to official key and model documentation. API billing is managed
by the provider. No paid provider round trip was performed in development.

The setup surface is disabled unless explicitly enabled by `--setup` (or the personal
process setting `CLINLOOP_RESEARCH_LOCAL_SETUP=1`). It accepts key changes only from
`http://127.0.0.1:18127`, a loopback peer, the exact Host, and the separate access code.
It cannot be configured from the public website, an unrelated origin or a remote peer.
Credentials are never returned by status/configuration endpoints. Setup has no report input,
external scripts, analytics, cookies or browser storage. Password fields clear after submission,
provider changes, page exit, form clearing or ten minutes of inactivity. **Clear form** does
not undo a submitted configuration change; check configured providers after interruptions.

Keys entered in this form stay only in gateway process memory until **Forget selected
provider** or process shutdown. Forgetting does not revoke a provider key, clear provider
logs or erase environment-supplied credentials; those can reappear on restart. Concurrent
configuration changes are refused during analysis. Keys are not exposed to the public page.
An unlocked device, extensions or the gateway operator may still access memory. Clearing
fields is not guaranteed secure memory deletion. Use one private gateway per operator.

For a private remote gateway, use the existing loopback SSH tunnel below, then open the
same local setup URL on the laptop. Phones/tablets cannot reach a computer's loopback
address directly. Do not expose this gateway publicly to avoid this limitation.

### Terminal key entry

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
## Unstructured-text evaluation candidate (2026-10-26)

The fixed synthetic evaluator contains 24 cases (18 English, six Korean) covering six text
categories. Added stresses include mixed negation, multiple recommendations with distinct intervals,
an addendum, unreadable laboratory context and an instruction-like document footer. These are
software expectations written by developers, not independent clinician references.

`node tests/test_report_evaluation.cjs` tests the real application transport with stand-in models,
including omitted findings, extra/duplicate findings, wrong assertion/timing, unsupported quotes,
partial output and changed checkpoint identity. This does not call a real LLM.

The optional local inference command in the README records checkpoint, prompt, schema, fixtures and
executable hashes. Exact tuple matching uses the full source quote, assertion, follow-up quote and
timing quote; it is one-to-one. Clinically equivalent alternate quotations may score as mismatches.
Metrics schema 2 separates attempted cases, rejected responses and unrun cases. Precision is
conditional on accepted output. Attempted-case recall includes rejected responses as abstentions;
unrun cases contribute no measured misses or recall. Legacy plan-wide recall/F1 fields remain
explicitly labelled conservative coverage bounds, not measured extraction accuracy. Report-type and
language results include attempted and accepted coverage; an entirely unrun subgroup has null measured
recall. Incomplete runs cannot support a complete paired model comparison.
Separate error counts describe assertion, follow-up and timing errors only when the source quotation
matches. No confidence intervals or clinical-equivalence/clinical-performance claims are made.

No images, DICOM, PDF/OCR or waveforms enter this evaluator. Modality-specific models require their
own capability checks, reference data and acceptance studies. No model comparison authorizes care.


The earlier two-case CPU pilot was rescored under schema 2 without new inference, changed prompts or
changed reference expectations. Its 22 unrun cases remain unrun. Rescoring an old run neither improves
the model nor establishes clinical performance. Model availability, schema/source rejection and lack
of independent labels remain open requirements.

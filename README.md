# ClinLoop AI — Closed-Loop Clinical Safety Monitoring

> 설명가능 AI 기반 미완결 진료루프 탐지·종결 지원 플랫폼
> **Live demo:** [https://clinloopai.app](https://clinloopai.app)

ClinLoop AI tracks **clinical obligations**, not diagnoses. Examples: an abnormal lab that must be
communicated, an incidental lung nodule that needs a follow-up CT, a warfarin dose change that needs
an INR recheck, a referral that needs a visit. When a required follow-up does not happen within its
guideline window, ClinLoop flags the **open loop**, scores its risk, and explains why. It does this
with transparent, rule-grounded logic and an audit trail.

> ⚠️ **Research prototype.** Everything in this repository runs on **synthetic** patient data. It is
> not a medical device, has not been clinically validated, and must not be used for patient care.
> Several components (EHR/PACS connectors, counterfactual survival paths, LLM baselines) are
> **simulations or fixed lookup tables**. See [Implementation status](#implementation-status).

---

## How it works

```
 Hospital FHIR R4 ──► FHIR sync / adapter ──► Detection engine ──────────────► Loop registry ──► Clinician worklist
 server (read-only)   (changed patients →     Temporal Hypergraph → Safety      (owner, ack,      (ranked, evidence,
 or uploaded export    full history; status-   Clock → Risk Scorer: which        defer, close,     acknowledge / defer /
                       aware, evidence spans)  obligations are open, overdue,    escalation,       close / message patient)
                                               and how dangerous                 audit, feed alarm)        │
                                                                                                           ▼
                                                                  Patient outreach: draft → clinician approval → send
```

1. **Obligation rules** (`clinical_ontology.py`): 36 guideline-based rules, each with a trigger, its
   required follow-ups (all or any), a deadline, a severity, references, a Korean name, and a
   `review_status` (all currently `pending_specialist_review`). Example:
   `□(LAB_RESULT[abnormal_pap] → ◇≤30d COLPOSCOPY_REFERRAL)`.

   | Rules | Covers |
   | --- | --- |
   | R001–R016 | Abnormal labs, incidental lung nodules (size-aware Fleischner windows), cervical cytology, post-discharge cultures, anticoagulation and drug monitoring, referrals, pathology, post-MI and new heart failure |
   | R017–R022 (Wave 1) | Positive FIT → colonoscopy, BI-RADS 4/5 → biopsy, Lung-RADS 4A and 4B/4X, abnormal result after discharge, critical value → clinician notified within 1 hour |
   | R023–R029 (Wave 2) | Heart-failure discharge → visit ≤7 days; postpartum BP check after hypertensive disorder of pregnancy (≤72 h if severe); gestational diabetes → postpartum glucose test; HCV antibody → RNA; HCC surveillance imaging every 6 months for chronic HBV or cirrhosis; self-harm or psychiatric discharge → mental-health follow-up ≤7 days (clinician-handled only) |
   | R030–R033 | Follow-up CT / MRI / ultrasound / radiograph **recommended in the radiology report**, with the deadline taken from the report itself (30-day default when no interval is stated) |
   | R034–R036 | Lung-RADS 3 → 6-month LDCT; critical imaging finding (acute PE, dissection, haemorrhage, pneumothorax, free air) → documented clinician communication within 1 hour; radiologist-recommended biopsy/FNA |
2. **Temporal hypergraph** (`temporal_hypergraph.py`): builds one hyperedge per triggered rule and
   marks it `closed`, `open` or `delayed`.
3. **Safety clock** (`safety_clock.py`): converts elapsed time against the deadline into a time-risk
   score and a colour state.
4. **Risk scorer** (`risk_scorer.py`): combines the factors and can **abstain**
   (`needs_human_review`) when the data are too sparse.
5. **Loop detector** (`loop_detector.py`): runs the pipeline per patient and returns ranked
   detections with full explanations.
6. **FHIR adapter** (`fhir_ingest.py`): maps hospital FHIR R4 resources to events. FHIR status is
   preserved (a *booked* appointment is not a completed one), report text extraction is
   negation-aware and records its evidence span, and every event says how it was mapped.
7. **FHIR sync** (`fhir_sync.py`): pulls from the hospital's FHIR server on a schedule. It finds
   patients whose records changed, then evaluates each one's full history, since an incremental
   pull alone would make earlier follow-ups look missing.
8. **Loop registry** (`loop_store.py`): remembers each loop's owner and workflow state, escalates
   unacknowledged overdue loops, computes the open-loop rate, keeps a hash-chained audit log, and
   **raises an alarm when the data feed goes silent**. A safety net fed by a dead interface shows an
   empty, reassuring worklist, which is worse than no safety net.
9. **Patient outreach** (`outreach.py`): diagnosis-free messages, sent only after clinician
   approval, through the hospital's own messaging integration. ClinLoop stores no contact details.

---

## Repository structure

```
clinloopai/
├── README.md                     # This file
├── AGENTS.md                     # Guidelines for AI coding agents working on this repo
├── requirements.txt              # Core Python dependencies (engine, benchmark, tests)
│
├── src/
│   ├── model.py                  # High-level API: ClinLoopModel.detect_loops() / explain()
│   ├── data_loader.py            # Load / generate / tabulate synthetic trajectories
│   ├── run_benchmark.py          # End-to-end benchmark entry point
│   ├── tests/test_noble_engine.py# Tests for counterfactual, outreach, BioMCP modules
│   ├── validation/chart_review.py# Stage 1 chart-review study toolkit (sampling, blinding, metrics)
│   └── clinloop_engine/
│       ├── clinical_ontology.py      # Event types, severities, obligation rules R001–R022
│       ├── temporal_hypergraph.py    # Dynamic Temporal Hypergraph (obligation matching)
│       ├── safety_clock.py           # SafetyClock (time risk) + background watchdog loop
│       ├── risk_scorer.py            # Multi-factor risk + abstention
│       ├── loop_detector.py          # Main detection pipeline
│       ├── data_generator.py         # Seeded synthetic scenario generator (seed 42)
│       ├── baselines.py              # Simulated EMR-inbox and LLM baselines
│       ├── benchmark.py              # Metrics (sens/spec/F1/AUROC/PR-AUC/alert burden)
│       ├── visualizer.py             # ROC / PR / bar / alert-fatigue figures
│       ├── fhir_ingest.py            # FHIR R4 → ClinLoop event adapter
│       ├── fhir_sync.py              # Scheduled read-only sync from a FHIR server
│       ├── outreach.py               # Patient messages: draft → approval → provider (outbox / webhook)
│       ├── literature.py             # Live PubMed / Europe PMC search and service health checks
│       ├── biomcp_client.py          # MCP client for the BioMCP server (stdio or streamable HTTP)
│       ├── loop_store.py             # SQLite loop registry, workflow, escalation, audit, open-loop rate
│       ├── clinical_api.py           # Pilot endpoints: ingest, worklist, actions, metrics
│       ├── auth.py                   # Bearer-token roles: viewer / navigator / clinician / admin
│       ├── api.py                    # FastAPI backend (mounts clinical_api)
│       ├── biomcp_server.py          # Guideline lookup tools (MCP-style, static data)
│       ├── ehr_mcp_server.py         # Mock EHR connector (returns canned responses)
│       ├── pacs_mcp_server.py        # Mock PACS connector (returns canned responses)
│       ├── evidence_agent.py         # Routes context to BioMCP guideline tools
│       ├── patient_outreach_agent.py # Patient message drafting (via local LLM)
│       ├── local_llm_engine.py       # Ollama client (localhost:11434)
│       ├── phi_deidentifier.py       # Pseudonymisation + regex PHI scrubbing
│       ├── counterfactual_engine.py  # Fixed survival-trajectory examples per case
│       ├── gpu_engine.py             # PyTorch demo kernels (untrained model)
│       ├── fhir_integration.py       # FHIR Task / Observation builders
│       ├── digital_signature.py      # HMAC signing of agent execution envelopes
│       ├── agent_execution.py        # Agent execution envelope (audit fields)
│       ├── causal_message.py         # Rule-based message-framing selector
│       ├── sdoh_monitor.py           # Equity (disparity ratio) monitor
│       └── safety/agent_guard.py     # Prompt-injection / unsafe-claim filters
│
├── tests/                        # Engine, FHIR, registry, API and chart-review tests
│
├── index.html, css/, js/         # Static web cockpit (served at clinloopai.app)
├── worklist.html                 # Clinician worklist (talks to the API)
├── data/cases.json               # 5 curated synthetic demo cases used by the web cockpit
├── data/fhir_example_bundle.json # Synthetic FHIR R4 bundle: 7 patients, the main failure modes
├── requirements-api.txt          # API dependencies
├── Dockerfile                    # On-premise image: API + worklist + cockpit + BioMCP
├── docker-compose.yml            # Full stack (API, BioMCP, optional Ollama)
├── install.sh                    # One-command hospital install
├── config.js                     # Tells the pages where the API is (rewritten by the container)
├── .github/workflows/            # Test → build → smoke-test → publish image to GHCR
├── manifest.json, sw.js, icons/  # PWA manifest and service worker
├── CNAME                         # Custom domain for static hosting
│
└── generate_monograph.py,        # Build the Word monograph (needs python-docx and an
    build_full_monograph.py       #   existing ClinLoop_AI_Package/ output directory)
```

Generated at runtime (not committed): `data/synthetic/` (300 scenario JSON files), `results/`
(benchmark JSON and figures) and `data/clinloop.db` (the loop registry).

---

## Installation

### Hospitals: one command

On a Linux server with Docker:

```bash
curl -fsSL https://raw.githubusercontent.com/drnaushad/clinloopai/main/install.sh | bash
```

This installs into `~/clinloop`. It creates a private `.env` with a new admin token and signing
key, pulls the published images, and starts:
- the ClinLoop API, worklist and cockpit;
- BioMCP;
- a local LLM (Ollama with EXAONE 3.5).

When it finishes, open **http://localhost:8124/worklist.html** and sign in with the printed admin
token. Re-running the command updates to the latest image and keeps the existing `.env`.

| Option | Example |
| --- | --- |
| Install directory | `CLINLOOP_DIR=/opt/clinloop` |
| Skip the bundled LLM (Ollama already runs on this host) | `CLINLOOP_LLM=0` |
| Pin a released version | `CLINLOOP_VERSION=1.0.0` |

Pass options like this: `curl -fsSL …/install.sh | CLINLOOP_LLM=0 bash`.

Images are published automatically to `ghcr.io/drnaushad/clinloopai` for amd64 and arm64:
- `:latest` on every change to `main`;
- `:1.2.3` / `:1.2` for version tags.

Each image is published only after the tests pass and a smoke test of the built container succeeds
(`.github/workflows/docker-publish.yml`).

For clinicians on the hospital network, put an HTTPS reverse proxy (e.g. nginx with the hospital
certificate) in front of port 8124 rather than exposing it over plain HTTP.

### Developers

**Requirements:** Python **3.10+** (tested on 3.13), `pip`, and git. A GPU is not required.

```bash
git clone https://github.com/drnaushad/clinloopai.git
cd clinloopai

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt    # core engine, benchmark, figures
pip install pytest                 # to run the test suite
```

### Optional extras

| Feature | Extra install |
| --- | --- |
| REST API, worklist, FHIR ingest | `pip install -r requirements-api.txt` |
| GPU demo endpoints | `pip install torch` (optional; without it those endpoints return 503) |
| Local LLM (patient-message drafts) | Install [Ollama](https://ollama.com), then `./scripts/setup_local_llm.sh` (pulls `exaone3.5:7.8b`). Without it, messages use a fixed safe template |
| BioMCP | Included in `requirements-api.txt` (`biomcp-python`); ClinLoop starts it automatically |
| Word monograph scripts | `pip install python-docx` and `mkdir ClinLoop_AI_Package` |

---

## Running

Run every command from the **repository root**. The code imports modules as `src.…`.

### 1. Tests

```bash
python -m pytest tests/ src/tests/ -v            # 153 tests
```

The API tests are skipped automatically when `requirements-api.txt` is not installed.

`tests/test_clinloop.py` includes patient-safety regression tests. Each one pins a failure mode
that would silently drop a patient: a partially completed follow-up counted as closed, a cancelled
CT counted as done, an overdue critical alert downgraded, a wrong guideline window applied.

### 2. Benchmark

```bash
python src/run_benchmark.py
```

This script:
1. generates 300 seeded synthetic trajectories into `data/synthetic/`,
2. runs ClinLoop AI and the two baselines,
3. writes `results/benchmark_results.json`,
4. saves four figures, `results/fig1_roc_curves.png` … `fig4_alert_fatigue.png`.

It takes a few seconds.

### 3. Use the engine from Python

```python
from datetime import datetime
from src.model import get_model

model = get_model(evaluation_time=datetime(2026, 4, 1))   # pin "now" for reproducibility
events = [
    {"event_id": "E1", "patient_id": "P001", "event_type": "radiology_report",
     "timestamp": "2026-01-10T09:00:00",
     "details": {"finding": "incidental_pulmonary_nodule", "nodule_size_mm": 8.2}},
]
for det in model.detect_loops("P001", events, scenario_id="demo-1"):
    print(model.explain(det))
```

Valid `event_type` values are listed in `EventType` in `src/clinloop_engine/clinical_ontology.py`.
Give a rule's trigger condition explicitly with `details["condition"]` (for example
`"abnormal_cervical_cytology"`, `"anticoagulant_dose_change"`). Timestamps may be timezone-aware
(`+09:00`, `Z`) or naive; aware values are converted to UTC and naive values are treated as UTC.
Give each event a `status`: only follow-ups that actually happened close a loop. `cancelled`,
`no_show`, `scheduled`, `pending` and similar statuses do not.

### 4. Clinical pilot: API and worklist

```bash
pip install -r requirements-api.txt

# One token per person: token:user:role  (roles: viewer, navigator, clinician, admin)
export CLINLOOP_API_TOKENS="$(openssl rand -hex 16):dr.lee:admin,$(openssl rand -hex 16):nurse.park:navigator"
export CLINLOOP_SIGNING_KEY="$(openssl rand -hex 32)"
echo "$CLINLOOP_API_TOKENS"          # hand each person their token

uvicorn src.clinloop_engine.api:app --host 127.0.0.1 --port 8124      # API + docs at /docs
python3 -m http.server 8123 --bind 127.0.0.1                           # in a second terminal
```

Open <http://localhost:8123/worklist.html>, sign in with the admin token, and click **Load synthetic
FHIR example**. Seven synthetic patients are ingested and their open loops appear, most dangerous
first:
- a positive culture after discharge with no callback;
- a 12 mm nodule whose follow-up CT was a no-show;
- colon cancer on biopsy with no referral;
- a positive FIT with no colonoscopy.

The worklist opens in Korean or English, following the browser setting; the toggle switches
between them. For each loop you can:
- acknowledge it, assign it (to yourself or someone else), and filter to **my loops**;
- defer it with a coded reason;
- close it with evidence;
- draft a diagnosis-free message to the patient, which a clinician approves (optionally editing it)
  before it is sent.

A banner at the top turns red when the data feed is silent or failing. Every action is written to
the audit trail.

Ingesting a real FHIR export instead (admin token):

```bash
curl -X POST http://127.0.0.1:8124/api/v1/fhir/ingest \
     -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
     --data @export_bundle.json
```

Key endpoints (all except `/rules` and `/health` require a token):

| Endpoint | Role | Purpose |
| --- | --- | --- |
| `GET /api/v1/rules` | public | The rule library, with references and review status |
| `POST /api/v1/fhir/ingest` | admin | Map a FHIR Bundle, run the engine, record loops |
| `GET /api/v1/worklist` | viewer | Active loops, ranked |
| `POST /api/v1/loops/{key}/acknowledge` | navigator | Take ownership of the next step |
| `POST /api/v1/loops/{key}/defer` | navigator / clinician | Coded reason; clinical reasons need a clinician |
| `POST /api/v1/loops/{key}/close` | navigator | Requires evidence of the completed follow-up |
| `GET /api/v1/metrics/open-loop-rate?stratify_by=` | viewer | Quality measure by rule, language, age group, sex |
| `POST /api/v1/loops/{key}/outreach` | navigator | Draft a patient message (blocked for clinician-handled rules) |
| `POST /api/v1/outreach/{id}/decision` | clinician | Approve (optionally edited) and send, or reject |
| `GET /api/v1/feed/status` | viewer | Data feed `OK` / `STALE` / `FAILING` / `NEVER` |
| `POST /api/v1/fhir/sync` | admin | Run one sync from the configured FHIR server now |
| `GET /api/v1/biomcp/status` | viewer | BioMCP connection and the tools ClinLoop may call |
| `POST /api/v1/biomcp/call` | viewer | Call a read-only BioMCP tool (articles, trials, openFDA, genes, variants) |
| `GET /api/v1/audit/verify` | admin | Verify the audit hash chain |
| `GET /api/v1/connections/status` | public | What is really connected, checked live (no hostnames, secrets or patient data) |
| `GET /api/v1/evidence/{rule_id}?source=pubmed\|europepmc` | public | Live literature for a rule (rule-level search terms only) |

Overdue loops nobody has acknowledged escalate automatically: owner → department lead → patient
safety officer. Each step waits a severity-specific grace period (1 hour for critical).

Without `CLINLOOP_API_TOKENS`, the API generates a one-time admin token and logs it, so it is never
open by default. CORS is limited to the cockpit origins (`CLINLOOP_CORS_ORIGINS` overrides).

Configuration:

| Variable | Purpose | Default |
| --- | --- | --- |
| `CLINLOOP_API_TOKENS` | `token:user:role,…` | one-time admin token |
| `CLINLOOP_SIGNING_KEY` | Key for agent audit signatures | per-process random |
| `CLINLOOP_DB` | Loop registry (SQLite) | `data/clinloop.db` |
| `CLINLOOP_FHIR_BASE` / `CLINLOOP_FHIR_TOKEN` | Hospital FHIR server and read-only token; enables background sync | sync off |
| `CLINLOOP_FHIR_SYNC_MINUTES` / `CLINLOOP_FHIR_INITIAL_DAYS` | Sync interval / first-sync look-back | 15 / 365 |
| `CLINLOOP_FEED_MAX_SILENCE_HOURS` | Feed alarm threshold | 24 |
| `CLINLOOP_OUTREACH_PROVIDER` | `outbox` (local JSONL, nothing leaves the server) or `webhook` | `outbox` |
| `CLINLOOP_OUTREACH_WEBHOOK_URL` | Hospital integration endpoint for KakaoTalk/SMS delivery | — |
| `CLINLOOP_OUTBOX` | Outbox file path | `data/outbox.jsonl` |
| `CLINLOOP_CORS_ORIGINS` | Allowed browser origins | cockpit origins |
| `NCBI_API_KEY` | Optional NCBI key (10 instead of 3 PubMed requests/s) | — |
| `CLINLOOP_LITERATURE` | `off` disables all outbound PubMed / Europe PMC calls | on |
| `CLINLOOP_BIOMCP_URL` | BioMCP over streamable HTTP, e.g. `http://biomcp:8000/mcp` | stdio: runs `biomcp run` |
| `CLINLOOP_BIOMCP_COMMAND` | Command used for stdio BioMCP | `biomcp run` |
| `CLINLOOP_OLLAMA_URL` | Ollama address | `http://localhost:11434` |
| `CLINLOOP_LLM_MODEL` | Force a specific installed model | best installed (EXAONE 3.5 first) |

One-off sync from the command line: `python -m src.clinloop_engine.fhir_sync --once`.

#### BioMCP and the local LLM

**BioMCP** is the open-source biomedical MCP server (PubMed/PubTator3, ClinicalTrials.gov, openFDA,
MyGene/MyVariant). ClinLoop connects to it as an MCP client: by default it launches `biomcp run`
over stdio, or it connects to `CLINLOOP_BIOMCP_URL` (streamable HTTP). Only read-only tools on an
allowlist can be called, and only rule-level search terms are sent. When BioMCP's upstream sources
are unreachable it returns an empty list; ClinLoop labels that explicitly so that "no results" is
never mistaken for "no evidence".

**The local LLM** is an Ollama server inside the hospital network. It drafts patient messages from
diagnosis-free facts, and a clinician approves every message. EXAONE 3.5 (Korean/English) is
preferred, any installed model is used as a fallback, and reasoning text from models such as
DeepSeek-R1 (`<think>…</think>`) is removed before anyone sees it.

Both appear in the Connections panel with their live status.

#### Docker

`install.sh` (above) is the simplest route. By hand, next to a `.env` file that sets
`CLINLOOP_API_TOKENS` and `CLINLOOP_SIGNING_KEY`:

```bash
COMPOSE_PROFILES=llm docker compose up -d     # API + BioMCP + Ollama + model download
docker compose up -d                          # without the bundled LLM
```

The container serves the worklist and cockpit itself, at `http://localhost:8124/worklist.html`
and `http://localhost:8124/`. It is published on `127.0.0.1` only; BioMCP and Ollama stay inside
the compose network. For an NVIDIA GPU, uncomment the `deploy` block of the `ollama` service.

Single container, API and UI only:

```bash
docker run -p 127.0.0.1:8124:8124 -v clinloop-data:/var/lib/clinloop \
  -e CLINLOOP_API_TOKENS -e CLINLOOP_SIGNING_KEY ghcr.io/drnaushad/clinloopai:latest
```

Build locally instead of pulling: `docker build -t ghcr.io/drnaushad/clinloopai:latest .`

`/api/v1/agent/safety-clock/status` reports the background watchdog over the cockpit demo cases.

### 5. Web cockpit (static demo)

```bash
python3 -m http.server 8123
# open http://localhost:8123/
```

The cockpit loads `data/cases.json` directly. Its local-LLM panel works only when the cockpit is
served from `localhost` with the API and Ollama running. On the public site it states that the
on-premise LLM is unavailable.

### 6. Stage 1 validation study (chart review)

```bash
# Draw a stratified sample of loops from a FHIR export; reviewers get a blinded packet
python -m src.validation.chart_review sample --fhir export_bundle.json --out review/ --per-stratum 20

# Two clinicians fill reviewer_1 / reviewer_2 (yes / no / unclear: "follow-up completed in time?"),
# an adjudicator resolves disagreements, then:
python -m src.validation.chart_review analyze --packet review/review_packet.csv --key review/prediction_key.csv
```

The analysis reports weighted sensitivity, specificity, PPV and NPV with stratified-bootstrap 95% CIs,
per-rule results, and Cohen's kappa between reviewers. This is the study that turns ClinLoop's
accuracy from a claim into a measurement.

---

## Benchmark results (synthetic, n = 300)

From `python src/run_benchmark.py`. The evaluation clock is fixed at 2027-01-01, after the last
synthetic event, so results are identical on every run.

| Metric | EMR inbox (simulated) | LLM zero-shot (simulated) | **ClinLoop AI** |
| --- | :---: | :---: | :---: |
| Sensitivity | 0.259 | 0.790 | 1.000 |
| Specificity | 0.684 | 0.895 | 1.000 |
| Precision | 0.639 | 0.942 | 1.000 |
| F1 | 0.368 | 0.859 | 1.000 |
| False alerts / 100 patients | 10.0 | 3.3 | 0.0 |

**This is a rule-conformance test, not an accuracy result.**

- **Labels and detector share the same rules.** The generator writes its ground-truth labels from
  the guideline rules the detector implements. A perfect score shows only that the engine
  implements its specification without error. Clinical accuracy can only be measured against
  clinician chart review of real records.
- **The baselines are not real models.** `EMRInboxBaseline` and `LLMBaseline` read the ground-truth
  label and add random errors at hard-coded rates. They illustrate known failure modes and are not
  measured comparators.

---

## Implementation status

| Component | Status |
| --- | --- |
| Obligation rules, hypergraph, safety clock, risk scorer, loop detector | **Implemented** (deterministic, tested). Rules await specialist sign-off |
| FHIR R4 ingestion | **Implemented** for 8 resource types; LOINC lists and text patterns need checking against each hospital's coding |
| Loop registry, workflow, escalation, audit, open-loop rate | **Implemented** (SQLite) |
| API authentication | **Implemented**: bearer tokens with roles. Not yet integrated with hospital SSO |
| Clinician worklist | **Implemented** (`worklist.html`): Korean/English, assignment, my loops, outreach approval |
| FHIR server sync | **Implemented** (bearer token). SMART Backend Services token exchange not yet built |
| Data-feed monitoring | **Implemented**: OK / STALE / FAILING / NEVER, audited alarm |
| Patient outreach | **Implemented** with clinician approval. Real delivery requires the hospital's KakaoTalk/SMS integration behind the webhook |
| Stage 1 validation toolkit | **Implemented**; awaits IRB approval and real data |
| Synthetic data generator, benchmark, figures | **Implemented** (seeded) |
| BioMCP | **Connected** over MCP (stdio or streamable HTTP) to the open-source BioMCP server: 36 tools, read-only allowlist |
| Built-in guideline library | Static, curated guideline citations in code (`biomcp_server.py`, `/api/v1/guidelines/call`) |
| EHR / PACS connectors | **Mock**: responses are labelled `simulated` |
| PubMed / Europe PMC | **Live** through the ClinLoop server: per-rule literature search and health checks. Only rule-level search terms are sent; never patient data |
| Connection status | The cockpit's badges, the "Live connections" count and the Connections panel show only what the server has verified. On the public site, with no server, they read "not connected" |
| OMOP CDM, EHR writeback, cloud LLMs | **Not connected** (OMOP: no database; EHR: read-only by design; cloud LLMs: not used) |
| Counterfactual engine | **Fixed lookup table** of hand-written, illustrative trajectories for specific case IDs; no Markov simulation runs. The API and cockpit label them as not clinically validated |
| GPU engine | PyTorch network with **untrained random weights**; its "confidence" output has no clinical meaning |
| Safety-clock watchdog | **Implemented**: runs the detection engine over the demo cases and escalates deadline violations |
| Patient outreach agent | Drafts messages with the local LLM (Ollama, configurable address and model) from diagnosis-free facts. It strips model reasoning, blocks definitive clinical claims, and falls back to a fixed safe message |
| PHI de-identifier | Pseudonymises structured fields and scrubs embedded names, MRNs, resident numbers, phone numbers, dates and Korean addresses from free text. It **cannot** detect names of people absent from the structured record, so human review is still required before any external transmission |
| API health-economics / ethics-charter endpoints | Report the planned evaluation and the honest status of each safety pillar. No outcomes have been measured |
| API key test endpoint | Not implemented; reports `not_verified` |

---

## Roadmap

[`docs/LIFE_SAVING_ROADMAP.md`](docs/LIFE_SAVING_ROADMAP.md) sets out how ClinLoop moves from a
synthetic-data prototype to a system proven to save lives: clinical scope, scientific
contributions, validation studies and deployment.

## Data protection

- Commit only synthetic data. Never commit real patient records, exports, or credentials.
- `data/cases.json` contains synthetic demo patients only.
- Audit signatures use `CLINLOOP_SIGNING_KEY`; supply it from a managed secret store in any real
  deployment.

## Key references

- Callen JL et al. *Failure to follow-up test results for ambulatory patients.* J Gen Intern Med 2012 (PMID 22183961)
- WHO, *Global Patient Safety Report* 2024
- MacMahon H et al. *Fleischner Society guidelines for incidental pulmonary nodules*, Radiology 2017
- Perkins RB et al. *ASCCP Risk-Based Management Consensus Guidelines*, 2019/2020

# ClinLoop AI — Closed-Loop Clinical Safety Monitoring

> 설명가능 AI 기반 미완결 진료루프 탐지·종결 지원 플랫폼
> **Website:** [https://clinloopai.app](https://clinloopai.app) shows the cockpit on five synthetic
> cases. The clinical pages (worklist, patient graph, imaging, quality, rule sign-off) need a ClinLoop
> server; to try them, run the [public demo](#try-the-full-app-public-demo) (one click or one command).

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

1. **Obligation rules** (`clinical_ontology.py`): 58 guideline-based rules, each with a trigger, its
   required follow-ups (all or any), a deadline, a severity, references and a Korean name. None is
   fit for patient care until a specialist signs it off (see **Governance** below). Example:
   `□(LAB_RESULT[abnormal_pap] → ◇≤30d COLPOSCOPY_REFERRAL)`.

   | Rules | Covers |
   | --- | --- |
   | R001–R016 | Abnormal labs, incidental lung nodules (Fleischner 2017, see below), cervical cytology, post-discharge cultures, anticoagulation and drug monitoring, referrals, pathology, post-MI and new heart failure |
   | R017–R022 (Wave 1) | Positive FIT → colonoscopy, BI-RADS 4/5 → biopsy, Lung-RADS 4A and 4B/4X, abnormal result after discharge, critical value → clinician notified within 1 hour |
   | R023–R029 (Wave 2) | Heart-failure discharge → visit ≤7 days; postpartum BP check after hypertensive disorder of pregnancy (≤72 h if severe); gestational diabetes → postpartum glucose test; HCV antibody → RNA; HCC surveillance imaging every 6 months for chronic HBV or cirrhosis; self-harm or psychiatric discharge → mental-health follow-up ≤7 days (clinician-handled only) |
   | R030–R033 | Follow-up CT / MRI / ultrasound / radiograph **recommended in the radiology report**, with the deadline taken from the report itself (30-day default when no interval is stated) |
   | R034–R036 | Lung-RADS 3 → 6-month LDCT; critical imaging finding (from the hospital-approved list) → documented clinician communication within its window; radiologist-recommended biopsy/FNA |
   | R037–R046 | ACR incidental findings without a written recommendation: adrenal nodule (1–4 cm → CT/MRI; ≥4 cm or with cancer → work-up), renal mass (solid/Bosniak III–IV → urology; IIF or indeterminate → CT/MRI), pancreatic cyst (size-based MRI; worrisome features → EUS), thyroid nodule on CT/MRI/PET (→ ultrasound), abdominal aortic aneurysm (diameter-based surveillance; ≥5.5 cm, ≥5.0 cm in women → vascular surgery); growing or suspicious lung nodule → work-up |
   | R047 | Imaging-AI finding (approved product or ClinLoop's model runner) that the radiology report does not address → radiologist review (1 day for critical findings, 7 days otherwise) |
   | R056 | The same lung nodule, linked across reports by lobe and size, measured ≥ 2 mm larger than before when the report does not say so (with volume-doubling time) → radiologist confirmation and work-up |
   | R057 | Critical imaging-AI finding (intracranial haemorrhage, pneumothorax, free air) on a study with no report yet → read the study now (60 minutes by default); closed by the study's first report |
   | R058 | Report item no rule tracked, found by the hospital's own model as a second reader (exact quote required) → clinician review; never opens or closes a clinical obligation itself |
   | R052–R055 | Diagnostic patterns across events: iron-deficiency anaemia → GI investigation; creatinine rise (AKI warning) → repeat creatinine; atrial fibrillation with high CHA₂DS₂-VASc and no anticoagulant → anticoagulation decision; persistent microscopic haematuria → urology. See [`docs/DIAGNOSTIC_PATTERNS.md`](docs/DIAGNOSTIC_PATTERNS.md) |
   | R048–R051 | Plans written in clinicians' notes (English and Korean): repeat a lab test, imaging, a specialist referral, a follow-up visit. Each closes only on the matching event (same test, same modality and region, same specialty). Conditional, cancelled and already-done plans are not tracked |
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
   **Radiology reports** (`radiology.py`) are read in two steps: findings from each report, then
   obligations decided with the patient's context (age, sex, smoking status, cancer history,
   earlier reports):
   - *Fleischner 2017*: solid, part-solid and ground-glass; single or multiple; low or high risk
     (unknown risk is managed as high risk); stepped follow-up of a known nodule; growth → work-up;
     age < 35, cancer or immunocompromise → human review. Screening LDCT follows Lung-RADS instead.
   - *ACR incidental findings* (adrenal, renal/Bosniak, pancreatic cyst, thyroid/TI-RADS, aorta)
     when the radiologist wrote no recommendation; when they did, their recommendation is tracked.
   - *Body region*: a follow-up study closes a loop only if it covers the region asked for (an
     abdominal CT covers the adrenals; a head CT does not).
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
│   ├── validation/report_validation.py # Report-level validation (blind labels → sensitivity / PPV)
│   └── clinloop_engine/
│       ├── clinical_ontology.py      # Event types, severities, obligation rules R001–R046
│       ├── temporal_hypergraph.py    # Dynamic Temporal Hypergraph (obligation matching)
│       ├── safety_clock.py           # SafetyClock (time risk) + background watchdog loop
│       ├── risk_scorer.py            # Multi-factor risk + abstention
│       ├── loop_detector.py          # Main detection pipeline
│       ├── data_generator.py         # Seeded synthetic scenario generator (seed 42)
│       ├── baselines.py              # Simulated EMR-inbox and LLM baselines
│       ├── benchmark.py              # Metrics (sens/spec/F1/AUROC/PR-AUC/alert burden)
│       ├── visualizer.py             # ROC / PR / bar / alert-fatigue figures
│       ├── fhir_ingest.py            # FHIR R4 → ClinLoop event adapter
│       ├── radiology.py              # Radiology reports: Fleischner, ACR incidental findings, regions, critical findings
│       ├── report_text.py            # Negation-aware report text helpers
│       ├── governance.py             # Specialist rule sign-off, critical-finding list approval, shadow mode
│       ├── imaging_fhir.py           # Imaging studies and imaging-AI findings as FHIR resources
│       ├── pacs_client.py            # PACS study labels over DICOMweb QIDO-RS (read-only, no pixels)
│       ├── ai_review.py              # Imaging AI: findings the report does not address (R047); critical findings on unread studies (R057)
│       ├── imaging_ai.py             # DICOM analysis: header safety checks, study record, imaging models
│       ├── document_reader.py        # Outside reports: PDF text and OCR (Korean/English)
│       ├── ct_organs.py              # CT series: organ segmentation (TotalSegmentator) and measurements
│       ├── imaging_api.py            # Imaging and outside-report endpoints
│       ├── patient_graph.py          # Patient knowledge graph from the temporal hypergraph
│       ├── note_reader.py            # Plans in clinicians' notes (EN/KO) → tracked follow-ups (R048–R051)
│       ├── motifs.py                 # Diagnostic patterns across events (R052–R056, incl. lesion tracking)
│       ├── rule_check.py             # Static check: every rule can fire and every loop can close
│       ├── config/guidelines.json    # Guideline registry: rules citing an outdated edition are flagged
│       ├── config/critical_findings.json # Example critical-finding list (each hospital approves its own)
│       ├── fhir_sync.py              # Scheduled read-only sync from a FHIR server
│       ├── outreach.py               # Patient messages: draft → approval → provider (outbox / webhook)
│       ├── literature.py             # Live PubMed / Europe PMC search and service health checks
│       ├── biomcp_client.py          # MCP client for the BioMCP server (stdio or streamable HTTP)
│       ├── loop_store.py             # SQLite loop registry, workflow, escalation, audit, open-loop rate
│       ├── clinical_api.py           # Pilot endpoints: ingest, worklist, actions, metrics
│       ├── auth.py                   # Bearer-token roles: viewer / navigator / clinician / admin
│       ├── demo.py                   # Public demo mode: synthetic seed, view-only token, no hospital links
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
├── governance.html               # Specialist rule sign-off and critical-finding list approval
├── imaging.html                  # Outside reports (PDF/OCR), DICOM analysis, CT organ measurement
├── patient.html                  # Patient knowledge graph: events, obligations, missing follow-ups
├── quality.html                  # Where follow-up breaks: bottlenecks, missing steps, equity gaps, workload
├── data/cases.json               # 5 curated synthetic demo cases used by the web cockpit
├── data/fhir_example_bundle.json # Synthetic FHIR R4 bundle: 7 patients, the main failure modes
├── requirements-api.txt          # API dependencies
├── Dockerfile                    # On-premise image: API + worklist + cockpit + BioMCP
├── docker-compose.yml            # Full stack (API, BioMCP, optional Ollama)
├── render.yaml                   # One-click public demo (CLINLOOP_DEMO=1, synthetic data only)
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
| DICOM, outside-report PDFs | Included in `requirements-api.txt` (`pydicom`, `pdfplumber`) |
| OCR of scanned reports | `apt install tesseract-ocr tesseract-ocr-kor` (the Docker image includes it) |
| Research chest-X-ray model | `pip install torch torchxrayvision`, then `CLINLOOP_IMAGING_MODELS=txrv`; or build the image with `--build-arg WITH_IMAGING_AI=1`. Research use only |
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
| `CLINLOOP_HISTORY_DAYS` | Obligations whose deadline passed more than this many days ago stay off the worklist (0 = keep all) | 365 |
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

#### Try the full app (public demo)

Demo mode lets anyone use every page through a link, with no risk to real patients:

- **Synthetic data only:** 37 synthetic patients from `data/fhir_example_bundle.json` and
  `data/radiology_test_bundle.json`, loaded into an in-memory database that resets on every restart.
- **View-only token:** a published token, `clinloop-public-demo-viewer`, with the viewer role. The pages
  fill it in and sign in by themselves. It cannot upload reports or images, ingest data, or change a loop.
- **No hospital connections:** FHIR sync, PACS scanning and the second reader are switched off, even if
  their settings are present.
- **Clearly marked:** every page shows a "synthetic patients only" banner.

One command:

```bash
docker run -p 8124:8124 -e CLINLOOP_DEMO=1 ghcr.io/drnaushad/clinloopai:latest
# open http://localhost:8124/worklist.html
```

One click: [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/drnaushad/clinloopai)
uses [`render.yaml`](render.yaml), which runs the same image with `CLINLOOP_DEMO=1` on a free Render
web service; the service's address is then a link anyone can open. The image honours `PORT`, so other
container hosts (Fly.io, Railway, Cloud Run) work the same way.

Never set `CLINLOOP_DEMO` on a server that holds real patient data.

### 5. Web cockpit (static demo)

```bash
python3 -m http.server 8123
# open http://localhost:8123/
```

The cockpit loads `data/cases.json` directly. Its local-LLM panel works only when the cockpit is
served from `localhost` with the API and Ollama running. On the public site it states that the
on-premise LLM is unavailable.

### 6. Imaging: PACS, imaging AI, outside reports, DICOM

See [`docs/IMAGING.md`](docs/IMAGING.md). In short:

- **PACS** (`CLINLOOP_PACS_DICOMWEB`): reads study labels only (modality, body part, date) over
  DICOMweb. "Was the follow-up adrenal CT done?" is then answered from the PACS itself.
- **Automatic image scanning** (`CLINLOOP_IMAGE_SCAN=1`, off by default): new PACS studies are sent
  to the approved imaging-AI products that apply to them. Each study is matched to exactly one
  patient, every image's patient ID is checked, and pixels are never stored. See
  [`docs/IMAGING.md`](docs/IMAGING.md) §4a.
- **Imaging AI as second reader** (`/api/v1/imaging/ai-results`, R047): a finding from an approved
  product that the report does not address asks a radiologist to look again. ClinLoop never
  diagnoses.
- **Outside reports** (`imaging.html`): PDF text or OCR (Tesseract, Korean and English). A person
  checks and corrects the text before filing.
- **DICOM analysis** (`imaging.html`): header safety checks (a wrong-patient image is refused), a
  study record, and imaging models. The built-in research chest-X-ray model is TorchXRayVision;
  approved vendor models can be added for any modality. Pixel data is never stored.
- **CT organ measurement** (`imaging.html`, `CLINLOOP_IMAGING_MODELS=totalseg`): a whole CT series
  is segmented by TotalSegmentator (research use). ClinLoop measures the aorta's short-axis
  diameter (abdominal ≥ 3.0 cm, thoracic ≥ 4.0 cm) and the spleen's length (> 13 cm). An abnormal
  measurement that the report does not mention asks a radiologist to look again (R047).
- **Vision-language model** (`vlm`): for example MedGemma on the hospital's own Ollama or
  OpenAI-compatible server. It gives a draft description, shown but never stored, and findings
  limited to a fixed list. Images are never sent outside the hospital network.
- **Approved vendor products**: see [`docs/VENDOR_IMAGING_AI.md`](docs/VENDOR_IMAGING_AI.md) and the
  placeholder template [`docs/imaging_models.example.json`](docs/imaging_models.example.json).
- **Clinical notes** (`patient.html` → *Read a clinical note*, or FHIR `DocumentReference`): plans
  written in notes ("repeat potassium in 1 week", "3개월 후 흉부 CT", "refer to cardiology") become
  tracked follow-ups (R048–R051), each with its source sentence. See
  [`docs/CLINICAL_NOTES.md`](docs/CLINICAL_NOTES.md); the wider graph-AI plan is in
  [`docs/GRAPH_AI_VISION.md`](docs/GRAPH_AI_VISION.md).
- **Report-reading accuracy**: a blind evaluation by three independent case writers covering 450
  synthetic reports (CT, MRI, X-ray, ultrasound, mammography, pathology; about a third Korean) and 60
  patient follow-up timelines. Scored once on untouched sets:
  - clean impressions: 97% correct;
  - full real-style reports: 80% on the first set, 87.5% after fixes on a new set;
  - follow-up status on timelines: about 85% correct; no follow-up wrongly shown as done once the
    defects found were fixed.

  Method, every defect found and the limits are in
  [`docs/ACCURACY_EVALUATION.md`](docs/ACCURACY_EVALUATION.md).
- **Whole-record test on EHR-style data**: a complete Synthea FHIR bulk export (120 patients, 144,758
  records) and the HL7 FHIR R4 examples ran without errors. An independent blind reviewer listed 210
  obligations:
  - **First pass:** the app found 87 and raised 1,048 loops, mostly noise from prescription renewals,
    known heart failure and dialysis creatinine.
  - **After the fixes:** it finds 149 (71%), 123 with the same status, and raises 194 loops; no follow-up
    is shown as done when it was not.

  Details and remaining disagreements are in [`docs/HOSPITAL_DATA_TEST.md`](docs/HOSPITAL_DATA_TEST.md).
- **Model-based second reader** (`CLINLOOP_SECOND_READER=1`, off by default): the hospital's own
  on-premise model reads each recent report. Any item it quotes word for word that no rule tracked
  goes to a clinician for review (R058).
  - **Coverage:** with a small stand-in model, 16 of the rules' 17 first-pass misses would have
    reached a person.
  - **Workload:** 8% of normal reports were flagged.

  See [`docs/SECOND_READER.md`](docs/SECOND_READER.md).
- **Patient knowledge graph** (`patient.html`, `GET /api/v1/patients/{id}/graph`): every event the
  engine read (diagnoses, lab values, orders, medications, appointments, imaging studies,
  radiology reports, AI findings) on one time axis. Each obligation is drawn as a hyperedge from
  the event that created it to the follow-up that fulfilled it, or to the missing follow-up at
  its deadline, with its evidence chain and worklist state.

### 7. Governance: specialist sign-off and the critical-finding list

No rule should be used for patient care until a named specialist has reviewed it. ClinLoop records
that review; it cannot replace it.

- **Rule sign-off** (`governance.html`, `/api/v1/governance/rules`): a clinician approves, rejects or
  requests changes to a rule. Each sign-off is bound to the rule's **fingerprint** (a hash of its
  definition, plus the radiology decision code for radiology rules). If the rule changes, the
  sign-off becomes "needs re-review". `CLINLOOP_SIGNOFF_APPROVALS` sets how many distinct reviewers
  are required (default 1).
- **Critical-finding list**: ships as an example in `src/clinloop_engine/config/critical_findings.json`
  (ACR communication categories, a window per finding). A hospital copies it and points
  `CLINLOOP_CRITICAL_FINDINGS` at its own version. A clinical leader then approves it on
  `governance.html`. The approval is bound to the file's content hash.
- **Shadow mode** (`CLINLOOP_ENFORCE_SIGNOFF=1`, on by default for new installs): loops from unsigned
  rules are still detected and stored. They are kept off the worklist and never escalate. R035
  also needs the approved critical-finding list.
- Every review and approval goes into the hash-chained audit log.

### 8. Validation studies

**Report reading** (does ClinLoop create the right obligations from each report?):

```bash
# Blind labelling sheet from a FHIR export: de-identified text, patient context, empty expected_rules
python -m src.validation.report_validation template --fhir export_bundle.json --out sheet.csv
# A radiologist fills expected_rules (e.g. "R003;R035"), then:
python -m src.validation.report_validation score --sheet sheet.csv --out result.json
```

This reports per-rule sensitivity and PPV with Wilson 95% intervals, and lists every disagreement
for adjudication. `data/radiology_validation_synthetic.csv` exercises the tool. Its labels were
written by the developers, so its agreement says nothing about real-world accuracy.

**Chart review** (was each follow-up really completed in time?):

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
| Radiology report reading | **Implemented**: Fleischner 2017, Lung-RADS, BI-RADS, TI-RADS, ACR incidental findings, critical findings, body-region matching, English and Korean. Tested on synthetic reports only |
| Governance | **Implemented**: hash-bound specialist sign-off, critical-finding list approval, shadow mode. The sign-offs themselves must come from the hospital's specialists |
| FHIR R4 ingestion | **Implemented** for 8 resource types; LOINC lists and text patterns need checking against each hospital's coding |
| Loop registry, workflow, escalation, audit, open-loop rate | **Implemented** (SQLite) |
| API authentication | **Implemented**: bearer tokens with roles. Not yet integrated with hospital SSO |
| Clinician worklist | **Implemented** (`worklist.html`): Korean/English, assignment, my loops, outreach approval |
| FHIR server sync | **Implemented** (bearer token). SMART Backend Services token exchange not yet built |
| Data-feed monitoring | **Implemented**: OK / STALE / FAILING / NEVER, audited alarm |
| Patient outreach | **Implemented** with clinician approval. Real delivery requires the hospital's KakaoTalk/SMS integration behind the webhook |
| Stage 1 validation toolkits | **Implemented** (report-level and chart review); await IRB approval and real, de-identified data |
| Synthetic data generator, benchmark, figures | **Implemented** (seeded) |
| BioMCP | **Connected** over MCP (stdio or streamable HTTP) to the open-source BioMCP server: 36 tools, read-only allowlist |
| Built-in guideline library | Static, curated guideline citations in code (`biomcp_server.py`, `/api/v1/guidelines/call`) |
| PACS | **Implemented**: study labels over DICOMweb QIDO-RS, with body-region matching. Tested against a stand-in DICOMweb server; not yet against a hospital PACS |
| Imaging AI | **Implemented** as a second reader (R047): approved products' results (FHIR or DICOM SR), plus an on-premise runner. Built-in model: TorchXRayVision (chest X-ray, **research use only**); vendor models over HTTP for any modality. Research findings open no loops by default |
| Outside reports | **Implemented**: PDF text and OCR (Tesseract kor+eng) with a human check before filing |
| DICOM analysis | **Implemented**: header safety checks (wrong patient refused), study record, model plug-ins, preview |
| CT organ measurement | **Implemented, research use**: TotalSegmentator on a whole CT series; aortic diameter, spleen length and organ volumes. Run live here on a public sample CT and a synthetic aneurysm phantom; not validated on hospital CTs |
| Vision-language model | **Adapter implemented**, for MedGemma or similar on an on-premise Ollama/OpenAI-compatible server. Tested against a stand-in server only: the model weights could not be downloaded in the build environment |
| Patient knowledge graph | **Implemented** (`patient.html`): API and bilingual SVG view of events and obligations |
| Follow-up breakdowns | **Implemented** (`quality.html`): bottlenecks by rule and missing step, equity gaps, workload by owner |
| Guideline versions | **Implemented**: registry of current editions. Rules citing an older one are flagged for re-review (today: R013, R025, R054) |
| Diagnostic patterns | **Implemented**: R052–R055 as graph motifs over each patient's events, with evidence links on the patient graph. Synthetic tests only; positive predictive value not yet measured |
| Clinical notes | **Implemented, rule-based**: FHIR `DocumentReference` notes and pasted notes (`patient.html`); plans → R048–R051 with the source sentence. Optional on-premise LLM suggestions, shown for review only. Tested on synthetic notes; extraction accuracy on real notes not yet measured — see [`docs/CLINICAL_NOTES.md`](docs/CLINICAL_NOTES.md) |
| EHR connector (MCP demo) | **Mock**: responses are labelled `simulated` |
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

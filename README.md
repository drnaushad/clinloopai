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
 FHIR R4 export ──► FHIR adapter ──► Detection engine ──────────────────────► Loop registry ──► Clinician worklist
 (Observation,      (status-aware,     Temporal Hypergraph → Safety Clock       (owner, ack,      (ranked, evidence,
  DiagnosticReport,  evidence spans)   → Risk Scorer: which obligations are     defer, close,     acknowledge / defer /
  Appointment, …)                       open, overdue, and how dangerous         escalation,       close with evidence)
                                                                                 hash-chained audit)
```

1. **Obligation rules** (`clinical_ontology.py`): 22 guideline-based rules. R001–R016 cover abnormal
   labs, incidental nodules, cytology, cultures, anticoagulation, referrals and cardiac transitions.
   R017–R022 are the Wave 1 life-saving rules: positive FIT → colonoscopy, BI-RADS 4/5 → biopsy,
   Lung-RADS 4A/4B/4X work-up, abnormal results after discharge, and critical values (clinician
   notified within 1 hour). Each rule has a trigger, its required follow-ups (all or any), a deadline,
   a severity, references, and a `review_status` (all currently `pending_specialist_review`).
   Example rule: `□(LAB_RESULT[abnormal_pap] → ◇≤30d COLPOSCOPY_REFERRAL)`.
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
7. **Loop registry** (`loop_store.py`): remembers each loop's owner and workflow state, escalates
   unacknowledged overdue loops, computes the open-loop rate, and keeps a hash-chained audit log.

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
├── Dockerfile                    # On-premise API image
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
| Local LLM text generation | Install [Ollama](https://ollama.com) and pull a model, e.g. `ollama pull llama3.1`. Without it, LLM endpoints return an "unavailable" result. |
| Word monograph scripts | `pip install python-docx` and `mkdir ClinLoop_AI_Package` |

---

## Running

Run every command from the **repository root**. The code imports modules as `src.…`.

### 1. Tests

```bash
python -m pytest tests/ src/tests/ -v            # 106 tests
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

Each loop can be acknowledged, deferred with a coded reason, or closed with evidence. Every action
is written to the audit trail.

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
| `GET /api/v1/audit/verify` | admin | Verify the audit hash chain |

Overdue loops nobody has acknowledged escalate automatically: owner → department lead → patient
safety officer. Each step waits a severity-specific grace period (1 hour for critical).

Without `CLINLOOP_API_TOKENS`, the API generates a one-time admin token and logs it, so it is never
open by default. CORS is limited to the cockpit origins (`CLINLOOP_CORS_ORIGINS` overrides). The
database path is `CLINLOOP_DB` (default `data/clinloop.db`).

Docker (on-premise; publish the port on localhost only):

```bash
docker build -t clinloop-api .
docker run -p 127.0.0.1:8124:8124 -v clinloop-data:/var/lib/clinloop \
  -e CLINLOOP_API_TOKENS -e CLINLOOP_SIGNING_KEY clinloop-api
```

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
| Clinician worklist | **Implemented** (`worklist.html`) |
| Stage 1 validation toolkit | **Implemented**; awaits IRB approval and real data |
| Synthetic data generator, benchmark, figures | **Implemented** (seeded) |
| BioMCP guideline tools | Static guideline lookup; no live PubMed/guideline retrieval |
| EHR / PACS MCP servers | **Mock**: return canned text and do not connect to any EHR |
| Counterfactual engine | **Fixed lookup table** of hand-written, illustrative trajectories for specific case IDs; no Markov simulation runs. The API and cockpit label them as not clinically validated |
| GPU engine | PyTorch network with **untrained random weights**; its "confidence" output has no clinical meaning |
| Safety-clock watchdog | **Implemented**: runs the detection engine over the demo cases and escalates deadline violations |
| Patient outreach agent | Drafts messages with a local LLM (Ollama). It blocks drafts containing definitive diagnoses, falls back to a fixed safe message, and always requires human review |
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

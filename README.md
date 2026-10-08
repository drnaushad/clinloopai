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
patient events ──► Temporal Hypergraph ──► Safety Clock ──► Risk Scorer ──► prioritized open loops
 (labs, imaging,    (match each trigger      (sigmoid time     (severity × time    + explanation
  referrals, Rx)     to its required          risk, GREEN/      × failure prior ×    + evidence chain
                     follow-ups per rule)     YELLOW/RED/BLACK)  actionability)      + FHIR Task preview
```

1. **Obligation rules** (`clinical_ontology.py`): 16 guideline-based rules (R001–R016). Each has a
   trigger, its required follow-ups, a deadline and a severity. Example rule:
   `□(LAB_RESULT[abnormal_pap] → ◇≤30d COLPOSCOPY_REFERRAL)`.
2. **Temporal hypergraph** (`temporal_hypergraph.py`): builds one hyperedge per triggered rule and
   marks it `closed`, `open` or `delayed`.
3. **Safety clock** (`safety_clock.py`): converts elapsed time against the deadline into a time-risk
   score and a colour state.
4. **Risk scorer** (`risk_scorer.py`): combines the factors and can **abstain**
   (`needs_human_review`) when the data are too sparse.
5. **Loop detector** (`loop_detector.py`): runs the pipeline per patient and returns ranked
   detections with full explanations.

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
│   └── clinloop_engine/
│       ├── clinical_ontology.py      # Event types, severities, obligation rules R001–R016
│       ├── temporal_hypergraph.py    # Dynamic Temporal Hypergraph (obligation matching)
│       ├── safety_clock.py           # SafetyClock (time risk) + background watchdog loop
│       ├── risk_scorer.py            # Multi-factor risk + abstention
│       ├── loop_detector.py          # Main detection pipeline
│       ├── data_generator.py         # Seeded synthetic scenario generator (seed 42)
│       ├── baselines.py              # Simulated EMR-inbox and LLM baselines
│       ├── benchmark.py              # Metrics (sens/spec/F1/AUROC/PR-AUC/alert burden)
│       ├── visualizer.py             # ROC / PR / bar / alert-fatigue figures
│       ├── api.py                    # FastAPI backend for the web cockpit
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
├── tests/test_clinloop.py        # Unit + integration tests for the core engine
│
├── index.html, css/, js/         # Static web cockpit (served at clinloopai.app)
├── data/cases.json               # 5 curated synthetic demo cases used by the web cockpit
├── manifest.json, sw.js, icons/  # PWA manifest and service worker
├── CNAME                         # Custom domain for static hosting
│
└── generate_monograph.py,        # Build the Word monograph (needs python-docx and an
    build_full_monograph.py       #   existing ClinLoop_AI_Package/ output directory)
```

Generated at runtime (not committed): `data/synthetic/` (300 scenario JSON files) and `results/`
(benchmark JSON and figures).

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
| REST API (`api.py`) | `pip install fastapi uvicorn requests torch` (the API imports `gpu_engine`, which needs `torch`; CPU is fine) |
| Local LLM text generation | Install [Ollama](https://ollama.com) and pull a model, e.g. `ollama pull llama3.1`. Without it, LLM endpoints return an "unavailable" result. |
| Word monograph scripts | `pip install python-docx` and `mkdir ClinLoop_AI_Package` |

---

## Running

Run every command from the **repository root**. The code imports modules as `src.…`.

### 1. Tests

```bash
python -m pytest tests/ src/tests/ -v            # 54 tests
```

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

### 4. REST API

```bash
uvicorn src.clinloop_engine.api:app --host 127.0.0.1 --port 8124
# Interactive docs: http://127.0.0.1:8124/docs
```

`/api/v1/agent/safety-clock/status` reports the background watchdog. Every 10 seconds it runs the
full detection engine over `data/cases.json` and lists every obligation past its deadline.

Set `CLINLOOP_SIGNING_KEY` to sign agent audit envelopes with a stable key. Without it, a random
per-process key is used.

The API has **no authentication** and allows CORS from any origin. Keep it bound to `127.0.0.1`.

### 5. Web cockpit (static demo)

```bash
python3 -m http.server 8123
# open http://localhost:8123/
```

The cockpit loads `data/cases.json` directly. Its live-LLM panels call the API on port 8124 when
the API is running.

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
| Obligation rules, hypergraph, safety clock, risk scorer, loop detector | **Implemented** (deterministic, tested) |
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

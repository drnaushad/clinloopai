# ClinLoop AI — Antigravity Agent Guidelines & Rules

## 1. Project Overview
- **Project Name**: ClinLoop AI (설명가능 AI 기반 미완결 진료루프 탐지·종결 지원 플랫폼)
- **Mission**: Clinical AI Integration
- **Team**: ClinLoop AI
- **Core Mission**: Closed-loop clinical safety monitoring. ClinLoop AI does not diagnose disease; it tracks clinical obligations (abnormal lab results, incidental radiological findings, medication reconciliation, and referrals) across time to prevent diagnostic delays and open-loop patient harm.

---

## 2. Directory Structure Conventions
```
ClinLoop_Project/
├── AGENTS.md                          # Persistent instructions and guidelines for AI agents
├── requirements.txt                   # Python project dependencies
├── .gitignore                         # Git ignore rules (data, checkpoints, caches)
│   └── 04_research_plan.md       # Markdown version of research plan
├── src/                               # Core engine & API entrypoints
│   ├── data_loader.py                 # Dataset loading & trajectory preprocessing interface
│   ├── model.py                       # High-level ClinLoop AI model interface
│   ├── run_benchmark.py               # Benchmark runner against baselines
│   └── clinloop_engine/               # Neuro-symbolic core modules
│       ├── clinical_ontology.py       # Clinical event & obligation definitions
│       ├── temporal_hypergraph.py     # Temporal Clinical Obligation Graph (TCOG)
│       ├── safety_clock.py            # Clinical urgency & deadline timers
│       ├── risk_scorer.py             # Multi-factor risk scoring engine
│       ├── loop_detector.py           # Open-loop detection & status resolution
│       ├── data_generator.py          # Synthetic clinical trajectory generator
│       ├── baselines.py               # EMR inbox alert & naive LLM baselines
│       ├── benchmark.py               # Metrics & benchmark evaluation suite
│       └── visualizer.py              # Performance plots & confusion matrix generation
├── tests/                             # Automated test suite
│   └── test_clinloop.py               # Unit & integration tests
├── data/                              # Data directory (synthetic data, gitignored)
└── results/                           # Benchmark charts and evaluation outputs
```

---

## 3. Technology Stack & Coding Standards
- **Python**: Version >= 3.10.
- **Core Libraries**: `numpy`, `pandas`, `scikit-learn`, `networkx`, `matplotlib`, `seaborn`, `scipy`.
- **Package Management**: Use `pip install -r requirements.txt`.
- **Code Style**:
  - Maintain type hints (`from typing import List, Dict, Optional, Tuple`).
  - Keep docstrings informative with clinical and technical context.
  - Ensure all synthetic data generation uses explicit random seeds (`random_state=42`) for full reproducibility.
- **Testing**:
  - Run tests with: `pytest tests/` or `python -m unittest discover -s tests`.
  - Always verify that benchmarks run cleanly with: `python src/run_benchmark.py`.

---

## 4. Research Guidelines
- **Submission Deadline**: October 9, 2026 (18:00 KST).
- **Core Evaluation Criteria**:
  1. **문제인식 (Problem Definition)**: Focus on diagnostic delay, missed follow-ups, and clinical burnout. Cite WHO Patient Safety (2024) and Callen et al. (PMID 22183961).
  2. **실현가능성 (Feasibility)**: Read-only EMR safety layer, deterministic hypergraph + probabilistic risk scoring.
  3. **성장전략 (Growth & Business Model)**: B2B hospital SaaS, initial focus on outpatient abnormal labs, expanding to incidental findings and oncology follow-up.
  4. **팀 역량 (Team Capacity)**: Biomedical AI research foundation, clear roadmap for clinical advisory and regulatory guidance (MFDS).

---

## 5. Agent Workflow Rules
- **Do Not Duplicate**: Check existing files in `src/clinloop_engine/` and `ClinLoop_AI_Package/` before generating new code or documents.
- **Data Protection**: Never output sensitive patient data or commit raw clinical datasets to source control.
- **Explainability**: Prioritize transparent, rule-grounded, audit-ready reasoning over black-box predictions.

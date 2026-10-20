# Local models: roles, registry and measured capacity

ClinLoop uses three on-premise models through Ollama. Each has one role, and none decides follow-up:
the rules do. `GET /api/v1/models/registry` reports, for each role:
- the configured model and whether exactly that model is installed (digest, size, quantisation);
- the capabilities Ollama declares;
- its allowed use;
- its fallback, which is none: a missing model is reported unavailable and its feature does not run.

| Role | Setting | Default | Allowed use |
|---|---|---|---|
| text | `CLINLOOP_LLM_MODEL` | `exaone3.5:7.8b` | Drafts of Korean/English patient messages from the loop's facts; a clinician approves each |
| second_reader | `CLINLOOP_SECOND_READER_MODEL` | `medgemma:27b` | Re-reads reports; exact-quote flags go to a person ([SECOND_READER.md](SECOND_READER.md)) |
| vision | `CLINLOOP_VLM_MODEL` | `medgemma:4b` | Research only; locked off in the core profile |

**No silent substitution.** Before October 2026 the second reader fell back to "the best installed
model" when MedGemma 27B was missing. It now does not run at all, because a reader evaluated as
MedGemma must not quietly become another model.

## Measured on the development server (October 2026)

Single NVIDIA RTX A4500 (20 GB), Ollama 0.33.3, Q4_K_M models, short prompt, 80 output tokens:

| Model | Cold start (load) | Warm reply | Generation | GPU memory |
|---|---|---|---|---|
| exaone3.5:7.8b | 3.5 s (2.9 s) | 0.5 s | 103 tok/s | 5.2 GB |
| medgemma:4b | 3.7 s (3.4 s) | 0.3 s | 141 tok/s | 2.9 GB |
| medgemma:27b | 12.7 s (11.2 s) | 1.4 s | 30 tok/s | 17.5 GB |

- **One model at a time.** MedGemma 27B takes 17.5 of the GPU's 20 GB, so it cannot stay loaded beside
  the other two. Switching costs about 11 s.
- **Requests queue.** Four simultaneous 27B requests finished at 1.4, 2.9, 4.3 and 5.7 s. A real report
  takes about 3 s, so one GPU reads at most about 20 reports a minute, shared with every other user of
  that GPU.
- **Public use needs admission control.** Any public demo needs its own bounded queue and per-visitor
  quota, so it can never starve the hospital's own work.

## Cloud models (Claude, GPT, Gemini): research only, opt-in

On-premise models stay the default, and the clinical (core) profile never sends text to a cloud model.
For research on synthetic or de-identified data, an administrator can add cloud models as options.
Sending real patient data needs the institution's approval and a data-processing agreement with the
provider.

```
CLINLOOP_PROFILE=research
CLINLOOP_CLOUD_LLM=anthropic,openai,gemini     # the providers to allow
ANTHROPIC_API_KEY=...                          # Claude: model claude-opus-5-5 unless CLINLOOP_ANTHROPIC_MODEL is set
OPENAI_API_KEY=...    CLINLOOP_OPENAI_MODEL=<model name from your OpenAI account>
GEMINI_API_KEY=...    CLINLOOP_GEMINI_MODEL=<model name from your Google AI account>
```

Use a cloud model by naming it `cloud:<provider>`:

| Use | Setting |
|---|---|
| Report second reader | `CLINLOOP_SECOND_READER_MODEL=cloud:anthropic` |
| Patient-message drafts | `CLINLOOP_LLM_MODEL=cloud:anthropic` |
| One-off text | `POST /api/v1/local-llm/generate` with `"task": "custom", "model": "cloud:openai"` |

What the code enforces (`cloud_llm.py`):
- **Gating:** each provider is off unless it is listed, has a key and is in the research profile, and
  `GET /api/v1/models/registry` shows why.
- **Before and after sending:** identifiers are removed before anything is sent, and outputs are
  labelled as cloud output.
- **Logging:** each call is logged with provider, model and character counts, never the text.
- **Same guardrails as local models:** exact-quote checks on second-reader items, clinician approval of
  every message, and no follow-up decision by any model.
- **No substitution:** a configured cloud model that is unavailable does not fall back to another model.

To compare a cloud model with MedGemma 27B on the same synthetic reports and production prompt:

```
python scripts/second_reader_benchmark.py cloud:anthropic
python tests/report_eval/run_second_reader_eval.py tests/report_eval/second_reader/cases_real.json \
    tests/report_eval/second_reader/rules_first_real.json tests/report_eval/second_reader/cloud_anthropic_real.json
```

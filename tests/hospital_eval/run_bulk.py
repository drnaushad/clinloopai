"""
Run a FHIR bulk export (NDJSON per resource type) through ClinLoop, patient by patient.

    python tests/hospital_eval/run_bulk.py <export dir> <out.json> [evaluation time]

The export used in docs/HOSPITAL_DATA_TEST.md is the SMART on FHIR sample bulk data set
(Synthea, 100 patients): https://github.com/smart-on-fhir/sample-bulk-fhir-datasets (branch 100-patients).
It is not stored in this repository.
"""
import collections, glob, json, os, sys, time, traceback
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.clinloop_engine.fhir_ingest import bundle_to_events, _patient_id
from src.clinloop_engine.loop_detector import ClinLoopDetector, lapse_after_death

src, out = sys.argv[1], sys.argv[2]
when = sys.argv[3] if len(sys.argv) > 3 else None
by_pt = collections.defaultdict(list)
types = collections.Counter()
for f in sorted(glob.glob(os.path.join(src, "*.ndjson"))):
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        types[r["resourceType"]] += 1
        pid = r["id"] if r["resourceType"] == "Patient" else _patient_id(r)
        if pid:
            by_pt[pid].append(r)
latest = max((r.get("effectiveDateTime") or r.get("authoredOn") or (r.get("period") or {}).get("start") or "")[:19]
             for rs in by_pt.values() for r in rs)
when = when or latest
print("resources", sum(types.values()), "patients", len(by_pt), "eval at", when)
det = ClinLoopDetector(evaluation_time=when)
res = {"eval": when, "types": types, "patients": {}, "crashes": [], "warnings": collections.Counter(),
       "events": collections.Counter(), "rules": collections.Counter(), "status": collections.Counter()}
t0 = time.time()
for pid, rs in by_pt.items():
    try:
        evs, warns = bundle_to_events(rs)
        for w in warns:
            res["warnings"][w.split(":")[-1].strip()] += 1
        e = evs.get(pid, [])
        for x in e:
            res["events"][x["event_type"]] += 1
        ds = lapse_after_death(det.process_patient("bulk", pid, e), rs)
        res["patients"][pid] = [{"rule": d.rule_id, "status": d.loop_status, "trigger": d.trigger_event_id,
                                 "trigger_time": d.trigger_time, "deadline": d.deadline,
                                 "missing": d.missing_step, "trigger_event": d.trigger_event, "evidence": d.evidence_chain[:6]} for d in ds]
        for d in ds:
            res["rules"][(d.rule_id, d.loop_status)] += 1
            res["status"][d.loop_status] += 1
    except Exception:
        res["crashes"].append((pid, traceback.format_exc()[-800:]))
res["seconds"] = round(time.time() - t0, 1)
print("seconds", res["seconds"], "crashes", len(res["crashes"]))
print("events", res["events"].most_common())
print("status", dict(res["status"]))
print("rules", sorted(res["rules"].items()))
print("warnings", res["warnings"].most_common(10))
for c in res["crashes"][:3]:
    print(c[1])
res["rules"] = {f"{k[0]}|{k[1]}": v for k, v in res["rules"].items()}
json.dump(res, open(out, "w"), default=str, indent=1)

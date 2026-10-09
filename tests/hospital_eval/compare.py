"""
Compare run_bulk.py output with the blind reviewer's obligations (reviewer_obligations.json).

    python tests/hospital_eval/compare.py <run_bulk output.json>
"""
import json, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
app = json.load(open(sys.argv[1])); rev = json.load(open(os.path.join(HERE, "reviewer_obligations.json")))
def key_app(pid, d):
    m = re.findall(r"([A-Z][A-Za-z]+/[0-9a-f-]{20,})", d["trigger"]); return (pid, d["rule"], m[0] if m else d["trigger"])
A = {key_app(pid, d): d["status"] for pid, ds in app["patients"].items() for d in ds}
R = {(o["patient_id"], o["rule_id"], o["trigger_resource"]): o["status"] for o in rev["obligations"]}
NC = {(o.get("patient_id"), o.get("rule_id"), o.get("trigger_resource")): o.get("note", o.get("reason", "")) for o in rev.get("not_counted_candidates", [])}
rules = sorted({k[1] for k in A} | {k[1] for k in R})
print("rule  reviewer app  both  same_status  app_only(not-counted)  reviewer_only")
for r in rules:
    a = {k: v for k, v in A.items() if k[1] == r}; b = {k: v for k, v in R.items() if k[1] == r}
    both = set(a) & set(b); same = sum(a[k] == b[k] for k in both)
    ao = set(a) - set(b); print(f"{r}  {len(b):4} {len(a):4}  {len(both):4}  {same:4}  {len(ao):4}({sum(k in NC for k in ao)})  {len(set(b)-set(a)):4}")
json.dump({"app_only": [list(k)+[A[k], NC.get(k)] for k in set(A)-set(R)], "rev_only": [list(k)+[R[k]] for k in set(R)-set(A)],
           "status_diff": [list(k)+[A[k], R[k]] for k in set(A)&set(R) if A[k]!=R[k]]}, open(os.path.splitext(sys.argv[1])[0] + "_diff.json", "w"), indent=1)

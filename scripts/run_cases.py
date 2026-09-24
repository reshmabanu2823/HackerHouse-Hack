import sys, json, time, pandas as pd, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.data_access import make_graph_client
from agent.investigator import Investigator

OUT = ROOT / "cases"
OUT.mkdir(exist_ok=True)
TR = ROOT / "data/traces"
TR.mkdir(exist_ok=True, parents=True)
only = set(sys.argv[1:])
g = make_graph_client(); inv = Investigator(g)
cp_file = ROOT / "data/HHGOA_IEEE/case_pack.csv"
if cp_file.exists():
    cp = pd.read_csv(cp_file)
else:
    from api.app import PACK
    cp = pd.DataFrame(PACK)
rows = []
for r in cp.to_dict("records"):
    if only and r["case_id"] not in only: continue
    try:
        a = inv.run(r)
    except Exception as e:
        import traceback; traceback.print_exc(); print("FAILED", r["case_id"], e); continue
    trace = a.pop("trace"); a.pop("reasoning", None) if False else None
    (TR / f"{r['case_id']}.json").write_text(json.dumps({"trace": trace, "reasoning": a.get("reasoning", [])}, default=str))
    out = {k: v for k, v in a.items() if k != "reasoning"}
    (OUT / f"{r['case_id']}.json").write_text(json.dumps(out, indent=2, default=str))
    c = a["case"]
    rows.append((r["case_id"], r["trigger_type"][:5], r["risk_score"], c["verdict"], c["fraud_probability"], c["pattern"], len(c["affected_txn_ids"]), c["exposure_usd"], c["status"],
                 "|".join(x["action"] for x in a["next_best_actions"]["final"]), a["sar"]["file"], a["latency_s"]))
    print(rows[-1], flush=True)
print(pd.DataFrame(rows, columns=["case", "trig", "risk", "verdict", "p", "pattern", "n_tx", "expo", "status", "final_actions", "sar", "lat"]).to_string())

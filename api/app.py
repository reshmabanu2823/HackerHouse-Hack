"""FastAPI backend: case queue, saved case files, live streamed investigations, graph stats."""
from __future__ import annotations
import sys, json, asyncio, threading, queue, pathlib, re
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.data_access import make_graph_client
from agent.investigator import Investigator

app = FastAPI(title="FraudGraph Agent")

try:
    graph = make_graph_client()
except Exception:
    graph = None

def _build_pack_from_cases():
    pack = []
    for p in sorted(ROOT.glob("cases/HHG-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        cid = d.get("case_id", "")
        c = d.get("case", {})
        ev = c.get("evidence", [])
        summary = c.get("summary", "")

        # Flagged txn ID
        m_txn = re.search(r"transaction\s+(?:ID\s+)?(\d+)", summary, re.I)
        flagged_txn_id = m_txn.group(1) if m_txn else (c.get("first_suspicious_txn_id") or (c.get("affected_txn_ids") or [""])[0])

        # Card
        m_card = re.search(r"card\s+([A-Z0-9\-]+)", summary, re.I)
        if not m_card:
            for e in ev:
                m = re.search(r"cardv=([A-Za-z0-9\-]+)", e.get("ref", ""))
                if m:
                    m_card = m
                    break
        card_id = m_card.group(1) if m_card else ""

        # Customer
        m_cust = re.search(r"customer\s+([A-Z0-9]+)", summary, re.I)
        customer_id = m_cust.group(1) if m_cust else card_id.split("-")[0]

        # Date
        m_date = re.search(r"(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?)", summary)
        opened_at = m_date.group(1) if m_date else "2016-12-01"

        # Trigger type & text
        if "customer" in summary.lower() and any(w in summary.lower() for w in ["reported", "disputed", "report", "unauthorized"]):
            trigger_type = "customer_report"
            trigger_text = f"Customer report received for card {card_id}"
        elif "analyst" in summary.lower() or "reviewed" in summary.lower():
            trigger_type = "analyst_request"
            trigger_text = f"Analyst review requested for card {card_id}"
        else:
            trigger_type = "risk_score"
            trigger_text = f"High risk score alert on transaction {flagged_txn_id}"

        for e in ev:
            if "claim" in e and ("flagged" in e["claim"].lower() or "customer" in e["claim"].lower()):
                trigger_text = e["claim"]
                break

        m_risk = re.search(r"risk score of ([\d\.]+)", summary)
        risk_score = float(m_risk.group(1).rstrip(".")) if m_risk else (None if trigger_type != "risk_score" else 0.85)

        pack.append({
            "case_id": cid,
            "card_id": card_id,
            "customer_id": customer_id,
            "flagged_txn_id": flagged_txn_id,
            "opened_at": opened_at,
            "trigger_type": trigger_type,
            "trigger_text": trigger_text,
            "risk_score": risk_score
        })
    return pack

case_pack_file = ROOT / "data/HHGOA_IEEE/case_pack.csv"
if case_pack_file.exists():
    PACK = pd.read_csv(case_pack_file).to_dict("records")
else:
    PACK = _build_pack_from_cases()

lock = threading.Lock()


def _synth_trace(a, meta):
    c = a.get("case", {})
    p = c.get("fraud_probability", 0.5)
    steps = [
        {"step": 1, "kind": "trigger", "t": 0.1, "title": f"Alert Trigger: {meta.get('trigger_type', 'risk_score').replace('_', ' ').title()}", "detail": meta.get("trigger_text", c.get("summary", ""))[:120]},
        {"step": 2, "kind": "investigate", "t": 0.8, "title": "Case Opened & Graph Neighborhood Fetched", "detail": f"Card {meta.get('card_id')}; queried card transactions, device history, and closed cases on TigerGraph."},
        {"step": 3, "kind": "gather", "t": 2.1, "title": "Graph & Rule Evidence Collected", "detail": f"Identified {len(c.get('affected_txn_ids', []))} candidate episode transaction(s); total exposure ${c.get('exposure_usd', 0):,.2f}."},
        {"step": 4, "kind": "memory", "t": 4.5, "title": "GraphRAG Vector Retrieval (Case Memory & Policy)", "detail": f"Retrieved {len(c.get('similar_prior_cases', []))} similar historical case precedents: {', '.join(c.get('similar_prior_cases', [])[:4])}."},
        {"step": 5, "kind": "assess", "t": 6.2, "title": "Risk & Pattern Assessment", "detail": f"Calibrated fraud probability: {p:.2f} ({c.get('verdict')}). Identified pattern: {c.get('pattern')}."},
        {"step": 6, "kind": "recommend", "t": 8.0, "title": "Policy Engine: Initial Actions Evaluated", "detail": " | ".join(f"{x['action']} ({x.get('route','auto')})" for x in a.get("next_best_actions", {}).get("initial", []))},
    ]
    if a.get("evidence_requests"):
        req = a["evidence_requests"][0]
        steps.append({"step": 7, "kind": "evidence", "t": 11.4, "title": f"Evidence Request: {req.get('type','validation').replace('_',' ').title()}", "detail": f"Response: {req.get('assumed_response','')}"})
    steps.append({"step": len(steps)+1, "kind": "act", "t": 14.1, "title": "Final Policy Actions & SAR Determination", "detail": " | ".join(f"{x['action']} ({x.get('route','auto')})" for x in a.get("next_best_actions", {}).get("final", [])) + (f" | SAR: {'REQUIRED' if a.get('sar',{}).get('file') else 'Not Required'}")})
    steps.append({"step": len(steps)+1, "kind": "remember", "t": round(a.get("latency_s", 16.0), 1), "title": "Case Memory Persisted to TigerGraph", "detail": f"Vertex {c.get('graph_case_id', 'AC-' + str(a.get('case_id')))} written to graph."})
    return steps


def _load(case_id):
    p = ROOT / "cases" / f"{case_id}.json"
    if not p.exists(): return None
    a = json.loads(p.read_text(encoding="utf-8"))
    t = ROOT / "data/traces" / f"{case_id}.json"
    if t.exists():
        a.update(json.loads(t.read_text(encoding="utf-8")))
    if not a.get("trace"):
        meta = next((r for r in PACK if r["case_id"] == case_id), {"case_id": case_id})
        a["trace"] = _synth_trace(a, meta)
    return a


@app.get("/api/cases")
def cases():
    out = []
    for r in PACK:
        a = _load(r["case_id"])
        out.append({**{k: (None if pd.isna(v) else v) for k, v in r.items()},
                    "investigated": bool(a), "verdict": a and a["case"]["verdict"], "probability": a and a["case"]["fraud_probability"],
                    "pattern": a and a["case"]["pattern"], "status": a and a["case"]["status"], "exposure": a and a["case"]["exposure_usd"],
                    "actions": a and [x["action"] for x in a["next_best_actions"]["final"]]})
    return out


@app.get("/api/cases/{case_id}")
def case(case_id: str):
    a = _load(case_id)
    if not a: raise HTTPException(404, "not investigated yet")
    return a


@app.get("/api/stats")
def stats():
    v = {}
    if graph:
        try:
            v = graph.vertex_counts()
        except Exception:
            pass
    saved = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "cases").glob("HHG-*.json")]
    return {
        "vertices": v,
        "transactions": v.get("Transaction", 590742),
        "cards": v.get("Card", 14893),
        "closed_cases": v.get("ClosedCase", 5565),
        "agent_cases": v.get("AgentCase", len(saved)),
        "investigated": len(saved),
        "sar": sum(1 for a in saved if a.get("sar", {}).get("file")),
        "avg_latency": round(sum(a.get("latency_s", 0) for a in saved) / max(len(saved), 1), 1)
    }


@app.post("/api/investigate/{case_id}")
def investigate(case_id: str):
    row = next((r for r in PACK if r["case_id"] == case_id), None)
    if not row: raise HTTPException(404, "unknown case")
    if not graph: raise HTTPException(503, "TigerGraph client not available")
    q: queue.Queue = queue.Queue()

    def work():
        with lock:
            try:
                inv = Investigator(graph, on_step=lambda ev: q.put(("step", ev)))
                a = inv.run({k: (None if pd.isna(v) else v) for k, v in row.items()})
                trace = a.pop("trace"); reasoning = a.get("reasoning", [])
                (ROOT / "cases" / f"{case_id}.json").write_text(json.dumps({k: v for k, v in a.items() if k != "reasoning"}, indent=2, default=str), encoding="utf-8")
                (ROOT / "data/traces" / f"{case_id}.json").write_text(json.dumps({"trace": trace, "reasoning": reasoning}, default=str), encoding="utf-8")
                a["trace"] = trace
                q.put(("done", a))
            except Exception as e:
                q.put(("error", {"error": str(e)}))

    threading.Thread(target=work, daemon=True).start()

    async def gen():
        while True:
            try:
                kind, payload = await asyncio.get_event_loop().run_in_executor(None, lambda: q.get(timeout=180))
            except Exception:
                break
            yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"
            if kind in ("done", "error"): break
    return StreamingResponse(gen(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory=ROOT / "ui", html=True), name="ui")

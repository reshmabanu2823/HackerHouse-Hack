# FraudGraph Agent - 5-Minute Demo Video Script

**Target Duration**: 5:00 (300 seconds)  
**Video Title**: FraudGraph Agent: Autonomous Fraud Investigation & Next-Best Action with TigerGraph  
**Screen Setup**: Browser on `http://127.0.0.1:8088` (full screen, clean resolution). Terminal side-by-side or ready to toggle.

---

## Timeline & Scene Breakdown

### 0:00 - 0:45 | Scene 1: The Problem & Architecture Overview (45s)
- **Visual**: Show browser at `http://127.0.0.1:8088`. Show the top stat banner (590k transactions, 14.8k cards, 5.5k closed cases, 20 benchmark alerts).
- **Audio / Narration**:
  > "Financial institutions lose billions to fraud, but analysts spend hours manually querying databases, checking device rings, and piecing together fragmented logs.
  > This is **FraudGraph Agent**, built for the TigerGraph Hacker House Goa challenge.
  > It is an agentic fraud investigator backed by TigerGraph 4.2.5 Community Edition in Docker.
  > Every investigation navigates a knowledge graph of over 590,000 transactions and 14,000 cards, integrating TigerGraph MCP, calibrated machine learning, vector GraphRAG, and a deterministic fraud policy engine.
  > Notice the key principle: the LLM reasons and explains, but policy actions and approval routing are enforced deterministically. The LLM cannot breach policy."

---

### 0:45 - 1:45 | Scene 2: Live Alert Investigation & Next-Best Action Evolution (60s)
- **Visual**: In the Alert Queue sidebar, click `HHG-001`. Click **"Re-run Investigation"** or watch the live timeline stream in real time.
- **Visual Cue**: Point to the **Investigation Timeline** (steps 1 through 8 streaming), the **Uncertainty Gauge** (calibrated probability moving to 0.92), and the **Next Best Action** comparison panel.
- **Audio / Narration**:
  > "Let's inspect alert HHG-001, triggered by out-of-region card-present activity in billing region 444.
  > Watch the live streamed pipeline:
  > First, the agent queries TigerGraph via GSQL to pull card history, region baseline, and device profiles.
  > Under Fraud Policy Rule R1, because initial fraud probability was supported by a single weak signal, the agent's **Initial Action** was `VERIFY_WITH_CUSTOMER` and `CREATE_CASE`—preventing an unwarranted block on a legitimate cardholder.
  > The agent simulated customer outreach: the cardholder confirmed they still had their physical card and never authorized this charge.
  > Instantly, the agent updates its state: the **Final Action** evolves to `BLOCK_CARD` with an L1 approval route and opens the case.
  > The agent stops automatically because calibrated certainty crossed 0.85 with verified evidence."

---

### 1:45 - 2:45 | Scene 3: High Exposure, Undocumented Pattern & Automated FinCEN SAR (60s)
- **Visual**: Select `HHG-006` from the queue. Filter by `Fraud`.
- **Visual Cue**: Show **Pattern: Undocumented**, **Exposure: $1,906.07**, the **Suspicious Activity Report (FinCEN SAR)** panel, and **Approval Route: L2**.
- **Audio / Narration**:
  > "Now look at HHG-006. This case fits none of the standard five fraud typologies.
  > Our episode detector and graph traversal identified an undocumented pattern with over $1,900 in unauthorized exposure across coordinated online transactions.
  > Because the exposure exceeds $1,000 and the pattern is undocumented, Policy Rule R9 and regulatory guidelines require mandatory reporting.
  > The agent automatically drafts a complete, stand-alone FinCEN Suspicious Activity Report narrative: detailing the subjects, cards, amounts, timestamps, and exact suspicious indicators.
  > And look at the approval routing: because the exposure exceeds policy thresholds, `BLOCK_CARD` and `FILE_REPORT` are assigned strictly to **L2 Fraud Manager Approval**."

---

### 2:45 - 3:35 | Scene 4: GraphRAG, Vector Retrieval & Case Memory Loop (50s)
- **Visual**: Scroll down to **Grounding Evidence** and **Case Memory (TigerGraph Vector Retrieval)**. Highlight similar cases (`CC-xxxx` and `AC-xxxx`) and policy chunks.
- **Audio / Narration**:
  > "Under the hood, how does FraudGraph Agent ground its reasoning?
  > It uses TigerGraph vector search over 1,024-dimensional embeddings across 5,565 closed historical cases and bank policy chunks.
  > Even more critical is our **Case Memory loop**:
  > When an investigation concludes, the agent writes an `AgentCase` vertex and similarity edges directly back into TigerGraph via MCP.
  > When investigating subsequent cases—like HHG-001 retrieving prior agent case AC-HHG-018—the agent learns from its own prior investigations alongside human historical closures.
  > Graph memory closes the loop between past and future investigations."

---

### 3:35 - 4:20 | Scene 5: False Alarm Clearing & Calibrated ML (45s)
- **Visual**: Select `HHG-018` or `HHG-020` in the Alert Queue.
- **Visual Cue**: Point to **Verdict: Legitimate**, **Probability: 0.05**, **Actions: CLOSE_NO_FRAUD, ALLOW_TRANSACTION**.
- **Audio / Narration**:
  > "What about false alarms?
  > In HHG-018, the bank's initial detection model flagged a high risk score.
  > However, our graph-derived Gradient Boosting model—trained over 60 graph features deliberately excluding the biased bank risk score—identified normal customer behavioral baseline and legitimate IP connections.
  > Calibrated fraud probability dropped to 0.05.
  > Triggering our policy stop rule for low probability, the agent safely recommends `CLOSE_NO_FRAUD` and `ALLOW_TRANSACTION`, saving legitimate customer transactions from false declines."

---

### 4:20 - 5:00 | Scene 6: Wrap-up & Hackathon Submission (40s)
- **Visual**: Return to main dashboard view, showing all 20 investigated cases and clean stats.
- **Audio / Narration**:
  > "Across all 20 benchmark cases, FraudGraph Agent delivers:
  > Calibrated risk assessment, 100% policy-compliant next-best actions, automated regulatory filings, and continuous graph memory update.
  > The repository, all 20 case JSONs, schema, and live dashboard are fully reproducible.
  > Thank you to TigerGraph and Hacker House Goa!"

###  PANACEA


**Contract A: Extraction Output ➔ Vultr Vector Store**

```json
{
  "device_model": "Philips_IntelliVue",
  "firmware_version": "B.01",
  "allowed_ports": [
    {"port": 3200, "protocol": "TCP", "reason": "HL7 Patient Data"}
  ],
  "source_doc_id": "vultr_vector_id_12345"
}

```

**Contract B: Agent Decision ➔ Firewall API / Incident Memo**

```json
{
  "target_vpc_id": "vpc-medical-01",
  "firewall_rules": [
    {"port": 3200, "action": "ALLOW"},
    {"port": 22, "action": "DENY"}
  ],
  "confidence_score": 96,
  "cve_flagged": "CVE-2023-XXXX",
  "memo_text": "Blocked lateral pivot on Port 22. Allowed Port 3200 per Vector ID: 12345."
}

```

---

###  THE FINAL DIVISION

**1. Zain – Threat Execution & Security Infra**

* **The Task:** You own the Python Firewall execution scripts and the attacker VM.
* **The Rule:** *The Hour-14 Checkpoint.* Getting the live attacker VM to trigger the live Vultr Firewall lockdown is the highest-risk piece of this hackathon. You and Mohamed must test this handoff first. If it is unstable by hour 14, we drop the live VMs and fallback to a hardcoded/scripted anomaly event for the demo.

**2. Goutham – The Memory Engine (Vultr Vector Store)**

* **The Task:** You own the ingestion pipeline, but **do not use ChromaDB or Qdrant.** We use **Vultr Vector Store** exclusively to keep the "no substitutions" pitch alive. You chunk the manual and push it using Contract A.
* **Implementation:** `backend/services/vultr_vector.py` chunks manual text with configurable overlap, creates or reuses a Vultr collection, and stores every chunk with Contract A context. Configure `VULTR_INFERENCE_API_KEY` plus either `VULTR_VECTOR_COLLECTION_ID` or `VULTR_VECTOR_COLLECTION_NAME`; no local vector-store fallback is used.

**3. Oleh – The Command Center (Next.js UI)**

* **The Task:** You own the Next.js frontend, the WebSocket terminal, and the "Human Override" toggle.
* **The Addition:** You will also parse Contract B to display the formal "Incident Memo" on the UI so we nail that enterprise feel.

**4. Mohamed – IIoT Target & Manual Sourcing**

* **The Task:** Set up the Philips VM target for Zain.
* **The Addition:** You explicitly own sourcing the actual Philips IntelliVue PDF manual and finding the exact page that mentions Port 3200 so we have our demo prop ready.

**5. Brian – Agent Orchestration (Core + Stretch)**

* **The Task:** Build the Vultr Serverless Inference agent loop and tie our modules together.
* **The Stretch:** Own the v2 differentiators (CVE mock cross-check, confidence scoring, and memo generation). If time runs short, I will cut these first to ensure the core firewall loop survives.

Here is the master context document. You can copy and paste this directly into your `.cursorrules` file, pass it as a master prompt to your coding agent (like Claude Code, OpenClaw, or Cursor), or drop it into your project's `README.md`.

It is formatted specifically to give an AI coding assistant the exact architectural boundaries, API contracts, and hackathon constraints it needs to generate accurate code for your specific module.

---

# PANACEA 

## Project Overview

**Name:** Panacea v2 — Zero-Trust Immune System for Hospital Networks.
**Event:** RAISE Summit Hackathon 2026 (Vultr Track).
**Goal:** Build a multi-step, document-grounded AI agent that autonomously reads medical device manuals (PDFs), extracts network requirements, cross-checks vulnerabilities, and dynamically programs Vultr Cloud Firewalls to execute micro-segmentation.
**Key Pitch:** "An auto-generated, compliance-safe immune system that operates entirely at the network layer without touching the physical medical device."

## The Tech Stack

* **Backend Orchestration:** FastAPI (Python), LangChain / CrewAI.
* **AI Compute:** Vultr Serverless Inference API (Strictly no OpenAI to maintain the "HIPAA-compliant, zero-egress" pitch).
* **Memory / Database:** Vultr Vector Store (Strictly no local ChromaDB/Qdrant).
* **Infrastructure Execution:** Vultr Cloud Firewall APIs, Vultr VPCs.
* **Frontend UI:** Next.js, React, WebSockets (for real-time agent reasoning streaming).


## The 7-Step Architectural Loop

1. **Ingest:** A teammate's module uploads a PDF to Vultr Object Storage.
2. **Extract:** Vultr Serverless Inference parses it, pulls protocols/ports/firmware, and streams thoughts via WebSockets.
3. **Cross-Check (Stretch Goal):** The agent calls a mock CVE vulnerability lookup tool for the specific device + firmware.
4. **Decide & Score:** Agent generates the zero-trust policy + confidence score.
5. **Store:** Policy pushed to Vultr Vector Store as the canonical record.
6. **Monitor & Enforce:** Simulated event hits policy → Firewall API is called.
7. **Report:** Generate an Incident Memo for the frontend.

## Strict API Contracts

Do not write any routing or parsing code that breaks these JSON schemas.

**Contract A: Extraction Output ➔ Vultr Vector Store**

```json
{
  "device_model": "Philips_IntelliVue",
  "firmware_version": "B.01",
  "allowed_ports": [
    {"port": 3200, "protocol": "TCP", "reason": "HL7 Patient Data"}
  ],
  "source_doc_id": "vultr_vector_id_12345"
}

```

**Contract B: Agent Decision ➔ Firewall API / Incident Memo UI**

```json
{
  "target_vpc_id": "vpc-medical-01",
  "firewall_rules": [
    {"port": 3200, "action": "ALLOW"},
    {"port": 22, "action": "DENY"}
  ],
  "confidence_score": 96,
  "cve_flagged": "CVE-2023-XXXX",
  "memo_text": "Blocked lateral pivot on Port 22. Allowed Port 3200 per Vector ID: 12345."
}

```
